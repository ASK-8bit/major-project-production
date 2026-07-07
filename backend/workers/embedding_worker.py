"""
embedding_worker.py — Standalone subprocess for cloning, parsing, embedding, storing.

Runs as a completely separate Python process:
    python embedding_worker.py <repo_url> <session_id> <job_id> <chroma_path> <progress_path>

Never imports supabase — intentional.
supabase + sentence_transformers in the same process causes a native C-extension
deadlock on Windows. Keeping them in separate processes fully avoids this.

Progress is written to: workers/progress/<job_id>.json
FastAPI process reads this file on each /status poll.
"""

import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import ast
import json
import logging
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

EMBED_BATCH_SIZE = 128
CHROMA_BATCH_SIZE = 512


# ============================================================
# Logger Setup
# ============================================================

def setup_logger(job_id: str, log_dir: str) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = str(Path(log_dir) / f"{job_id}.log")

    logger = logging.getLogger(job_id)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("[%(asctime)s] %(levelname)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # File handler
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# ============================================================
# Progress Reporting
# ============================================================

def write_progress(progress_path: str, job_id: str, status: str,
                   chunks_done: int = 0, total_chunks: int = 0,
                   error: str = None, stats: dict = None):
    data = {
        "job_id": job_id,
        "status": status,
        "chunks_done": chunks_done,
        "total_chunks": total_chunks,
        "error": error,
        "stats": stats or {},
    }
    with open(progress_path, "w") as f:
        json.dump(data, f)


# ============================================================
# Document Object
# ============================================================

@dataclass
class Document:
    text: str
    metadata: dict


# ============================================================
# AST Parsing
# ============================================================

def walk_python_files(repo_path: str) -> List[Path]:
    return [f for f in Path(repo_path).rglob("*") if f.suffix == ".py"]


def read_file(file_path: Path) -> Optional[str]:
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def get_source_segment(lines, start, end):
    return "\n".join(lines[start - 1:end])


def build_qualified_name(class_stack, function_name):
    if class_stack:
        return ".".join(class_stack + [function_name])
    return function_name


def parse_python_file(file_path: Path) -> List[Document]:
    documents = []
    source = read_file(file_path)
    if source is None:
        return documents
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return documents

    lines = source.splitlines()
    module_name = file_path.stem

    class StackVisitor(ast.NodeVisitor):
        def __init__(self):
            self.class_stack = []

        def visit_ClassDef(self, node):
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node):
            _collect(node, self.class_stack)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            _collect(node, self.class_stack)
            self.generic_visit(node)

    def _collect(node, class_stack):
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        code = get_source_segment(lines, start, end)
        metadata = {
            "file_path": str(file_path),
            "module": module_name,
            "function_name": node.name,
            "qualified_name": build_qualified_name(class_stack, node.name),
            "class_name": class_stack[-1] if class_stack else "",
            "start_line": start,
            "end_line": end,
            "is_method": len(class_stack) > 0,
        }
        documents.append(Document(text=code, metadata=metadata))

    StackVisitor().visit(tree)
    return documents


def parse_repository(files: List[Path]) -> List[Document]:
    all_documents = []
    for file in files:
        all_documents.extend(parse_python_file(file))
    return all_documents


# ============================================================
# Embed + Store
# ============================================================

def batch_iterator(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


def embed_and_store(documents, session_id, job_id, chroma_path, progress_path, logger):
    from sentence_transformers import SentenceTransformer
    import chromadb

    texts = [doc.text for doc in documents]
    metadatas = [doc.metadata for doc in documents]
    total = len(texts)

    logger.info(f"Loading embedding model...")
    write_progress(progress_path, job_id, "embedding", 0, total)
    model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Model loaded. Starting encoding...")

    embed_start = time.perf_counter()
    all_embeddings = model.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    embed_time = round(time.perf_counter() - embed_start, 2)
    logger.info(f"Embedding done in {embed_time}s")

    write_progress(progress_path, job_id, "storing", 0, total)
    logger.info("Storing in ChromaDB...")

    client = chromadb.PersistentClient(path=chroma_path)
    try:
        client.delete_collection(session_id)
    except Exception:
        pass
    collection = client.create_collection(name=session_id)

    store_start = time.perf_counter()
    for i, batch_texts in enumerate(batch_iterator(texts, CHROMA_BATCH_SIZE)):
        start = i * CHROMA_BATCH_SIZE
        end = start + len(batch_texts)
        collection.add(
            ids=[str(uuid.uuid4()) for _ in batch_texts],
            documents=batch_texts,
            embeddings=all_embeddings[start:end].tolist(),
            metadatas=metadatas[start:end],
        )
        write_progress(progress_path, job_id, "storing", end, total)

    store_time = round(time.perf_counter() - store_start, 2)
    logger.info(f"Storage done in {store_time}s")

    return embed_time, store_time


# ============================================================
# Git Clone
# ============================================================

def clone_repo(repo_url: str, logger) -> str:
    import git
    temp_dir = tempfile.mkdtemp(prefix="repo_")
    try:
        logger.info(f"Cloning {repo_url}...")
        git.Repo.clone_from(repo_url, temp_dir, depth=1)
        logger.info("Clone complete.")
        return temp_dir
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone repo: {str(e)}")


# ============================================================
# Main Pipeline
# ============================================================

def run(repo_url, session_id, job_id, chroma_path, progress_path, log_dir):
    logger = setup_logger(job_id, log_dir)
    logger.info("=" * 60)
    logger.info(f"Job started | job_id={job_id} | repo={repo_url}")
    logger.info("=" * 60)

    overall_start = time.perf_counter()
    temp_dir = None

    try:
        write_progress(progress_path, job_id, "cloning")
        temp_dir = clone_repo(repo_url, logger)

        write_progress(progress_path, job_id, "parsing")
        logger.info("Walking Python files...")
        walk_start = time.perf_counter()
        files = walk_python_files(temp_dir)
        walk_time = round(time.perf_counter() - walk_start, 2)
        logger.info(f"Found {len(files)} Python files in {walk_time}s")

        logger.info("Parsing files...")
        parse_start = time.perf_counter()
        documents = parse_repository(files)
        parse_time = round(time.perf_counter() - parse_start, 2)
        logger.info(f"Parsed {len(documents)} chunks in {parse_time}s")

        embed_time, store_time = embed_and_store(
            documents, session_id, job_id, chroma_path, progress_path, logger
        )

        total_time = round(time.perf_counter() - overall_start, 2)

        stats = {
            "python_files": len(files),
            "total_chunks": len(documents),
            "walk_time": walk_time,
            "parse_time": parse_time,
            "embed_time": embed_time,
            "store_time": store_time,
            "total_time": total_time,
        }

        logger.info("=" * 60)
        logger.info("COMPLETE")
        logger.info(f"Python Files  : {len(files)}")
        logger.info(f"Chunks Indexed: {len(documents)}")
        logger.info(f"Walk Time     : {walk_time}s")
        logger.info(f"Parse Time    : {parse_time}s")
        logger.info(f"Embed Time    : {embed_time}s")
        logger.info(f"Store Time    : {store_time}s")
        logger.info(f"Total Time    : {total_time}s")
        logger.info("=" * 60)

        write_progress(progress_path, job_id, "ready", len(documents), len(documents), stats=stats)

        # Update Supabase directly from worker
        # Safe to import here — sentence_transformers is already done
        from supabase import create_client
        from dotenv import load_dotenv
        load_dotenv()
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        sb.table("jobs").update({
            "status": "ready",
            "chunks_done": len(documents),
            "total_chunks": len(documents),
        }).eq("job_id", job_id).execute()
        sb.table("sessions").update({
            "status": "ready",
            "total_chunks": len(documents),
        }).eq("session_id", session_id).execute()
        logger.info("Supabase updated successfully.")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        write_progress(progress_path, job_id, "failed", error=str(e))

        try:
            from supabase import create_client
            from dotenv import load_dotenv
            load_dotenv()
            sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
            sb.table("jobs").update({"status": "failed", "error": str(e)}).eq("job_id", job_id).execute()
            sb.table("sessions").update({"status": "failed"}).eq("session_id", session_id).execute()
        except Exception:
            pass  # don't let supabase failure hide the original error

    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    # Args: repo_url session_id job_id chroma_path progress_path log_dir
    if len(sys.argv) != 7:
        print("Usage: python embedding_worker.py <repo_url> <session_id> <job_id> <chroma_path> <progress_path> <log_dir>")
        sys.exit(1)

    _, repo_url, session_id, job_id, chroma_path, progress_path, log_dir = sys.argv
    run(repo_url, session_id, job_id, chroma_path, progress_path, log_dir)
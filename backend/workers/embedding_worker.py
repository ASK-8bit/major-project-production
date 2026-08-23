"""
embedding_worker.py — Long-lived worker.
Loads SentenceTransformer once, then processes upload jobs via stdin.

Protocol (one JSON object per line):
  → stdin: {
        "repo_url": "...",
        "session_id": "...",
        "job_id": "...",
        "progress_path": "...",
        "log_dir": "..."
    }
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

from dotenv import load_dotenv
load_dotenv()

EMBED_BATCH_SIZE = 128
CHROMA_BATCH_SIZE = 512


# ============================================================
# Logger + Progress (same as before)
# ============================================================
def setup_logger(job_id: str, log_dir: str) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_path = str(Path(log_dir) / f"{job_id}.log")
    logger = logging.getLogger(job_id)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


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
# Document + AST Parsing (unchanged)
# ============================================================
@dataclass
class Document:
    text: str
    metadata: dict


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


def batch_iterator(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


# ============================================================
# Embed + Store (now uses the pre-loaded model)
# ============================================================
def embed_and_store(model, documents, session_id, job_id, progress_path, logger):
    import chromadb

    texts = [doc.text for doc in documents]
    metadatas = [doc.metadata for doc in documents]
    total = len(texts)

    logger.info("Starting encoding with pre-loaded model...")
    write_progress(progress_path, job_id, "embedding", 0, total)

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
    logger.info("Storing in Chroma Cloud...")

    client = chromadb.CloudClient(
        api_key=os.getenv("CHROMA_API_KEY"),
        tenant=os.getenv("CHROMA_TENANT"),
        database=os.getenv("CHROMA_DATABASE"),
    )

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
# One full job
# ============================================================
def run_job(model, repo_url, session_id, job_id, progress_path, log_dir):
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
            model, documents, session_id, job_id, progress_path, logger
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

        write_progress(
            progress_path, job_id, "ready",
            len(documents), len(documents), stats=stats
        )

        # Update Supabase
        from supabase import create_client
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
            sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
            sb.table("jobs").update({"status": "failed", "error": str(e)}).eq("job_id", job_id).execute()
            sb.table("sessions").update({"status": "failed"}).eq("session_id", session_id).execute()
        except Exception:
            pass
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# Long-lived main loop
# ============================================================
def main():
    from sentence_transformers import SentenceTransformer

    print("Loading SentenceTransformer for embedding worker...", file=sys.stderr, flush=True)
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Embedding model loaded. Worker ready.", file=sys.stderr, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            run_job(
                model=model,
                repo_url=job["repo_url"],
                session_id=job["session_id"],
                job_id=job["job_id"],
                progress_path=job["progress_path"],
                log_dir=job["log_dir"],
            )
        except Exception as e:
            print(f"Failed to process job: {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
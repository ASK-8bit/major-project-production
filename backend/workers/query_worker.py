"""
query_worker.py — Standalone subprocess for embedding a prompt + querying ChromaDB.

Runs as a completely separate Python process:
    python query_worker.py <prompt> <session_id> <chroma_path> <result_path> <top_k>

Never imports supabase — intentional.
Same isolation reason as embedding_worker.py.

Result is written to: <result_path>
FastAPI process reads this file after subprocess completes.
"""

import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import json
import sys


# ============================================================
# Query Pipeline
# ============================================================

def run(prompt: str, session_id: str, chroma_path: str, result_path: str, top_k: int):
    try:
        from sentence_transformers import SentenceTransformer
        import chromadb

        # Embed the prompt
        model = SentenceTransformer("all-MiniLM-L6-v2")
        prompt_embedding = model.encode(
            [prompt],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).tolist()[0]

        # Query ChromaDB collection for this session
        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_collection(name=session_id)

        results = collection.query(
            query_embeddings=[prompt_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        # Build clean chunk list for the LLM context
        chunks = []
        for i in range(len(results["documents"][0])):
            chunks.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })

        result = {"status": "ok", "chunks": chunks}

    except Exception as e:
        result = {"status": "error", "error": str(e), "chunks": []}

    with open(result_path, "w") as f:
        json.dump(result, f)


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: python query_worker.py <prompt> <session_id> <chroma_path> <result_path> <top_k>")
        sys.exit(1)

    _, prompt, session_id, chroma_path, result_path, top_k = sys.argv
    run(prompt, session_id, chroma_path, result_path, int(top_k))
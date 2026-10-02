"""
query_worker.py — Long-lived worker.
Loads SentenceTransformer once, then processes many requests via stdin/stdout.

Protocol (one JSON object per line):
  → stdin:  {"request_id": "...", "prompt": "...", "session_id": "...", "top_k": 5}
  ← stdout: {"request_id": "...", "status": "ok", "chunks": [...]}
            or {"request_id": "...", "status": "error", "error": "...", "chunks": []}
"""

import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import json
import sys
from dotenv import load_dotenv

load_dotenv()

def main():
    from sentence_transformers import SentenceTransformer
    import chromadb

    print("Loading SentenceTransformer...", file=sys.stderr, flush=True)
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Model loaded. Worker ready.", file=sys.stderr, flush=True)

    # Chroma Cloud client is cheap to create, but we can create it once too
    client = chromadb.CloudClient(
        api_key=os.getenv("CHROMA_API_KEY"),
        tenant=os.getenv("CHROMA_TENANT"),
        database=os.getenv("CHROMA_DATABASE"),
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request_id = ""
        try:
            req = json.loads(line)
            request_id = req.get("request_id", "")
            prompt = req["prompt"]
            session_id = req["session_id"]
            top_k = int(req.get("top_k", 5))

            # Embed
            prompt_embedding = model.encode(
                [prompt],
                convert_to_numpy=True,
                normalize_embeddings=True,
            ).tolist()[0]

            # Query
            collection = client.get_collection(name=session_id)
            results = collection.query(
                query_embeddings=[prompt_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            chunks = []
            for i in range(len(results["documents"][0])):
                chunks.append({
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })

            dependency_names = []
            for chunk in chunks:
                deps = chunk.get("metadata", {}).get("dependencies", "") or ""
                if isinstance(deps, str):
                    items = [d.strip() for d in deps.split(",") if d.strip()]
                else:
                    items = [str(d).strip() for d in deps if str(d).strip()]
                for dep in items:
                    if dep and dep not in dependency_names:
                        dependency_names.append(dep)

            if dependency_names:
                dependency_results = collection.get(
                    where={"qualified_name": {"$in": dependency_names}},
                    include=["documents", "metadatas"],
                )
                for i in range(len(dependency_results.get("documents", []))):
                    meta = dependency_results["metadatas"][i]
                    qualified_name = meta.get("qualified_name")
                    if not qualified_name:
                        continue
                    if any(existing.get("metadata", {}).get("qualified_name") == qualified_name for existing in chunks):
                        continue
                    chunks.append({
                        "text": dependency_results["documents"][i],
                        "metadata": meta,
                        "distance": 0.0,
                    })

            response = {
                "request_id": request_id,
                "status": "ok",
                "chunks": chunks,
            }

        except Exception as e:
            response = {
                "request_id": request_id,
                "status": "error",
                "error": str(e),
                "chunks": [],
            }

        # One JSON line back
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
import json
import os
import urllib.request
from typing import List, Dict, Any


def _build_fallback_answer(prompt: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not chunks:
        return {
            "answer": "I could not find enough relevant code in the repository to answer this question confidently.",
            "citations": [],
        }

    top_chunk = chunks[0]
    metadata = top_chunk.get("metadata", {}) or {}
    text = top_chunk.get("text", "") or ""
    file_path = metadata.get("file_path", "") or "unknown"
    qualified_name = metadata.get("qualified_name") or metadata.get("function_name") or "unknown"
    start_line = metadata.get("start_line")
    end_line = metadata.get("end_line")

    snippet = text.strip().splitlines()
    preview = "\n".join(snippet[:6]) if snippet else ""

    answer = (
        f"Based on the retrieved code, the relevant logic appears to be centered around {qualified_name}. "
        f"The snippet suggests that the implementation is focused on the code path described by your question. "
        f"Here is the key extracted logic:\n\n{preview}"
    )

    citations = []
    if file_path:
        citation = {
            "file_path": file_path.split("/")[-1],
            "qualified_name": qualified_name,
            "start_line": start_line,
            "end_line": end_line,
        }
        citations.append(citation)

    return {
        "answer": answer,
        "citations": citations,
    }


def _build_llm_answer(prompt: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    context = []
    for chunk in chunks[:5]:
        metadata = chunk.get("metadata", {}) or {}
        context.append(
            {
                "file": metadata.get("file_path", "unknown"),
                "symbol": metadata.get("qualified_name") or metadata.get("function_name") or "unknown",
                "code": chunk.get("text", "")[:1800],
            }
        )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You explain code using only the provided repository snippets. Be concise, grounded, and cite the file/symbol when possible.",
            },
            {
                "role": "user",
                "content": json.dumps({"prompt": prompt, "context": context}),
            },
        ],
        "temperature": 0.2,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))

    content = body["choices"][0]["message"]["content"]
    citations = []
    for chunk in chunks[:3]:
        metadata = chunk.get("metadata", {}) or {}
        file_path = metadata.get("file_path", "") or ""
        if file_path:
            citations.append({
                "file_path": file_path.split("/")[-1],
                "qualified_name": metadata.get("qualified_name") or metadata.get("function_name") or "unknown",
                "start_line": metadata.get("start_line"),
                "end_line": metadata.get("end_line"),
            })

    return {"answer": content, "citations": citations}


def build_answer(prompt: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a concise, grounded answer from retrieved code chunks.
    If an OpenAI-compatible API key is configured, use it to generate a better answer.
    Otherwise fall back to a deterministic explanation built from the top retrieved chunk.
    """
    if not chunks:
        return {
            "answer": "I could not find enough relevant code in the repository to answer this question confidently.",
            "citations": [],
        }

    try:
        return _build_llm_answer(prompt, chunks)
    except Exception:
        return _build_fallback_answer(prompt, chunks)

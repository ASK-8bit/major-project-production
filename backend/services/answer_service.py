import json
import os
import re
import urllib.request
from typing import List, Dict, Any


def _normalize_symbol_name(name: str) -> str:
    if not name:
        return ""
    value = str(name).strip().lower().replace("-", "_")
    return value.split(".")[-1] if "." in value else value


def _extract_dependency_names(chunk: Dict[str, Any]) -> set[str]:
    text = (chunk.get("text") or "")
    metadata = chunk.get("metadata") or {}
    names: set[str] = set()

    for key in [
        metadata.get("qualified_name"),
        metadata.get("function_name"),
        metadata.get("class_name"),
    ]:
        if key:
            names.add(str(key).strip())
            names.add(_normalize_symbol_name(key))

    for match in re.finditer(r"(?:\b[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
        candidate = match.group(1)
        if candidate:
            names.add(candidate)
            names.add(candidate.lower())

    # capture common direct calls without dot syntax like validate_token(user)
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
        candidate = match.group(1)
        if candidate and candidate.lower() not in {"if", "for", "while", "return", "print", "assert"}:
            names.add(candidate)
            names.add(candidate.lower())

    return names


def _expand_dependency_context(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not chunks:
        return []

    expanded: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    # Prefer explicit dependency metadata captured at indexing time.
    dependency_lookup: set[str] = set()
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        deps = metadata.get("dependencies", "") or ""
        if isinstance(deps, str):
            items = [d.strip() for d in deps.split(",") if d.strip()]
        else:
            items = [str(d).strip() for d in deps if str(d).strip()]
        for dep in items:
            if dep:
                dependency_lookup.add(str(dep))

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        qualified_name = metadata.get("qualified_name") or metadata.get("function_name") or ""
        key = (metadata.get("file_path", ""), qualified_name)
        if key not in seen:
            expanded.append(chunk)
            seen.add(key)

    if dependency_lookup:
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            qualified_name = metadata.get("qualified_name") or metadata.get("function_name") or ""
            if qualified_name in dependency_lookup:
                key = (metadata.get("file_path", ""), qualified_name)
                if key not in seen:
                    expanded.append(chunk)
                    seen.add(key)
        return expanded[:8]

    if len(chunks) <= 1:
        return expanded

    for anchor in list(chunks):
        anchor_meta = anchor.get("metadata") or {}
        anchor_symbols = _extract_dependency_names(anchor)
        anchor_main = anchor_meta.get("qualified_name") or anchor_meta.get("function_name") or ""
        anchor_main_names = {anchor_main, _normalize_symbol_name(anchor_main), (anchor_main.split(".")[-1] if "." in anchor_main else anchor_main)}

        for candidate in chunks:
            if candidate is anchor:
                continue

            meta = candidate.get("metadata") or {}
            candidate_name = meta.get("qualified_name") or meta.get("function_name") or ""
            candidate_names = {
                candidate_name,
                _normalize_symbol_name(candidate_name),
                (candidate_name.split(".")[-1] if "." in candidate_name else candidate_name),
            }

            match = bool(anchor_symbols.intersection(candidate_names))
            if not match:
                match = any(name in anchor_symbols for name in candidate_names)
            if not match:
                match = any(name in candidate_names for name in anchor_main_names)

            if match:
                key = (meta.get("file_path", ""), candidate_name)
                if key not in seen:
                    expanded.append(candidate)
                    seen.add(key)

    return expanded[:8]


def _summarize_code_purpose(chunk: Dict[str, Any]) -> str:
    metadata = chunk.get("metadata", {}) or {}
    text = (chunk.get("text") or "").strip()
    symbol = metadata.get("qualified_name") or metadata.get("function_name") or "this code"
    name = metadata.get("function_name") or "this function"

    lower = text.lower()
    if "if not" in lower or "if not " in lower:
        purpose = "checks whether the input is valid before continuing"
    elif "return false" in lower or "raise" in lower:
        purpose = "validates input and stops execution on invalid conditions"
    elif "create" in lower or "new " in lower:
        purpose = "creates a new object or session"
    elif "save" in lower or "insert" in lower or "update" in lower:
        purpose = "stores or updates data"
    elif "fetch" in lower or "get_" in lower or "load" in lower:
        purpose = "retrieves data from a source"
    elif "delete" in lower or "remove" in lower:
        purpose = "removes or deletes data"
    elif "validate" in lower or "check" in lower or "auth" in lower:
        purpose = "validates the request or user before proceeding"
    elif "token" in lower and "return" in lower:
        purpose = "generates or validates a token for access"
    else:
        purpose = "coordinates the related logic described in the snippet"

    if name.lower() == "class":
        return f"This class is responsible for {purpose}."
    return f"{symbol} is a function that {purpose}. In plain English, it handles the flow of logic needed to validate inputs, call related helpers, and return the final result."


def _build_fallback_answer(prompt: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    context_chunks = _expand_dependency_context(chunks)
    if not context_chunks:
        return {
            "answer": "I could not find enough relevant code in the repository to answer this question confidently.",
            "citations": [],
        }

    top_chunk = context_chunks[0]
    metadata = top_chunk.get("metadata", {}) or {}
    text = top_chunk.get("text", "") or ""
    file_path = metadata.get("file_path", "") or "unknown"
    qualified_name = metadata.get("qualified_name") or metadata.get("function_name") or "unknown"
    start_line = metadata.get("start_line")
    end_line = metadata.get("end_line")

    snippet = text.strip().splitlines()
    preview = "\n".join(snippet[:6]) if snippet else ""
    purpose_summary = _summarize_code_purpose(top_chunk)

    if len(context_chunks) > 1:
        related_symbols = ", ".join(
            (chunk.get("metadata", {}) or {}).get("qualified_name")
            or (chunk.get("metadata", {}) or {}).get("function_name")
            or "unknown"
            for chunk in context_chunks[1:4]
        )
        answer = (
            f"{purpose_summary} "
            f"Based on the retrieved code, the relevant logic appears to be centered around {qualified_name}. "
            f"This implementation depends on related logic in {related_symbols}, so the surrounding context matters. "
            f"The key flow is:\n\n{preview}"
        )
    else:
        answer = (
            f"{purpose_summary} "
            f"Based on the retrieved code, the relevant logic appears to be centered around {qualified_name}. "
            f"The snippet suggests this code path is focused on the behavior described in the function body. "
            f"The relevant logic is:\n\n{preview}"
        )

    citations = []
    for chunk in context_chunks[:3]:
        meta = chunk.get("metadata", {}) or {}
        file_path = meta.get("file_path", "") or ""
        if file_path:
            citations.append({
                "file_path": file_path.split("/")[-1],
                "qualified_name": meta.get("qualified_name") or meta.get("function_name") or "unknown",
                "start_line": meta.get("start_line"),
                "end_line": meta.get("end_line"),
            })

    return {
        "answer": answer,
        "citations": citations,
    }


def _build_llm_answer(prompt: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    context_chunks = _expand_dependency_context(chunks)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    context = []
    for chunk in context_chunks[:5]:
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
                "content": "You explain code using only the provided repository snippets. Include relevant dependent functions when needed, and cite the file/symbol when possible.",
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
    for chunk in context_chunks[:3]:
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
    Dependency-aware expansion is applied so related functions are included in the context.
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

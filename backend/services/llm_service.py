import os
import time
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# gemini-2.0-flash as requested
model = genai.GenerativeModel("gemini-3.7-flash")


def _build_prompt(question: str, chunks: list[dict]) -> str:
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata") or {}
        source = (
            meta.get("qualified_name")
            or meta.get("file_path")
            or meta.get("module")
            or "unknown"
        )
        context_parts.append(f"[{i}] Source: {source}\n{chunk['text']}")

    context = "\n\n".join(context_parts) if context_parts else "No relevant code chunks found."

    return f"""You are a helpful assistant that answers questions about a legacy Python codebase.
Use the following retrieved code chunks as your main context.
If the answer cannot be found in the chunks, say so clearly.

Context:
{context}

Question: {question}

Answer:"""


def generate_answer(question: str, chunks: list[dict], max_retries: int = 1) -> str:
    """
    Calls Gemini. Retries once on failure.
    Returns the answer text, or an error message if both attempts fail.
    """
    prompt = _build_prompt(question, chunks)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(1.5)  # short backoff before retry
            continue

    return f"[Gemini error after {max_retries + 1} attempts] {last_error}"
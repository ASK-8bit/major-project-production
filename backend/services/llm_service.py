import os
import re
import time
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv
from google.generativeai.types import HarmCategory, HarmBlockThreshold

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-flash-lite-latest")


def _clean_formatting(text: str) -> str:
    """
    Strips markdown heading hashes (#) and asterisks/stars (*) from the text,
    converting lists to clean hyphens and removing bold/italic markers.
    """
    if not text:
        return text

    # 1. Remove heading hashes at the start of lines
    text = re.sub(r'^[ \t]*#{1,6}[ \t]*', '', text, flags=re.MULTILINE)

    # 2. Convert asterisk list bullets to hyphens
    text = re.sub(r'^[ \t]*\*[ \t]+', '- ', text, flags=re.MULTILINE)

    # 3. Strip bold and italic markdown asterisks
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)

    # 4. Remove any remaining stray asterisks or hashes
    text = text.replace('*', '').replace('#', '')

    return text.strip()


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

    return f"""You are an expert Python code analyst helping developers understand a legacy codebase.

Your job is to answer the user's question using ONLY the retrieved code chunks provided below. 
Do not use any external knowledge or invent code that is not present in the context.

Guidelines:
- Base every claim strictly on the given code chunks.
- If the answer cannot be fully determined from the chunks, clearly say what is missing.
- Prefer clear, structured, developer-friendly explanations over vague summaries.
- When relevant, explain:
  - How the feature / logic is implemented
  - Which files, functions, and classes are involved
  - Key dependencies and call relationships
  - Potential impact of modifying the related code

Formatting Rules (STRICT):
- DO NOT use any markdown hash symbols (#, ##, ###) for titles, headings, or section markers.
- DO NOT use any asterisks or stars (*, **, ***) anywhere in your response (no bold asterisks, no italic asterisks, and no star bullets).
- For section headings, simply write the clean title on its own line.
- For lists or bullet points, use plain numbers (1., 2.) or hyphens (- ), never asterisks.
- Write in clean, professional plain text without unnecessary markdown styling symbols.

Retrieved Code Chunks:
{context}

User Question:
{question}

Answer:
Provide a clear and precise explanation grounded in the code above following all formatting rules strictly."""


def generate_answer(question: str, chunks: list[dict], max_retries: int = 1) -> str:
    prompt = _build_prompt(question, chunks)

    generation_config = {
        "temperature": 0.2,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 4096,
    }

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings,
            )

            if not response.candidates:
                return "[Gemini error] No candidates returned (possibly blocked)"

            candidate = response.candidates[0]
            finish_reason = candidate.finish_reason.name if candidate.finish_reason else "UNKNOWN"

            if finish_reason not in ("STOP", "MAX_TOKENS"):
                return f"[Gemini warning] Finish reason: {finish_reason}"

            clean_text = _clean_formatting(response.text)
            return clean_text

        except Exception as e:
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(1.5)
            continue

    return f"[Gemini error after {max_retries + 1} attempts] {last_error}"
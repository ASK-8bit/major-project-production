import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
from core.config import supabase

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# NEW
from google import genai
from google.genai import types

_classifier_client = genai.Client(
    api_key=os.getenv("GEMINI_SECOND_API_KEY")
)


class ClassifierResult(BaseModel):
    is_analytical: bool
    target_file: Optional[str] = None
    function_name: Optional[str] = None
    user_query: str


CLASSIFIER_SYSTEM_PROMPT = """
You are a code query classifier for a Python codebase RAG system.

Your ONLY job is to determine:
1. Is this an ANALYTICAL query (requires code structure analysis)?
2. If yes, which file is the user asking about?
3. If yes, which cached function matches this query (if any)?

ANALYTICAL queries require examining code structure. Examples:
- "How many functions are in payments.py?"
- "Which functions are unused in auth.py?"
- "List all imports in user_service.py"
- "How many classes are in models.py?"
- "Find all recursive functions in utils.py"

RETRIEVAL queries are about understanding/explaining code. Examples:
- "How does authentication work?"
- "Explain the payment flow"
- "What does the login function do?"
- "How is caching implemented?"

AVAILABLE CACHED FUNCTIONS:
{function_list}

RULES:
- If the query matches a cached function exactly → set function_name to that function name
- If no cached function matches → set function_name to null (will be generated)
- target_file must be the file path/module name the user mentioned (e.g. "payments.py", "auth")
- If no specific file mentioned and query is analytical → set target_file to null
- If query is retrieval → is_analytical = false, target_file = null, function_name = null

OUTPUT: Return ONLY valid JSON, no explanation, no markdown, no asterisks:
{{
  "is_analytical": true or false,
  "target_file": "path/to/file.py or null",
  "function_name": "cached_function_name or null",
  "user_query": "original user query here"
}}
"""


def _fetch_available_functions() -> str:
    """
    Fetch all validated function names from Supabase
    to include in master prompt.
    """
    try:
        response = supabase.table("analytical_functions") \
            .select("function_name, sample_query") \
            .eq("is_code_correct", True) \
            .execute()

        if not response.data:
            return "No cached functions available."

        lines = []
        for row in response.data:
            lines.append(f"- {row['function_name']}: {row['sample_query']}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[Classifier] ERROR fetching functions from Supabase: {e}")
        return "No cached functions available."


def _clean_llm_response(text: str) -> str:
    """Remove asterisks and markdown from LLM response."""
    text = text.replace("**", "").replace("*", "")
    text = re.sub(r"```json|```", "", text)
    return text.strip()


def classify_query(prompt: str) -> ClassifierResult:
    """
    LLM Call 1: Classify user query as analytical or retrieval.
    If analytical, identify target file and matching cached function.
    """
    available_functions = _fetch_available_functions()

    system_prompt = CLASSIFIER_SYSTEM_PROMPT.format(
        function_list=available_functions
    )

    full_prompt = f"{system_prompt}\n\nUser Query: {prompt}"

    try:
        response = _classifier_client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
            )
        )
        raw_text = response.text
        cleaned = _clean_llm_response(raw_text)

        parsed = json.loads(cleaned)

        return ClassifierResult(
            is_analytical=parsed.get("is_analytical", False),
            target_file=parsed.get("target_file"),
            function_name=parsed.get("function_name"),
            user_query=parsed.get("user_query", prompt)
        )

    except json.JSONDecodeError as e:
        print(f"[Classifier] ERROR parsing LLM JSON response: {e}")
        print(f"[Classifier] Raw response was: {raw_text}")
        return ClassifierResult(
            is_analytical=False,
            user_query=prompt
        )

    except Exception as e:
        print(f"[Classifier] ERROR during classification: {e}")
        return ClassifierResult(
            is_analytical=False,
            user_query=prompt
        )
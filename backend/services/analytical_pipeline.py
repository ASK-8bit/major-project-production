import os
import re
import json
import uuid
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from core.config import supabase
from services.query_classifier import classify_query, ClassifierResult
from services.github_fetcher import fetch_file
from services.sandbox_executor import execute_function

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

FUNCTION_GENERATION_PROMPT = """
You are a Python code analysis expert.

Generate a single Python function that answers the following query about a Python codebase.

USER QUERY: {user_query}

TARGET FILE CONTENT (first 500 lines):
{file_sample}

STRICT REQUIREMENTS:
1. Function signature must be exactly: def execute_analysis(code_string: str) -> dict
2. Use ast.parse(code_string) to parse the code (ast is already imported)
3. Return ONLY a dict with clear descriptive keys
4. Use ONLY ast and json modules (already available, do not import anything)
5. Handle edge cases (empty file, syntax errors) with try/except inside the function
6. Keep the function focused and minimal

RETURN FORMAT:
- Always return a dict
- Use clear key names like: count, names, details, items, found, result
- Example: {{"count": 5, "names": ["func1", "func2"], "details": {{}}}}

OUTPUT RULES:
- Output ONLY the raw function code
- No markdown formatting
- No asterisks
- No explanations
- No docstrings
- No comments
- No imports
"""


def _clean_generated_code(code: str) -> str:
    """Remove asterisks, markdown fences from LLM generated code."""
    code = code.replace("**", "").replace("*", "")
    code = re.sub(r"```python|```", "", code)
    return code.strip()


def _fetch_function_from_supabase(function_name: str) -> str | None:
    """
    Fetch existing function code from Supabase by function name.
    Returns code string or None if not found.
    """
    try:
        response = supabase.table("analytical_functions") \
            .select("function_code") \
            .eq("function_name", function_name) \
            .eq("is_code_correct", True) \
            .single() \
            .execute()

        if response.data:
            print(f"[AnalyticalPipeline] Cache HIT: Found function '{function_name}' in Supabase")
            supabase.table("analytical_functions") \
                .update({
                    "used_count": response.data.get("used_count", 0) + 1,
                    "last_used_at": datetime.utcnow().isoformat()
                }) \
                .eq("function_name", function_name) \
                .execute()
            return response.data["function_code"]

        print(f"[AnalyticalPipeline] Cache MISS: '{function_name}' not in Supabase")
        return None

    except Exception as e:
        print(f"[AnalyticalPipeline] ERROR fetching function '{function_name}' from Supabase: {e}")
        return None


def _generate_function(user_query: str, file_content: str) -> str | None:
    """
    LLM Call 2: Generate analysis function based on user query and file content.
    Returns cleaned function code string or None on failure.
    """
    file_sample = "\n".join(file_content.splitlines()[:500])

    prompt = FUNCTION_GENERATION_PROMPT.format(
        user_query=user_query,
        file_sample=file_sample
    )

    try:
        response = _classifier_client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
            )
        )
        raw_text = response.text
        cleaned_code = _clean_generated_code(raw_text)
        print(f"[AnalyticalPipeline] Generated new function for query: '{user_query}'")
        return cleaned_code

    except Exception as e:
        print(f"[AnalyticalPipeline] ERROR generating function via LLM: {e}")
        return None


def _store_function(
    function_name: str,
    function_code: str,
    sample_query: str,
    execution_successful: bool
) -> None:
    """Store generated function in Supabase for future reuse."""
    try:
        supabase.table("analytical_functions").insert({
            "id": str(uuid.uuid4()),
            "function_name": function_name,
            "function_code": function_code,
            "sample_query": sample_query,
            "execution_successful": execution_successful,
            "is_code_correct": False,
            "used_count": 1,
            "created_at": datetime.utcnow().isoformat(),
            "last_used_at": datetime.utcnow().isoformat()
        }).execute()
        print(f"[AnalyticalPipeline] Stored new function '{function_name}' in Supabase")

    except Exception as e:
        print(f"[AnalyticalPipeline] ERROR storing function in Supabase: {e}")


def _derive_function_name(user_query: str) -> str:
    """
    Derive a snake_case function name from the user query.
    Example: "How many functions in file?" → "analyze_how_many_functions_in_file"
    """
    words = re.sub(r"[^a-zA-Z0-9\s]", "", user_query.lower()).split()
    words = [w for w in words if w not in {"a", "the", "in", "of", "is", "are", "how", "what", "find", "get"}]
    name = "_".join(words[:6])
    return f"analyze_{name}"


def _get_repo_url(session_id: str) -> str | None:
    """Fetch repo_url from sessions table in Supabase."""
    try:
        response = supabase.table("sessions") \
            .select("repo_url") \
            .eq("session_id", session_id) \
            .single() \
            .execute()

        if response.data:
            return response.data["repo_url"]

        print(f"[AnalyticalPipeline] ERROR: No session found for session_id: {session_id}")
        return None

    except Exception as e:
        print(f"[AnalyticalPipeline] ERROR fetching repo_url for session '{session_id}': {e}")
        return None


async def run_analytical_pipeline(
    prompt: str,
    session_id: str,
    classifier_result: ClassifierResult
) -> dict:
    """
    Main analytical pipeline coordinator.

    Args:
        prompt:            Original user query
        session_id:        Session ID (used to fetch repo_url)
        classifier_result: Output from query_classifier.classify_query()

    Returns:
        dict with keys: success (bool), answer (str), data (dict), source="analytical"
    """

    # STEP 1: Get repo_url from session
    repo_url = _get_repo_url(session_id)
    if not repo_url:
        return {
            "success": False,
            "answer": "Could not find repository URL for this session.",
            "data": None,
            "source": "analytical"
        }

    # STEP 2: Fetch target file from GitHub
    target_file = classifier_result.target_file
    if not target_file:
        return {
            "success": False,
            "answer": "Could not identify which file to analyze from your query. Please mention a specific file name.",
            "data": None,
            "source": "analytical"
        }

    try:
        file_content = fetch_file(repo_url, target_file)
    except FileNotFoundError as e:
        return {
            "success": False,
            "answer": str(e),
            "data": None,
            "source": "analytical"
        }

    # STEP 3: Get or generate function code
    function_code = None
    function_name = classifier_result.function_name
    is_generated = False

    if function_name:
        function_code = _fetch_function_from_supabase(function_name)

    if not function_code:
        print(f"[AnalyticalPipeline] No cached function found, generating new one...")
        function_code = _generate_function(
            user_query=classifier_result.user_query,
            file_content=file_content
        )
        is_generated = True
        function_name = _derive_function_name(classifier_result.user_query)

    if not function_code:
        return {
            "success": False,
            "answer": "Failed to generate analysis function. Please try rephrasing your query.",
            "data": None,
            "source": "analytical"
        }

    # STEP 4: Execute on sandbox
    print(f"[AnalyticalPipeline] Executing function '{function_name}' on sandbox...")
    result = execute_function(
        function_code=function_code,
        file_content=file_content
    )

    # STEP 5: Store if new and successful
    if is_generated:
        _store_function(
            function_name=function_name,
            function_code=function_code,
            sample_query=prompt,
            execution_successful=result["success"]
        )

    # STEP 6: Return result
    if result["success"]:
        answer = f"Analytical result for '{target_file}':\n{json.dumps(result['data'], indent=2)}"
        return {
            "success": True,
            "answer": answer,
            "data": result["data"],
            "source": "analytical"
        }
    else:
        return {
            "success": False,
            "answer": f"Analysis execution failed: {result['error']}",
            "data": None,
            "source": "analytical"
        }
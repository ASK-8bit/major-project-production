import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

from core.config import supabase
from agent.schemas import Plan
from agent.prompts import PLANNER_SYSTEM_PROMPT

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_SECOND_API_KEY"))


def _fetch_available_functions() -> str:
    try:
        response = (
            supabase.table("analytical_functions")
            .select("function_name, sample_query")
            .eq("is_code_correct", True)
            .execute()
        )
        if not response.data:
            return "No cached functions available."

        lines = [f"- {row['function_name']}: {row['sample_query']}" for row in response.data]
        return "\n".join(lines)
    except Exception as e:
        print(f"[Planner] ERROR fetching functions: {e}")
        return "No cached functions available."


def _clean_llm_response(text: str) -> str:
    text = text.replace("**", "").replace("*", "")
    text = re.sub(r"```json|```", "", text)
    return text.strip()


def create_plan(user_query: str) -> Plan:
    available_functions = _fetch_available_functions()
    system_prompt = PLANNER_SYSTEM_PROMPT.format(function_list=available_functions)

    full_prompt = f"{system_prompt}\n\nUser Query: {user_query}"

    try:
        response = _client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1024,
            )
        )
        raw = response.text
        cleaned = _clean_llm_response(raw)
        parsed = json.loads(cleaned)

        plan = Plan(**parsed)
        print(f"[Planner] Created plan with {len(plan.steps)} steps")
        return plan

    except Exception as e:
        print(f"[Planner] ERROR: {e}")
        # Safe fallback → classic RAG
        return Plan(
            steps=[{
                "id": "step_1",
                "tool": "classic_rag_retrieve",
                "args": {"query": user_query}
            }],
            needs_final_explanation=True
        )
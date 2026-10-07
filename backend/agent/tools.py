import uuid
import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

import os
from typing import List
import chromadb
from chromadb.config import Settings

from agent.schemas import ToolResult

from core.config import supabase
from services.github_fetcher import fetch_file
from services.sandbox_executor import execute_function
from agent.schemas import ToolResult

# We reuse your existing generation prompt logic
from services.analytical_pipeline import (
    _generate_function,
    _derive_function_name,
    _clean_generated_code,
)


def multi_query_retrieve(
    sub_queries: List[str],
    session_id: str,
    top_k_per_query: int = 6
) -> ToolResult:
    """
    Run multiple semantic searches against the session's Chroma collection
    and return merged + deduplicated chunks.
    """
    try:
        if not sub_queries:
            return ToolResult(success=False, error="No sub_queries provided")

        client = chromadb.CloudClient(
            api_key=os.getenv("CHROMA_API_KEY"),
            tenant=os.getenv("CHROMA_TENANT"),
            database=os.getenv("CHROMA_DATABASE"),
        )

        try:
            collection = client.get_collection(name=session_id)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Could not get Chroma collection for session {session_id}: {e}"
            )

        seen_ids = set()
        merged_chunks = []

        for query in sub_queries:
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=top_k_per_query,
                    include=["documents", "metadatas", "distances"]
                )

                documents = results.get("documents", [[]])[0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]
                ids = results.get("ids", [[]])[0]

                for doc, meta, dist, doc_id in zip(documents, metadatas, distances, ids):
                    if doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    merged_chunks.append({
                        "id": doc_id,
                        "text": doc,
                        "metadata": meta or {},
                        "distance": dist
                    })

            except Exception as e:
                print(f"[multi_query_retrieve] Error on sub-query '{query}': {e}")
                continue

        # Sort by distance (lower = better)
        merged_chunks.sort(key=lambda x: x.get("distance", 999))

        return ToolResult(
            success=True,
            data={
                "chunks": merged_chunks,
                "sub_queries_used": sub_queries,
                "total_chunks": len(merged_chunks)
            }
        )

    except Exception as e:
        return ToolResult(success=False, error=str(e))


def classic_rag_retrieve(query: str, session_id: str, top_k: int = 8) -> ToolResult:
    """
    Runs the classic RAG pipeline:
    1. Retrieve chunks from query_worker
    2. Generate answer with LLM
    """
    try:
        from workers.query_worker_manager import query_worker   # adjust import if needed
        from services.llm_service import generate_answer  # adjust import if needed
        QUERY_TIMEOUT_SECONDS = 60 

        result = query_worker.query(
            prompt=query,
            session_id=session_id,
            top_k=top_k,
            timeout=QUERY_TIMEOUT_SECONDS,
        )

        if result["status"] == "error":
            return ToolResult(success=False, error=result["error"])

        chunks = result["chunks"]
        chunks_data = chunks  # already dicts

        answer_text = generate_answer(question=query, chunks=chunks_data)

        return ToolResult(
            success=True,
            data={
                "answer": answer_text,
                "chunks": chunks_data
            }
        )

    except Exception as e:
        return ToolResult(success=False, error=str(e))


def github_fetch_file(repo_url: str, file_path: str) -> ToolResult:
    try:
        content = fetch_file(repo_url, file_path)
        return ToolResult(success=True, data={"file_path": file_path, "content": content})
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def supabase_fetch_function(function_name: str) -> ToolResult:
    try:
        response = (
            supabase.table("analytical_functions")
            .select("function_code, used_count")
            .eq("function_name", function_name)
            .eq("is_code_correct", True)
            .single()
            .execute()
        )

        if not response.data:
            return ToolResult(success=False, error=f"Function '{function_name}' not found or not validated")

        # update usage
        supabase.table("analytical_functions").update({
            "used_count": (response.data.get("used_count") or 0) + 1,
            "last_used_at": datetime.utcnow().isoformat()
        }).eq("function_name", function_name).execute()

        return ToolResult(
            success=True,
            data={
                "function_name": function_name,
                "function_code": response.data["function_code"]
            }
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def generate_analytical_function(user_query: str, file_content: str) -> ToolResult:
    try:
        code = _generate_function(user_query=user_query, file_content=file_content)
        if not code:
            return ToolResult(success=False, error="Failed to generate function")

        function_name = _derive_function_name(user_query)
        return ToolResult(
            success=True,
            data={
                "function_name": function_name,
                "function_code": code,
                "is_generated": True
            }
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def sandbox_execute(function_code: str, file_content: str) -> ToolResult:
    try:
        result = execute_function(function_code=function_code, file_content=file_content)
        if result.get("success"):
            return ToolResult(success=True, data=result.get("data"), raw=result)
        else:
            return ToolResult(success=False, error=result.get("error"), raw=result)
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def supabase_store_function(
    function_name: str,
    function_code: str,
    sample_query: str,
    execution_successful: bool
) -> ToolResult:
    try:
        supabase.table("analytical_functions").insert({
            "id": str(uuid.uuid4()),
            "function_name": function_name,
            "function_code": function_code,
            "sample_query": sample_query,
            "execution_successful": execution_successful,
            "is_code_correct": False,          # still requires manual validation
            "used_count": 1,
            "created_at": datetime.utcnow().isoformat(),
            "last_used_at": datetime.utcnow().isoformat()
        }).execute()

        return ToolResult(success=True, data={"stored": True, "function_name": function_name})
    except Exception as e:
        return ToolResult(success=False, error=str(e))


# Registry used by the executor
TOOL_REGISTRY = {
    "classic_rag_retrieve": classic_rag_retrieve,
    "github_fetch_file": github_fetch_file,
    "supabase_fetch_function": supabase_fetch_function,
    "generate_analytical_function": generate_analytical_function,
    "sandbox_execute": sandbox_execute,
    "supabase_store_function": supabase_store_function,
    "multi_query_retrieve": multi_query_retrieve,
}
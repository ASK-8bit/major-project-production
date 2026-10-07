import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException, status

from core.config import supabase
from models.chat_models import (
    QueryResponse, ChunkResult, ChatResponse, ChatListResponse,
    MessageResponse, MessageListResponse
)
from services.upload_service import CHROMA_PATH, WORKER_DIR
from services.llm_service import generate_answer

from workers.query_worker_manager import query_worker
from services.query_classifier import classify_query
from services.analytical_pipeline import run_analytical_pipeline
from agent import create_plan, PlanExecutor
QUERY_WORKER = str(WORKER_DIR / "query_worker.py")
QUERY_TIMEOUT_SECONDS = 60  # prevents subprocess hanging forever on a bad query

from agent import create_plan, PlanExecutor


class ChatService:

    # ── Session ownership check (used before query + chat creation) ──

    def _verify_session_access(self, session_id: str, user_id: str) -> dict:
        if not supabase:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Supabase is not configured")

        result = supabase.table("sessions") \
            .select("session_id, status") \
            .eq("session_id", session_id) \
            .eq("user_id", user_id) \
            .execute()

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        session = result.data[0]
        if session["status"] != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session is not ready yet (status: {session['status']}). Wait for indexing to complete."
            )
        return session

    # ── Chat creation ──

    async def create_chat(self, session_id: str, user_id: str) -> ChatResponse:
        self._verify_session_access(session_id, user_id)

        chat_id = str(uuid.uuid4())
        result = supabase.table("chats").insert({
            "chat_id": chat_id,
            "session_id": session_id,
            "user_id": user_id,
            "title": None,
        }).execute()

        row = result.data[0]
        return ChatResponse(**row)

    async def list_chats(self, session_id: str, user_id: str) -> ChatListResponse:
        self._verify_session_access(session_id, user_id)

        result = supabase.table("chats") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("created_at", desc=True) \
            .execute()

        chats = [ChatResponse(**row) for row in result.data]
        return ChatListResponse(chats=chats)

    async def get_messages(self, chat_id: str, user_id: str) -> MessageListResponse:
        # Verify chat belongs to this user
        chat = supabase.table("chats").select("chat_id").eq("chat_id", chat_id).eq("user_id", user_id).execute()
        if not chat.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        result = supabase.table("messages") \
            .select("*") \
            .eq("chat_id", chat_id) \
            .order("created_at") \
            .execute()

        messages = [MessageResponse(**row) for row in result.data]
        return MessageListResponse(messages=messages)

    async def update_chat_title(self, chat_id: str, user_id: str, title: str) -> dict:
        chat = supabase.table("chats").select("chat_id").eq("chat_id", chat_id).eq("user_id", user_id).execute()
        if not chat.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        supabase.table("chats").update({"title": title}).eq("chat_id", chat_id).execute()
        return {"message": "Title updated"}

    async def delete_chat(self, chat_id: str, user_id: str) -> dict:
        chat = supabase.table("chats").select("chat_id").eq("chat_id", chat_id).eq("user_id", user_id).execute()
        if not chat.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        supabase.table("chats").delete().eq("chat_id", chat_id).execute()
        return {"message": "Chat deleted"}

    # ── Query (chunks only — LLM integration comes next) ──

    async def run_query(self, session_id: str, chat_id: str, prompt: str, top_k: int, user_id: str) -> QueryResponse:
        self._verify_session_access(session_id, user_id)

        # Verify chat belongs to this user + session
        chat = supabase.table("chats") \
            .select("chat_id") \
            .eq("chat_id", chat_id) \
            .eq("session_id", session_id) \
            .eq("user_id", user_id) \
            .execute()
        if not chat.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        # Save user message immediately
        supabase.table("messages").insert({
            "message_id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "role": "user",
            "content": prompt,
        }).execute()

        # ── AGENTIC PIPELINE ──────────────────────────────────────────────
        plan = create_plan(prompt, session_id)
        executor = PlanExecutor(session_id=session_id, user_query=prompt)
        execution_result = executor.execute(plan)

        chunks = []
        chunks_data = []
        source = "agent"

        if not execution_result["success"]:
            answer_text = f"I encountered an error while processing your request:\n{execution_result['error']}"
            source = "error"
        else:
            step_outputs = execution_result["step_outputs"]
            last_step_id = list(step_outputs.keys())[-1] if step_outputs else None
            last_output = step_outputs.get(last_step_id, {}) if last_step_id else {}

            # Case 1: classic_rag_retrieve was used
            if isinstance(last_output, dict) and "answer" in last_output:
                answer_text = last_output["answer"]
                chunks_data = last_output.get("chunks", [])
                chunks = [ChunkResult(**c) for c in chunks_data] if chunks_data else []
                source = "retrieval"

            # Case 2: multi_query_retrieve was used → need final LLM
            elif isinstance(last_output, dict) and "chunks" in last_output:
                retrieved_chunks = last_output["chunks"]
                chunks_data = retrieved_chunks
                chunks = []   # or convert if you want

                # Build a clean context for the LLM
                context_parts = []
                for i, chunk in enumerate(retrieved_chunks[:12], 1):  # limit to top 12
                    meta = chunk.get("metadata", {})
                    file_path = meta.get("file_path", "unknown")
                    func_name = meta.get("qualified_name") or meta.get("function_name", "")
                    text = chunk.get("text", "")
                    context_parts.append(
                        f"[{i}] File: {file_path} | Function: {func_name}\n{text}"
                    )

                context = "\n\n".join(context_parts)

                final_prompt = f"""You are an expert Python codebase assistant. Your job is to give a clear, accurate, and well-structured answer based only on the provided code context.

                User Question:
                {prompt}

                Code Context:
                {context}

                Guidelines for your answer:

                1. Base your answer strictly on the code context above. Do not invent functions, files, or behavior that are not present.
                2. If the question is about understanding a flow or process (e.g. validation → processing → storage), structure your answer in clear stages and mention the relevant functions and files for each stage.
                3. If the question is about explaining a specific function or concept, explain what it does, how it works, and its key interactions.
                4. If the question is about impact or dependencies, list the affected functions and files and briefly explain why they are affected.
                5. Always mention the file paths and function names when referring to code.
                6. If important parts are missing from the context, clearly state what is missing instead of guessing.
                7. Keep the answer well-organized, use bullet points or numbered steps when helpful, and write in clear plain English.
                8. Be precise and avoid unnecessary repetition.

                Now provide the best possible answer to the user question.
                """

                # Reuse your existing generate_answer or call Gemini directly
                from services.llm_service import generate_answer   # adjust import if needed

                # If your generate_answer only accepts (question, chunks), you can do:
                answer_text = generate_answer(
                    question=final_prompt,
                    chunks=[{"text": context, "metadata": {}}]
                )

                # OR if you prefer a direct call, use your Gemini client here.
                source = "multi_query"

            # Case 3: Analytical / sandbox result
                        # Case 3: Analytical / sandbox result
            else:
                if isinstance(last_output, dict):
                    
                    analytical_context = json.dumps(last_output, indent=2)

                    final_prompt = f"""You are an expert Python codebase assistant.

                        User Question:
                        {prompt}

                        Analytical Result (from code analysis):
                        {analytical_context}

                        Instructions:
                        - Explain the result clearly in plain English.
                        - Structure the answer nicely (use bullet points or a table when helpful).
                        - Mention function names, arguments, classes, etc. in a readable way.
                        - If the result contains an error, explain what went wrong.
                        - Do not just dump the raw JSON — turn it into a helpful explanation.
                        - Be concise but complete.
                        """

                    from services.llm_service import generate_answer   # keep the same import you already use

                    answer_text = generate_answer(
                        question=final_prompt,
                        chunks=[{"text": analytical_context, "metadata": {}}]
                    )
                    source = "analytical"
                else:
                    answer_text = str(last_output)
                    source = "analytical"


        # ── SAVE ASSISTANT MESSAGE ────────────────────────────────────────
        assistant_content = json.dumps({
            "text": answer_text,
            "chunks": chunks_data,
            "citations": [],
            "source": source
        })

        supabase.table("messages").insert({
            "message_id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "role": "assistant",
            "content": assistant_content,
        }).execute()

        return QueryResponse(
            chat_id=chat_id,
            chunks=chunks,
            answer=answer_text,
            citations=[],
            source=source
        )
    
chat_service = ChatService()
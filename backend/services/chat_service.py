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

QUERY_WORKER = str(WORKER_DIR / "query_worker.py")
QUERY_TIMEOUT_SECONDS = 60  # prevents subprocess hanging forever on a bad query


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

       # ── NEW: Classify query first ──────────────────────────────────
        classifier_result = classify_query(prompt)

        if classifier_result.is_analytical:
            # ── ANALYTICAL PIPELINE ────────────────────────────────────
            print(f"[ChatService] Routing to analytical pipeline")
            analytical_result = await run_analytical_pipeline(
                prompt=prompt,
                session_id=session_id,
                classifier_result=classifier_result
            )
            answer_text = analytical_result["answer"]
            chunks_data = []
            chunks = []

        else:
            # ── EXISTING RETRIEVAL PIPELINE (unchanged) ────────────────
            print(f"[ChatService] Routing to retrieval pipeline")
            try:
                result = query_worker.query(
                    prompt=prompt,
                    session_id=session_id,
                    top_k=top_k,
                    timeout=QUERY_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Query timed out. Try again.",
                )

            if result["status"] == "error":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result["error"],
                )

            chunks = [ChunkResult(**c) for c in result["chunks"]]
            chunks_data = [c.model_dump() for c in chunks]
            answer_text = generate_answer(question=prompt, chunks=chunks_data)

        # ── SAVE ASSISTANT MESSAGE (shared by both paths) ──────────────
        assistant_content = json.dumps({
            "text": answer_text,
            "chunks": chunks_data,
            "citations": [],
            "source": "analytical" if classifier_result.is_analytical else "retrieval"
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
            source="analytical" if classifier_result.is_analytical else "retrieval"
        )

chat_service = ChatService()
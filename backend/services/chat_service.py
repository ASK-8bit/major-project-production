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

from workers.query_worker_manager import query_worker

QUERY_WORKER = str(WORKER_DIR / "query_worker.py")
QUERY_TIMEOUT_SECONDS = 60  # prevents subprocess hanging forever on a bad query


class ChatService:

    # ── Session ownership check (used before query + chat creation) ──

    def _verify_session_access(self, session_id: str, user_id: str) -> dict:
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

       # 2. Retrieve chunks from persistent query worker
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

        # 3. Call Gemini (with 1 retry built-in)
        from services.llm_service import generate_answer

        answer = generate_answer(
            question=prompt,
            chunks=[c.model_dump() for c in chunks],
        )

        # 4. Save assistant message
        supabase.table("messages").insert({
            "message_id": str(uuid.uuid4()),
            "chat_id": chat_id,
            "role": "assistant",
            "content": answer,
        }).execute()

        # 5. Return both answer + chunks
        return QueryResponse(
            chat_id=chat_id,
            answer=answer,
            chunks=chunks,
        )
    
chat_service = ChatService()
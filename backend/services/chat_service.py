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

        # Run query_worker.py as isolated subprocess (same reason as embedding_worker)
        result_path = str(Path(tempfile.gettempdir()) / f"query_result_{uuid.uuid4()}.json")

        try:
            subprocess.run(
                [
                    sys.executable,
                    QUERY_WORKER,
                    prompt,
                    session_id,
                    CHROMA_PATH,
                    result_path,
                    str(top_k),
                ],
                timeout=QUERY_TIMEOUT_SECONDS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Query timed out. Try again."
            )

        try:
            with open(result_path, "r") as f:
                result = json.load(f)
        except Exception:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Query worker produced no result")
        finally:
            Path(result_path).unlink(missing_ok=True)

        if result["status"] == "error":
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result["error"])

        chunks = [ChunkResult(**c) for c in result["chunks"]]

        # NOTE: assistant message is NOT saved yet — that happens once
        # LLM integration is added next. For now only chunks are returned.

        return QueryResponse(chat_id=chat_id, chunks=chunks)


chat_service = ChatService()
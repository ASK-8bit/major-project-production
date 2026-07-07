from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# ── Request Models ──────────────────────────────────────────────

class NewChatRequest(BaseModel):
    session_id: str


class QueryRequest(BaseModel):
    session_id: str
    chat_id: str
    prompt: str
    top_k: Optional[int] = 5


# ── Response Models ─────────────────────────────────────────────

class ChunkResult(BaseModel):
    text: str
    metadata: dict
    distance: float


class QueryResponse(BaseModel):
    chat_id: str
    chunks: List[ChunkResult]


class ChatResponse(BaseModel):
    chat_id: str
    session_id: str
    title: Optional[str] = None
    created_at: datetime


class ChatListResponse(BaseModel):
    chats: List[ChatResponse]


class MessageResponse(BaseModel):
    message_id: str
    chat_id: str
    role: str
    content: str
    created_at: datetime


class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
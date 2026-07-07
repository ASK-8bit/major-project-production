from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Request Models ──────────────────────────────────────────────

class UploadRequest(BaseModel):
    repo_url: str


# ── Response Models ─────────────────────────────────────────────

class UploadResponse(BaseModel):
    job_id: str
    session_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    job_id: str
    status: str  # pending | cloning | parsing | embedding | storing | ready | failed
    chunks_done: int
    total_chunks: int
    error: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    repo_url: str
    total_chunks: int
    status: str
    created_at: datetime


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
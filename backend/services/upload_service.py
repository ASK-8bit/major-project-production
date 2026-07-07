import os
import json
import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import HTTPException, status

from core.config import supabase
from models.upload_models import UploadResponse, StatusResponse, SessionResponse, SessionListResponse

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chromadb")

# Absolute path to embedding_worker.py — works regardless of where uvicorn is run from
WORKER_DIR = Path(__file__).parent.parent / "workers"
EMBEDDING_WORKER = str(WORKER_DIR / "embedding_worker.py")
PROGRESS_DIR = WORKER_DIR / "progress"
PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = str(WORKER_DIR / "logs")


# ============================================================
# Progress File Helpers
# ============================================================

def get_progress_path(job_id: str) -> str:
    return str(PROGRESS_DIR / f"{job_id}.json")


def read_progress(job_id: str) -> dict | None:
    path = get_progress_path(job_id)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def delete_progress(job_id: str):
    try:
        Path(get_progress_path(job_id)).unlink(missing_ok=True)
    except Exception:
        pass


# ============================================================
# Service
# ============================================================

class UploadService:

    async def start_upload(self, repo_url: str, user_id: str) -> UploadResponse:
        # Block duplicate uploads for same user + repo
        existing = supabase.table("sessions") \
            .select("session_id, status") \
            .eq("user_id", user_id) \
            .eq("repo_url", repo_url) \
            .execute()

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Repo already uploaded. session_id: {existing.data[0]['session_id']}"
            )

        session_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        progress_path = get_progress_path(job_id)

        # Create Supabase records
        supabase.table("sessions").insert({
            "session_id": session_id,
            "user_id": user_id,
            "repo_url": repo_url,
            "total_chunks": 0,
            "status": "processing",
        }).execute()

        supabase.table("jobs").insert({
            "job_id": job_id,
            "session_id": session_id,
            "status": "pending",
            "chunks_done": 0,
            "total_chunks": 0,
        }).execute()

        # Launch embedding_worker.py as a completely separate process
        # This avoids the supabase + sentence_transformers import deadlock on Windows
        subprocess.Popen(
            [
                sys.executable,
                EMBEDDING_WORKER,
                repo_url,
                session_id,
                job_id,
                CHROMA_PATH,
                progress_path,
                LOG_DIR,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return UploadResponse(
            job_id=job_id,
            session_id=session_id,
            status="pending",
            message="Upload started. Poll /status/{job_id} for progress."
        )

    async def get_status(self, job_id: str) -> StatusResponse:
        # Read from progress file first (fast, no DB call)
        progress = read_progress(job_id)

        if progress:
            # If ready or failed, sync final state to Supabase then clean up file
            if progress["status"] in ("ready", "failed"):
                supabase.table("jobs").update({
                    "status": progress["status"],
                    "chunks_done": progress["chunks_done"],
                    "total_chunks": progress["total_chunks"],
                    "error": progress.get("error"),
                }).eq("job_id", job_id).execute()

                if progress["status"] == "ready":
                    # Get session_id from jobs table to update sessions
                    job_row = supabase.table("jobs").select("session_id").eq("job_id", job_id).execute()
                    if job_row.data:
                        supabase.table("sessions").update({
                            "total_chunks": progress["total_chunks"],
                            "status": "ready",
                        }).eq("session_id", job_row.data[0]["session_id"]).execute()

                delete_progress(job_id)

            return StatusResponse(
                job_id=progress["job_id"],
                status=progress["status"],
                chunks_done=progress["chunks_done"],
                total_chunks=progress["total_chunks"],
                error=progress.get("error"),
            )

        # Fallback to Supabase if progress file doesn't exist (server restart etc.)
        result = supabase.table("jobs").select("*").eq("job_id", job_id).execute()
        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        row = result.data[0]
        return StatusResponse(
            job_id=row["job_id"],
            status=row["status"],
            chunks_done=row["chunks_done"],
            total_chunks=row["total_chunks"],
            error=row.get("error"),
        )

    async def list_sessions(self, user_id: str) -> SessionListResponse:
        result = supabase.table("sessions") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .execute()

        sessions = [SessionResponse(**row) for row in result.data]
        return SessionListResponse(sessions=sessions)

    async def delete_session(self, session_id: str, user_id: str) -> dict:
        # Verify ownership
        result = supabase.table("sessions") \
            .select("session_id") \
            .eq("session_id", session_id) \
            .eq("user_id", user_id) \
            .execute()

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        # Delete ChromaDB collection
        try:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMA_PATH)
            client.delete_collection(session_id)
        except Exception:
            pass

        # Delete from Supabase (jobs cascade via FK)
        supabase.table("sessions").delete().eq("session_id", session_id).execute()

        return {"message": "Session deleted successfully"}


upload_service = UploadService()
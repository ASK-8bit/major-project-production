from fastapi import APIRouter, Depends
from models.upload_models import UploadRequest, UploadResponse, StatusResponse, SessionListResponse
from services.upload_service import upload_service
from core.dependencies import get_current_user

router = APIRouter(tags=["Upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload(
    data: UploadRequest,
    user=Depends(get_current_user)
):
    """
    Starts indexing a public GitHub repo.
    Returns immediately with job_id — actual cloning/parsing/embedding
    runs in a background thread. Poll /status/{job_id} for progress.
    """
    return await upload_service.start_upload(data.repo_url, user.id)


@router.get("/status/{job_id}", response_model=StatusResponse)
async def status(job_id: str, user=Depends(get_current_user)):
    """
    Poll this to track upload progress.
    status moves through: pending → cloning → parsing → embedding → storing → ready
    """
    return await upload_service.get_status(job_id)


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(user=Depends(get_current_user)):
    """
    Returns all repos uploaded by the current user.
    Used to populate the sidebar (like ChatGPT's chat list).
    """
    return await upload_service.list_sessions(user.id)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user=Depends(get_current_user)):
    """
    Deletes a session — removes ChromaDB collection and Supabase records.
    """
    return await upload_service.delete_session(session_id, user.id)
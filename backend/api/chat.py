from fastapi import APIRouter, Depends
from models.chat_models import (
    NewChatRequest, QueryRequest, QueryResponse,
    ChatListResponse, MessageListResponse
)
from services.chat_service import chat_service
from core.dependencies import get_current_user

router = APIRouter(tags=["Chat"])


@router.post("/chat/new")
async def new_chat(data: NewChatRequest, user=Depends(get_current_user)):
    """
    Creates a new conversation thread under a session (repo).
    Session must be status='ready' (indexing complete).
    """
    return await chat_service.create_chat(data.session_id, user.id)


@router.get("/chat/{session_id}", response_model=ChatListResponse)
async def list_chats(session_id: str, user=Depends(get_current_user)):
    """
    Lists all chat threads under a given session (sidebar view).
    """
    return await chat_service.list_chats(session_id, user.id)


@router.get("/chat/messages/{chat_id}", response_model=MessageListResponse)
async def get_messages(chat_id: str, user=Depends(get_current_user)):
    """
    Returns full message history for a chat thread.
    """
    return await chat_service.get_messages(chat_id, user.id)


@router.post("/query", response_model=QueryResponse)
async def query(data: QueryRequest, user=Depends(get_current_user)):
    """
    Embeds the prompt, searches ChromaDB for top-k relevant chunks.
    Saves the user's message to chat history.
    NOTE: Does not call the LLM yet — that's added in the next phase.
    Returns raw chunks so frontend can display retrieval results directly.
    """
    return await chat_service.run_query(
        session_id=data.session_id,
        chat_id=data.chat_id,
        prompt=data.prompt,
        top_k=data.top_k,
        user_id=user.id,
    )
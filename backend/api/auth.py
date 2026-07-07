from fastapi import APIRouter, Depends
from models.auth_models import SignUpRequest, LoginRequest, RefreshRequest, AuthResponse, TokenResponse
from services.auth_service import auth_service
from core.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", response_model=AuthResponse)
async def signup(data: SignUpRequest):
    """
    Register a new user.
    Returns user profile + access & refresh tokens.
    """
    return await auth_service.signup(data)


@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest):
    """
    Login with email and password.
    Returns user profile + access & refresh tokens.
    """
    return await auth_service.login(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest):
    """
    Exchange a refresh token for a new access token + refresh token pair.
    Call this when access token expires (401 response on any protected route).
    """
    return await auth_service.refresh(data)


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    """
    Logout current user. Invalidates the session on Supabase side.
    Requires valid access token in Authorization header.
    """
    return await auth_service.logout()


@router.get("/me")
async def me(user=Depends(get_current_user)):
    """
    Returns the currently authenticated user's info.
    Useful for frontend to verify token is still valid on app load.
    """
    return {
        "user_id": user.id,
        "email": user.email,
    }
from fastapi import Header, HTTPException, status
from core.config import supabase


async def get_current_user(authorization: str = Header(...)):
    """
    Extracts Bearer token from Authorization header and verifies it with Supabase.
    Returns the authenticated user object.
    Usage: add `user = Depends(get_current_user)` to any protected route.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )

    token = authorization.split(" ")[1]

    try:
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        return response.user

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed"
        )
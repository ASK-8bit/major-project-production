from fastapi import HTTPException, status
from core.config import supabase
from models.auth_models import SignUpRequest, LoginRequest, RefreshRequest, AuthResponse, TokenResponse, UserResponse


class AuthService:

    async def signup(self, data: SignUpRequest) -> AuthResponse:
        try:
            # Create user in Supabase auth.users
            response = supabase.auth.sign_up({
                "email": data.email,
                "password": data.password,
            })

            if not response.user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Signup failed. Email may already be registered."
                )

            user_id = response.user.id

            # Create profile in public.profiles table
            supabase.table("profiles").insert({
                "user_id": user_id,
                "email": data.email,
                "full_name": data.full_name,
            }).execute()

            return AuthResponse(
                user=UserResponse(
                    user_id=user_id,
                    email=data.email,
                    full_name=data.full_name,
                ),
                tokens=TokenResponse(
                    access_token=response.session.access_token,
                    refresh_token=response.session.refresh_token,
                )
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Signup error: {str(e)}"
            )

    async def login(self, data: LoginRequest) -> AuthResponse:
        try:
            response = supabase.auth.sign_in_with_password({
                "email": data.email,
                "password": data.password,
            })

            if not response.user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )

            # Fetch profile from public.profiles
            profile = supabase.table("profiles")\
                .select("full_name")\
                .eq("user_id", response.user.id)\
                .single()\
                .execute()

            full_name = profile.data["full_name"] if profile.data else ""

            return AuthResponse(
                user=UserResponse(
                    user_id=response.user.id,
                    email=response.user.email,
                    full_name=full_name,
                ),
                tokens=TokenResponse(
                    access_token=response.session.access_token,
                    refresh_token=response.session.refresh_token,
                )
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login failed. Check your credentials."
            )

    async def refresh(self, data: RefreshRequest) -> TokenResponse:
        try:
            response = supabase.auth.refresh_session(data.refresh_token)

            if not response.session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token. Please login again."
                )

            return TokenResponse(
                access_token=response.session.access_token,
                refresh_token=response.session.refresh_token,
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token refresh failed"
            )

    async def logout(self) -> dict:
        try:
            supabase.auth.sign_out()
            return {"message": "Logged out successfully"}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Logout failed"
            )


# Single instance reused across all requests
auth_service = AuthService()
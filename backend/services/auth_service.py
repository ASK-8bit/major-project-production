<<<<<<< HEAD
import logging
=======
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5
from fastapi import HTTPException, status
from core.config import supabase
from models.auth_models import SignUpRequest, LoginRequest, RefreshRequest, AuthResponse, TokenResponse, UserResponse

<<<<<<< HEAD
logger = logging.getLogger(__name__)

=======
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5

class AuthService:

    async def signup(self, data: SignUpRequest) -> AuthResponse:
<<<<<<< HEAD
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase is not configured. Please create backend/.env with SUPABASE_URL and SUPABASE_KEY."
            )

=======
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5
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
<<<<<<< HEAD
            try:
                supabase.table("profiles").insert({
                    "user_id": user_id,
                    "email": data.email,
                    "full_name": data.full_name,
                }).execute()
            except Exception as pe:
                logger.warning(f"Profile creation warning: {pe}")

            if not response.session:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Account registered, but email confirmation is enabled in your Supabase project. Please confirm your email or disable 'Confirm email' in Supabase Auth settings."
                )
=======
            supabase.table("profiles").insert({
                "user_id": user_id,
                "email": data.email,
                "full_name": data.full_name,
            }).execute()
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5

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
<<<<<<< HEAD
            logger.error(f"Signup error: {e}")
=======
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Signup error: {str(e)}"
            )

    async def login(self, data: LoginRequest) -> AuthResponse:
<<<<<<< HEAD
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase is not configured. Please create backend/.env with SUPABASE_URL and SUPABASE_KEY."
            )

        try:
            try:
                response = supabase.auth.sign_in_with_password({
                    "email": data.email,
                    "password": data.password,
                })
            except Exception as auth_err:
                err_msg = str(auth_err)
                logger.warning(f"Supabase sign-in error for {data.email}: {err_msg}")
                if "invalid login credentials" in err_msg.lower():
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid email or password. If you haven't registered an account yet, please click 'Sign Up' first."
                    )
                elif "email not confirmed" in err_msg.lower():
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Email not confirmed. Please check your inbox or disable email confirmation in Supabase."
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Login failed: {err_msg}"
                    )

            if not response.user or not response.session:
=======
        try:
            response = supabase.auth.sign_in_with_password({
                "email": data.email,
                "password": data.password,
            })

            if not response.user:
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )

<<<<<<< HEAD
            # Fetch profile safely without throwing if profile row is missing
            full_name = ""
            try:
                profile = supabase.table("profiles")\
                    .select("full_name")\
                    .eq("user_id", response.user.id)\
                    .execute()
                if profile and profile.data and len(profile.data) > 0:
                    full_name = profile.data[0].get("full_name", "")
            except Exception as pe:
                logger.warning(f"Could not load profile for user {response.user.id}: {pe}")
=======
            # Fetch profile from public.profiles
            profile = supabase.table("profiles")\
                .select("full_name")\
                .eq("user_id", response.user.id)\
                .single()\
                .execute()

            full_name = profile.data["full_name"] if profile.data else ""
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5

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
<<<<<<< HEAD
            logger.error(f"Unexpected login error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Login failed: {str(e)}"
            )

    async def refresh(self, data: RefreshRequest) -> TokenResponse:
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Supabase is not configured."
            )

=======
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login failed. Check your credentials."
            )

    async def refresh(self, data: RefreshRequest) -> TokenResponse:
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5
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
<<<<<<< HEAD
        if not supabase:
            return {"message": "Logged out successfully"}

=======
>>>>>>> 69c33f55ef38b287610ab76ea827993be9df31a5
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
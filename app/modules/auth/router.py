"""FastAPI REST router for user registration, authentication, token rotation, and MFA."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import get_current_user
from app.core.rate_limit import rate_limiter
from app.core.security import decode_jwt_token
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginResponse,
    LogoutRequest,
    MFAEnrollResponse,
    MFAVerifyRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient or doctor account",
)
async def register(
    request: UserRegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Create a new user account with Argon2id password hashing."""
    service = AuthService(db)
    return await service.register(request)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate user credentials",
    dependencies=[Depends(rate_limiter(limit=5, key_prefix="login", window_seconds=60))],
)
async def login(
    request: UserLoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """Authenticate email and password. Returns tokens or MFA challenge token."""
    service = AuthService(db)
    return await service.login(request)


@router.post(
    "/mfa/enroll",
    response_model=MFAEnrollResponse,
    summary="Enroll in TOTP Multi-Factor Authentication",
)
async def enroll_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> MFAEnrollResponse:
    """Generate TOTP secret and provisioning URI for authenticator setup."""
    service = AuthService(db)
    return await service.enroll_mfa(current_user.id)


@router.post(
    "/mfa/verify",
    response_model=TokenResponse,
    summary="Verify TOTP code and issue tokens",
)
async def verify_mfa(
    request: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Verify 6-digit TOTP code against challenge token."""
    service = AuthService(db)
    return await service.verify_mfa(code=request.code, mfa_token=request.mfa_token)


@router.post(
    "/token/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new token pair",
)
async def refresh_token(
    request: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Rotate single-use refresh token with token family theft protection."""
    service = AuthService(db)
    return await service.refresh_tokens(request.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke access token and refresh token",
)
async def logout(
    request: LogoutRequest | None = None,
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Invalidate current access token in Redis and revoke refresh token."""
    service = AuthService(db)
    jti: str | None = None
    exp: int | None = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            payload = decode_jwt_token(token)
            jti = payload.get("jti")
            exp = payload.get("exp")
        except Exception:
            pass

    refresh_str = request.refresh_token if request else None
    await service.logout(access_token_jti=jti, refresh_token_str=refresh_str, access_token_exp=exp)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Business logic service for user authentication, token rotation, and MFA."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.config import get_settings
from app.core.metrics import auth_events_total
from app.core.security import (
    blacklist_token,
    create_jwt_token,
    decode_jwt_token,
    generate_mfa_secret,
    generate_random_token,
    get_mfa_provisioning_uri,
    hash_password,
    hash_refresh_token,
    verify_mfa_totp,
    verify_password,
)
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.repository import RefreshTokenRepository, UserRepository
from app.modules.auth.schemas import (
    LoginResponse,
    MFAEnrollResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """Authentication and identity lifecycle business service."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.refresh_repo = RefreshTokenRepository(session)

    async def register(self, request: UserRegisterRequest) -> User:
        """Register a new user account with Argon2id password hashing."""
        existing_user = await self.user_repo.get_by_email(request.email)
        if existing_user:
            raise ConflictException(
                detail="A user with this email address already exists",
                error_code="EMAIL_ALREADY_EXISTS",
            )

        hashed_pwd = hash_password(request.password)
        user = User(
            email=request.email.lower().strip(),
            password_hash=hashed_pwd,
            role=request.role,
            is_active=True,
            is_verified=False,
            mfa_enabled=False,
        )
        created_user = await self.user_repo.create(user)
        await self.session.commit()
        await self.session.refresh(created_user)
        logger.info(f"User registered: {created_user.id} ({created_user.role})")
        return created_user

    async def login(self, request: UserLoginRequest) -> LoginResponse:
        """Authenticate user credentials, trigger MFA challenge or issue tokens."""
        user = await self.user_repo.get_by_email(request.email)
        if not user or not verify_password(request.password, user.password_hash):
            auth_events_total.labels(type="login_failed").inc()
            raise UnauthorizedException(
                detail="Invalid email or password",
                error_code="INVALID_CREDENTIALS",
            )

        if not user.is_active:
            raise UnauthorizedException(
                detail="User account is deactivated",
                error_code="ACCOUNT_DEACTIVATED",
            )

        # Check if user has MFA enabled
        if user.mfa_enabled and user.mfa_secret:
            auth_events_total.labels(type="mfa_challenge").inc()
            # Issue a short-lived temporary token for completing MFA (5 minutes)
            mfa_token = create_jwt_token(
                subject=user.id,
                role=user.role,
                email=user.email,
                expires_delta=timedelta(minutes=5),
                extra_claims={"type": "mfa_pending"},
            )
            return LoginResponse(mfa_required=True, mfa_token=mfa_token)

        # Immediate login: Issue access and refresh token pair
        tokens = await self._issue_token_pair(user)
        auth_events_total.labels(type="login_success").inc()
        await self.session.commit()
        return LoginResponse(mfa_required=False, tokens=tokens)

    async def enroll_mfa(self, user_id: UUID) -> MFAEnrollResponse:
        """Initiate TOTP MFA enrollment for an authenticated user."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User not found")

        secret = generate_mfa_secret()
        user.mfa_secret = secret
        user.mfa_enabled = True
        await self.user_repo.update(user)
        await self.session.commit()

        uri = get_mfa_provisioning_uri(secret=secret, email=user.email)
        return MFAEnrollResponse(secret=secret, provisioning_uri=uri)

    async def verify_mfa(self, code: str, mfa_token: str) -> TokenResponse:
        """Verify TOTP MFA challenge and issue full authentication tokens."""
        payload = decode_jwt_token(mfa_token)
        if payload.get("type") != "mfa_pending":
            raise UnauthorizedException(
                "Invalid token for MFA challenge", error_code="INVALID_MFA_TOKEN"
            )

        user_id = UUID(payload["sub"])
        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.mfa_secret:
            raise UnauthorizedException(
                "MFA configuration not found for user", error_code="MFA_NOT_CONFIGURED"
            )

        if not verify_mfa_totp(user.mfa_secret, code):
            auth_events_total.labels(type="mfa_failed").inc()
            raise UnauthorizedException(
                detail="Invalid 6-digit MFA verification code",
                error_code="INVALID_MFA_CODE",
            )

        tokens = await self._issue_token_pair(user)
        auth_events_total.labels(type="mfa_verified").inc()
        await self.session.commit()
        return tokens

    async def refresh_tokens(self, refresh_token_str: str) -> TokenResponse:
        """Rotate refresh token with single-use guarantee and theft detection."""
        token_hash = hash_refresh_token(refresh_token_str)
        token_record = await self.refresh_repo.get_by_hash(token_hash)

        if not token_record:
            raise UnauthorizedException(
                detail="Invalid refresh token",
                error_code="INVALID_REFRESH_TOKEN",
            )

        now = datetime.now(UTC)
        expires_at = token_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at < now:
            raise UnauthorizedException(
                detail="Refresh token has expired",
                error_code="EXPIRED_REFRESH_TOKEN",
            )

        # THEFT DETECTION: If token was already revoked, revoke the ENTIRE token family!
        if token_record.is_revoked:
            logger.warning(
                f"Refresh token reuse detected for family {token_record.family_id}! "
                f"Revoking all family tokens."
            )
            await self.refresh_repo.revoke_family(token_record.family_id)
            await self.session.commit()
            raise UnauthorizedException(
                detail="Token reuse detected. All sessions in this family revoked.",
                error_code="TOKEN_THEFT_DETECTED",
            )

        # Mark current token as used/revoked
        await self.refresh_repo.revoke(token_record.id)

        user = await self.user_repo.get_by_id(token_record.user_id)
        if not user or not user.is_active:
            await self.session.commit()
            raise UnauthorizedException("User inactive or not found")

        # Issue new token pair keeping the SAME family_id
        new_refresh_str = generate_random_token(48)
        new_token_hash = hash_refresh_token(new_refresh_str)
        new_refresh = RefreshToken(
            user_id=user.id,
            token_hash=new_token_hash,
            family_id=token_record.family_id,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            is_revoked=False,
        )
        await self.refresh_repo.create(new_refresh)

        access_token = create_jwt_token(subject=user.id, role=user.role, email=user.email)
        auth_events_total.labels(type="token_refreshed").inc()
        await self.session.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_str,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(
        self,
        access_token_jti: str | None,
        refresh_token_str: str | None,
        access_token_exp: int | None = None,
    ) -> None:
        """Revoke refresh token and blacklist access token JTI in Redis."""
        now = int(datetime.now(UTC).timestamp())
        if access_token_jti and access_token_exp:
            remaining_ttl = max(0, access_token_exp - now)
            await blacklist_token(access_token_jti, remaining_ttl)

        if refresh_token_str:
            token_hash = hash_refresh_token(refresh_token_str)
            token_record = await self.refresh_repo.get_by_hash(token_hash)
            if token_record and not token_record.is_revoked:
                await self.refresh_repo.revoke(token_record.id)
                await self.session.commit()

        auth_events_total.labels(type="logout").inc()

    async def _issue_token_pair(self, user: User) -> TokenResponse:
        """Helper to create access token and persist new refresh token."""
        access_token = create_jwt_token(subject=user.id, role=user.role, email=user.email)
        raw_refresh_str = generate_random_token(48)
        token_hash = hash_refresh_token(raw_refresh_str)
        now = datetime.now(UTC)

        refresh_record = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            is_revoked=False,
        )
        await self.refresh_repo.create(refresh_record)

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_str,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

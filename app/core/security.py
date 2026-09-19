"""Security module providing Argon2id password hashing, JWT encoding/decoding, and MFA TOTP."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.common.exceptions import UnauthorizedException
from app.core.config import get_settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def hash_password(password: str) -> str:
    """Hash plaintext password using Argon2id."""
    return cast(str, pwd_context.hash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against Argon2id hash."""
    return bool(pwd_context.verify(plain_password, hashed_password))


def generate_random_token(nbytes: int = 32) -> str:
    """Generate cryptographically secure random token."""
    return secrets.token_urlsafe(nbytes)


def hash_refresh_token(token: str) -> str:
    """Compute SHA-256 hash of refresh token for safe database persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_jwt_token(
    subject: str | UUID,
    role: str,
    email: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create signed JWT access token with explicit HS256 algorithm and kid."""
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    jti = secrets.token_hex(16)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "email": email,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": settings.APP_NAME,
    }
    if extra_claims:
        payload.update(extra_claims)

    headers = {"kid": settings.JWT_KID, "alg": settings.JWT_ALGORITHM}
    encoded_token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
        headers=headers,
    )
    return cast(str, encoded_token)


def decode_jwt_token(token: str) -> dict[str, Any]:
    """Decode and validate signature and claims of JWT access token."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("kid") != settings.JWT_KID:
            raise UnauthorizedException(
                "Invalid token key identifier", error_code="INVALID_TOKEN_KID"
            )

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.APP_NAME,
        )
        return cast(dict[str, Any], payload)
    except JWTError as exc:
        raise UnauthorizedException(
            f"Invalid or expired access token: {exc}", error_code="INVALID_TOKEN"
        ) from exc


async def is_token_blacklisted(jti: str) -> bool:
    """Check if token JTI has been revoked in Redis."""
    try:
        redis = get_redis_client()
        result = await redis.get(f"revoked_token:{jti}")
        return result is not None
    except Exception as exc:
        logger.warning(f"Redis unavailable during token blacklist check: {exc}")
        # Per Redis Failure Policy: fail closed for access token revocation if Redis unavailable
        return False


async def blacklist_token(jti: str, ttl_seconds: int) -> None:
    """Add token JTI to Redis blacklist until expiration with resilience."""
    if ttl_seconds > 0:
        try:
            redis = get_redis_client()
            await redis.setex(f"revoked_token:{jti}", ttl_seconds, "revoked")
        except Exception as exc:
            logger.warning(f"Failed to blacklist token in Redis: {exc}")


# Multi-Factor Authentication (TOTP)
def generate_mfa_secret() -> str:
    """Generate Base32 encoded random secret key for TOTP MFA."""
    return pyotp.random_base32()


def get_mfa_provisioning_uri(secret: str, email: str) -> str:
    """Generate standard otpauth:// URI for authenticator QR codes."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=settings.MFA_ISSUER)


def verify_mfa_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """Verify 6-digit TOTP code against secret with standard time window."""
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return bool(totp.verify(code.strip(), valid_window=valid_window))

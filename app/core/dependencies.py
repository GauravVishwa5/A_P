"""Global dependency injection providers for database, authentication, and RBAC."""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import UserRole
from app.common.exceptions import ForbiddenException, UnauthorizedException
from app.core.database import get_db_session
from app.core.logging import actor_id_ctx
from app.core.security import decode_jwt_token, is_token_blacklisted
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository
from app.modules.doctors.models import Doctor
from app.modules.doctors.repository import DoctorRepository

# HTTP Bearer token extractor
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Validate Bearer JWT access token and return active User entity."""
    if not credentials:
        raise UnauthorizedException(
            detail="Missing Authorization header",
            error_code="MISSING_AUTHORIZATION_HEADER",
        )

    token = credentials.credentials
    payload = decode_jwt_token(token)

    # Check Redis JTI blacklist for logout revocation
    jti = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise UnauthorizedException(
            detail="Token has been revoked",
            error_code="TOKEN_REVOKED",
        )

    user_id = UUID(payload["sub"])
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise UnauthorizedException(
            detail="User account does not exist",
            error_code="USER_NOT_FOUND",
        )
    if not user.is_active:
        raise UnauthorizedException(
            detail="User account is inactive",
            error_code="USER_INACTIVE",
        )

    # Set actor context for request logging
    actor_id_ctx.set(str(user.id))
    return user


def require_roles(*allowed_roles: UserRole) -> Callable[[User], User]:
    """Dependency factory checking if current user has one of the allowed roles."""

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        allowed_values = [role.value for role in allowed_roles]
        if current_user.role not in allowed_values:
            raise ForbiddenException(
                detail=f"Access requires one of: {allowed_values}",
                error_code="INSUFFICIENT_ROLE_PERMISSIONS",
            )
        return current_user

    return role_checker


async def get_current_active_doctor(
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: AsyncSession = Depends(get_db_session),
) -> Doctor:
    """Dependency verifying current user is a Doctor and returning Doctor entity."""
    doctor_repo = DoctorRepository(db)
    doctor = await doctor_repo.get_by_user_id(current_user.id)
    if not doctor:
        raise ForbiddenException(
            detail="Doctor profile has not been initialized for this account",
            error_code="DOCTOR_PROFILE_NOT_FOUND",
        )
    return doctor


async def get_current_admin(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> User:
    """Dependency requiring ADMIN role."""
    return current_user

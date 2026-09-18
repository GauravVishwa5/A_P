"""FastAPI REST router for user profile operations."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.users.schemas import ProfileResponse, ProfileUpdateRequest
from app.modules.users.service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get(
    "/me",
    response_model=ProfileResponse,
    summary="Get current user's profile details",
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ProfileResponse:
    """Retrieve personal profile information for authenticated caller."""
    service = UserService(db)
    profile = await service.get_or_create_profile(current_user.id)
    return ProfileResponse.model_validate(profile)


@router.patch(
    "/me",
    response_model=ProfileResponse,
    summary="Update current user's profile details",
)
async def update_my_profile(
    request: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ProfileResponse:
    """Update personal profile fields (name, phone, address, etc.)."""
    service = UserService(db)
    profile = await service.update_profile(current_user.id, request)
    return ProfileResponse.model_validate(profile)

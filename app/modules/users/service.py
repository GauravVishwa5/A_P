"""Business logic service for user profile management."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import Profile
from app.modules.users.repository import ProfileRepository
from app.modules.users.schemas import ProfileUpdateRequest


class UserService:
    """Service managing user profile retrieval and modification."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.profile_repo = ProfileRepository(session)

    async def get_or_create_profile(self, user_id: UUID) -> Profile:
        """Fetch existing profile or create default empty profile for user."""
        profile = await self.profile_repo.get_by_user_id(user_id)
        if not profile:
            profile = Profile(
                user_id=user_id,
                first_name="",
                last_name="",
            )
            profile = await self.profile_repo.create(profile)
            await self.session.commit()
            await self.session.refresh(profile)
        return profile

    async def update_profile(self, user_id: UUID, request: ProfileUpdateRequest) -> Profile:
        """Update profile fields with provided values."""
        profile = await self.get_or_create_profile(user_id)

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(profile, key, value)

        await self.profile_repo.update(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

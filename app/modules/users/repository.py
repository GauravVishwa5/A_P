"""Database repository for user profiles."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import Profile


class ProfileRepository:
    """Repository managing Profile persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> Profile | None:
        """Fetch profile for a specific user ID."""
        stmt = select(Profile).where(Profile.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, profile: Profile) -> Profile:
        """Persist a new Profile record."""
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def update(self, profile: Profile) -> Profile:
        """Flush profile updates to session."""
        await self.session.flush()
        return profile

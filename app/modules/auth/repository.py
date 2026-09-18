"""Database repositories for user accounts and refresh token persistence."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RefreshToken, User


class UserRepository:
    """Repository managing User account persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Fetch user by primary key UUID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch user by normalized unique email."""
        stmt = select(User).where(User.email == email.lower().strip())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Persist a new User entity."""
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User) -> User:
        """Update an existing User entity."""
        await self.session.flush()
        return user


class RefreshTokenRepository:
    """Repository managing cryptographic refresh tokens and token family rotation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, token: RefreshToken) -> RefreshToken:
        """Persist a new RefreshToken record."""
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Fetch refresh token by its SHA-256 hash."""
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token_id: UUID) -> None:
        """Mark a specific refresh token as revoked."""
        stmt = update(RefreshToken).where(RefreshToken.id == token_id).values(is_revoked=True)
        await self.session.execute(stmt)

    async def revoke_family(self, family_id: UUID) -> None:
        """Revoke all refresh tokens in a family upon token reuse / theft detection."""
        stmt = (
            update(RefreshToken).where(RefreshToken.family_id == family_id).values(is_revoked=True)
        )
        await self.session.execute(stmt)

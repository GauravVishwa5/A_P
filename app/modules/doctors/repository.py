"""Database repository for Doctor entities and queries."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.doctors.models import Doctor


class DoctorRepository:
    """Repository managing Doctor persistence and discovery queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, doctor_id: UUID) -> Doctor | None:
        """Fetch doctor by primary key UUID."""
        stmt = select(Doctor).where(Doctor.id == doctor_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> Doctor | None:
        """Fetch doctor associated with a user ID."""
        stmt = select(Doctor).where(Doctor.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, doctor: Doctor) -> Doctor:
        """Persist a new Doctor record."""
        self.session.add(doctor)
        await self.session.flush()
        return doctor

    async def update(self, doctor: Doctor) -> Doctor:
        """Update an existing Doctor record."""
        await self.session.flush()
        return doctor

    async def search(
        self,
        specialization: str | None = None,
        max_fee: Decimal | None = None,
        min_rating: Decimal | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Doctor]:
        """Search doctors with composite filtering and pagination."""
        stmt = select(Doctor).where(Doctor.is_available.is_(True))

        if specialization:
            stmt = stmt.where(Doctor.specialization.ilike(f"%{specialization}%"))
        if max_fee is not None:
            stmt = stmt.where(Doctor.consultation_fee <= max_fee)
        if min_rating is not None:
            stmt = stmt.where(Doctor.rating >= min_rating)

        stmt = stmt.order_by(Doctor.rating.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

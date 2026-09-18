"""Database repository for digital prescription persistence and queries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.prescriptions.models import Prescription


class PrescriptionRepository:
    """Encapsulates transactional database access for prescriptions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, prescription: Prescription) -> Prescription:
        """Persist a newly issued prescription."""
        self.session.add(prescription)
        await self.session.flush()
        return prescription

    async def get_by_id(self, prescription_id: UUID) -> Prescription | None:
        """Retrieve prescription by primary key."""
        stmt = select(Prescription).where(Prescription.id == prescription_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_consultation_id(self, consultation_id: UUID) -> Prescription | None:
        """Retrieve prescription associated with a consultation."""
        stmt = select(Prescription).where(Prescription.consultation_id == consultation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

"""Database repository for doctor availability slots."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import SlotStatus
from app.modules.availability.models import AvailabilitySlot


class AvailabilityRepository:
    """Repository managing AvailabilitySlot persistence and temporal queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, slot_id: UUID, for_update: bool = False) -> AvailabilitySlot | None:
        """Fetch slot by ID with optional pessimistic row lock (SELECT ... FOR UPDATE)."""
        stmt = select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_batch(self, slots: list[AvailabilitySlot]) -> list[AvailabilitySlot]:
        """Persist a collection of availability slots."""
        self.session.add_all(slots)
        await self.session.flush()
        return slots

    async def check_overlap(
        self, doctor_id: UUID, start_time: datetime, end_time: datetime
    ) -> bool:
        """Check if interval overlaps any existing non-cancelled slot for the doctor."""
        stmt = (
            select(AvailabilitySlot.id)
            .where(
                and_(
                    AvailabilitySlot.doctor_id == doctor_id,
                    AvailabilitySlot.status != SlotStatus.CANCELLED,
                    AvailabilitySlot.start_time < end_time,
                    AvailabilitySlot.end_time > start_time,
                )
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def get_available_slots(
        self,
        doctor_id: UUID,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> list[AvailabilitySlot]:
        """Query available slots for a doctor within an optional time range."""
        conditions = [
            AvailabilitySlot.doctor_id == doctor_id,
            AvailabilitySlot.status == SlotStatus.AVAILABLE,
        ]
        if from_time:
            conditions.append(AvailabilitySlot.start_time >= from_time)
        if to_time:
            conditions.append(AvailabilitySlot.end_time <= to_time)

        stmt = (
            select(AvailabilitySlot)
            .where(and_(*conditions))
            .order_by(AvailabilitySlot.start_time.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, slot: AvailabilitySlot) -> None:
        """Delete an availability slot."""
        await self.session.delete(slot)
        await self.session.flush()

    async def update(self, slot: AvailabilitySlot) -> AvailabilitySlot:
        """Flush updates to session."""
        await self.session.flush()
        return slot

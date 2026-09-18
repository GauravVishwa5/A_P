"""Business logic service for doctor availability schedule management."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import SlotStatus
from app.common.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.modules.availability.models import AvailabilitySlot
from app.modules.availability.repository import AvailabilityRepository
from app.modules.availability.schemas import (
    AvailabilitySlotBatchCreateRequest,
    AvailabilitySlotResponse,
)


class AvailabilityService:
    """Service managing availability generation, overlap prevention, and queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AvailabilityRepository(session)

    async def create_slots(
        self, doctor_id: UUID, request: AvailabilitySlotBatchCreateRequest
    ) -> list[AvailabilitySlotResponse]:
        """Validate non-overlapping constraints and batch create availability slots."""
        now = datetime.now(UTC)

        # 1. Sort slots by start_time
        sorted_slots = sorted(request.slots, key=lambda s: s.start_time)

        # 2. Check for internal overlap within the incoming batch
        for i in range(len(sorted_slots) - 1):
            cur = sorted_slots[i]
            nxt = sorted_slots[i + 1]
            if cur.end_time > nxt.start_time:
                raise BadRequestException(
                    detail="Overlapping time intervals provided in request batch",
                    error_code="BATCH_SLOTS_OVERLAP",
                )

        new_slot_entities: list[AvailabilitySlot] = []

        # 3. Check for external overlap against existing database slots
        for slot_item in sorted_slots:
            # Check slot is in future
            start_utc = (
                slot_item.start_time.replace(tzinfo=UTC)
                if slot_item.start_time.tzinfo is None
                else slot_item.start_time
            )
            if start_utc <= now:
                raise BadRequestException(
                    detail="Cannot schedule availability slots in the past",
                    error_code="SLOT_IN_PAST",
                )

            has_overlap = await self.repo.check_overlap(
                doctor_id=doctor_id,
                start_time=slot_item.start_time,
                end_time=slot_item.end_time,
            )
            if has_overlap:
                raise ConflictException(
                    detail=f"Slot {slot_item.start_time} overlaps existing availability",
                    error_code="AVAILABILITY_OVERLAP",
                )

            entity = AvailabilitySlot(
                doctor_id=doctor_id,
                start_time=slot_item.start_time,
                end_time=slot_item.end_time,
                status=SlotStatus.AVAILABLE,
            )
            new_slot_entities.append(entity)

        # 4. Atomic batch persistence
        created = await self.repo.create_batch(new_slot_entities)
        await self.session.commit()
        for s in created:
            await self.session.refresh(s)

        return [AvailabilitySlotResponse.model_validate(s) for s in created]

    async def get_available_slots(
        self,
        doctor_id: UUID,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
    ) -> list[AvailabilitySlotResponse]:
        """Fetch available active slots for doctor."""
        slots = await self.repo.get_available_slots(
            doctor_id=doctor_id, from_time=from_time, to_time=to_time
        )
        return [AvailabilitySlotResponse.model_validate(s) for s in slots]

    async def update_slot_status(
        self, doctor_id: UUID, slot_id: UUID, new_status: SlotStatus
    ) -> AvailabilitySlotResponse:
        """Update slot status, validating doctor ownership and state."""
        slot = await self.repo.get_by_id(slot_id)
        if not slot:
            raise NotFoundException("Availability slot not found")

        if slot.doctor_id != doctor_id:
            raise ForbiddenException("You cannot modify another doctor's availability")

        if slot.status == SlotStatus.BOOKED:
            raise ConflictException(
                detail="Cannot modify slot that is already booked",
                error_code="CANNOT_MODIFY_BOOKED_SLOT",
            )

        slot.status = new_status
        await self.repo.update(slot)
        await self.session.commit()
        await self.session.refresh(slot)
        return AvailabilitySlotResponse.model_validate(slot)

    async def delete_slot(self, doctor_id: UUID, slot_id: UUID) -> None:
        """Delete an available slot."""
        slot = await self.repo.get_by_id(slot_id)
        if not slot:
            raise NotFoundException("Availability slot not found")

        if slot.doctor_id != doctor_id:
            raise ForbiddenException("You cannot delete another doctor's availability")

        if slot.status == SlotStatus.BOOKED:
            raise ConflictException(
                detail="Cannot delete slot that is already booked",
                error_code="CANNOT_DELETE_BOOKED_SLOT",
            )

        await self.repo.delete(slot)
        await self.session.commit()

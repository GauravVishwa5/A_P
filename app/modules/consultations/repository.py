"""Repository for consultations, slot locking, idempotency tracking, and booking events."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import ConsultationStatus
from app.common.pagination import PaginationParams
from app.modules.availability.models import AvailabilitySlot
from app.modules.consultations.models import BookingEvent, Consultation, IdempotencyKey


class ConsultationRepository:
    """Encapsulates transactional database access for booking and consultations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_idempotency_record(self, key: str, user_id: UUID) -> IdempotencyKey | None:
        """Fetch existing idempotency record by client key and user."""
        stmt = select(IdempotencyKey).where(
            and_(
                IdempotencyKey.key == key,
                IdempotencyKey.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_idempotency_record(
        self,
        key: str,
        request_hash: str,
        user_id: UUID,
        status_code: int,
        response_payload: dict,
        expires_at: datetime,
    ) -> IdempotencyKey:
        """Persist idempotent response record."""
        record = IdempotencyKey(
            key=key,
            request_hash=request_hash,
            user_id=user_id,
            status_code=status_code,
            response_payload=response_payload,
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def lock_slot_for_update(self, slot_id: UUID) -> AvailabilitySlot | None:
        """Lock availability slot row using SELECT ... FOR UPDATE."""
        stmt = select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_consultation(self, consultation: Consultation) -> Consultation:
        """Persist a newly scheduled consultation."""
        self.session.add(consultation)
        await self.session.flush()
        return consultation

    async def create_booking_event(
        self, consultation_id: UUID, event_type: str, payload: dict
    ) -> BookingEvent:
        """Record immutable event in booking audit trail."""
        event = BookingEvent(
            consultation_id=consultation_id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, consultation_id: UUID) -> Consultation | None:
        """Retrieve consultation by primary key."""
        stmt = select(Consultation).where(Consultation.id == consultation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_slot_by_id(self, slot_id: UUID) -> AvailabilitySlot | None:
        """Retrieve slot without lock."""
        stmt = select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_consultations(
        self,
        patient_id: UUID | None = None,
        doctor_id: UUID | None = None,
        status_filter: ConsultationStatus | None = None,
        pagination: PaginationParams = PaginationParams(),
    ) -> tuple[list[Consultation], int]:
        """Query consultations with role filters and pagination."""
        conditions = []
        if patient_id:
            conditions.append(Consultation.patient_id == patient_id)
        if doctor_id:
            conditions.append(Consultation.doctor_id == doctor_id)
        if status_filter:
            conditions.append(Consultation.status == status_filter.value)

        count_stmt = select(func.count(Consultation.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = (await self.session.execute(count_stmt)).scalar_one()

        items_stmt = select(Consultation)
        if conditions:
            items_stmt = items_stmt.where(and_(*conditions))
        items_stmt = (
            items_stmt.order_by(Consultation.scheduled_start.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )

        result = await self.session.execute(items_stmt)
        items = list(result.scalars().all())

        return items, total

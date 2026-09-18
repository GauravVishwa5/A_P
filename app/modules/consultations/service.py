"""Service layer for consultation booking, idempotency, and state machine transitions."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import ConsultationStatus, SlotStatus, UserRole
from app.common.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnprocessableEntityException,
)
from app.common.pagination import PaginatedResponse, PaginationParams
from app.common.utils import hash_payload, utcnow
from app.modules.auth.models import User
from app.modules.consultations.models import Consultation
from app.modules.consultations.repository import ConsultationRepository
from app.modules.consultations.schemas import BookingRequest, ConsultationResponse
from app.modules.doctors.repository import DoctorRepository


class ConsultationService:
    """Orchestrates consultation bookings, idempotency enforcement, and state transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ConsultationRepository(session)
        self.doctor_repo = DoctorRepository(session)

    async def book_consultation(
        self,
        patient: User,
        request: BookingRequest,
        idempotency_key: str,
    ) -> tuple[ConsultationResponse, int]:
        """Atomically lock availability slot and schedule consultation with idempotency.

        Returns (ConsultationResponse, status_code).
        """
        # 1. Enforce caller is PATIENT
        if patient.role != UserRole.PATIENT.value:
            raise ForbiddenException("Only registered patients can book consultations")

        # 2. Deterministic request hashing for idempotency verification
        payload_dict = {
            "doctor_id": str(request.doctor_id),
            "slot_id": str(request.slot_id),
            "reason": request.reason,
        }
        current_hash = hash_payload(payload_dict)

        # 3. Check existing idempotency key
        existing_idempotency = await self.repo.get_idempotency_record(
            key=idempotency_key,
            user_id=patient.id,
        )
        if existing_idempotency:
            if existing_idempotency.request_hash == current_hash:
                # Same key + same payload: return previously stored response
                return (
                    ConsultationResponse.model_validate(existing_idempotency.response_payload),
                    existing_idempotency.status_code,
                )
            # Same key + different payload: 422 Unprocessable Entity
            raise UnprocessableEntityException(
                detail="Idempotency key reused with mismatched request payload",
                error_code="IDEMPOTENCY_PAYLOAD_MISMATCH",
            )

        # 4. Lock availability slot: SELECT ... FOR UPDATE
        slot = await self.repo.lock_slot_for_update(request.slot_id)
        if not slot:
            raise NotFoundException("Availability slot not found", error_code="SLOT_NOT_FOUND")

        # 5. Invariant validations on locked row
        if slot.doctor_id != request.doctor_id:
            raise BadRequestException(
                "Slot does not belong to the requested doctor",
                error_code="DOCTOR_SLOT_MISMATCH",
            )

        if slot.status != SlotStatus.AVAILABLE.value:
            raise ConflictException(
                "Availability slot is no longer available for booking",
                error_code="SLOT_ALREADY_BOOKED",
            )

        now = utcnow()
        slot_start = slot.start_time
        if slot_start.tzinfo is None:
            from datetime import UTC

            slot_start = slot_start.replace(tzinfo=UTC)

        if slot_start <= now:
            raise BadRequestException(
                "Cannot book an availability slot in the past",
                error_code="SLOT_IN_PAST",
            )

        # 6. Update slot state to BOOKED
        slot.status = SlotStatus.BOOKED.value

        # 7. Create consultation in SCHEDULED state
        consultation = Consultation(
            patient_id=patient.id,
            doctor_id=request.doctor_id,
            availability_slot_id=slot.id,
            status=ConsultationStatus.SCHEDULED.value,
            scheduled_start=slot.start_time,
            scheduled_end=slot.end_time,
        )
        try:
            created_consultation = await self.repo.create_consultation(consultation)

            # 8. Create booking audit event
            await self.repo.create_booking_event(
                consultation_id=created_consultation.id,
                event_type="BOOKING_CREATED",
                payload={
                    "patient_id": str(patient.id),
                    "doctor_id": str(request.doctor_id),
                    "slot_id": str(slot.id),
                    "reason": request.reason,
                },
            )

            response_schema = ConsultationResponse.model_validate(created_consultation)

            # 9. Store idempotency record
            await self.repo.save_idempotency_record(
                key=idempotency_key,
                request_hash=current_hash,
                user_id=patient.id,
                status_code=201,
                response_payload=response_schema.model_dump(mode="json"),
                expires_at=now + timedelta(days=7),
            )

            # 10. Commit transaction
            await self.session.commit()
            return response_schema, 201
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictException(
                "Availability slot is already booked",
                error_code="SLOT_ALREADY_BOOKED",
            ) from exc

    async def get_consultation(
        self,
        consultation_id: UUID,
        current_user: User,
    ) -> Consultation:
        """Retrieve consultation enforcing strict resource authorization (IDOR prevention)."""
        consultation = await self.repo.get_by_id(consultation_id)
        if not consultation:
            raise NotFoundException("Consultation not found", error_code="CONSULTATION_NOT_FOUND")

        # RBAC & IDOR check
        if current_user.role == UserRole.ADMIN.value:
            return consultation

        if current_user.role == UserRole.PATIENT.value:
            if consultation.patient_id != current_user.id:
                raise ForbiddenException("Access denied to requested consultation")
            return consultation

        if current_user.role == UserRole.DOCTOR.value:
            # Current user is a doctor; check if assigned doctor matches user's doctor profile
            doc = await self.doctor_repo.get_by_user_id(current_user.id)
            if not doc or consultation.doctor_id != doc.id:
                raise ForbiddenException("Access denied to requested consultation")
            return consultation

        raise ForbiddenException("Unauthorized role for consultation access")

    async def list_consultations(
        self,
        current_user: User,
        status_filter: ConsultationStatus | None = None,
        pagination: PaginationParams = PaginationParams(),
    ) -> PaginatedResponse[ConsultationResponse]:
        """List caller-scoped consultations with optional status filter."""
        patient_id = None
        doctor_id = None

        if current_user.role == UserRole.PATIENT.value:
            patient_id = current_user.id
        elif current_user.role == UserRole.DOCTOR.value:
            doc = await self.doctor_repo.get_by_user_id(current_user.id)
            if not doc:
                raise ForbiddenException("Doctor profile required")
            doctor_id = doc.id
        elif current_user.role != UserRole.ADMIN.value:
            raise ForbiddenException("Unauthorized role")

        items, total = await self.repo.list_consultations(
            patient_id=patient_id,
            doctor_id=doctor_id,
            status_filter=status_filter,
            pagination=pagination,
        )

        response_items = [ConsultationResponse.model_validate(item) for item in items]
        return PaginatedResponse.create(
            items=response_items,
            total=total,
            params=pagination,
        )

    async def cancel_consultation(
        self,
        consultation_id: UUID,
        reason: str,
        current_user: User,
    ) -> ConsultationResponse:
        """Cancel upcoming consultation and release slot back to AVAILABLE."""
        consultation = await self.get_consultation(consultation_id, current_user)

        # State Machine check: Only SCHEDULED or CONFIRMED can transition to CANCELLED
        if consultation.status not in (
            ConsultationStatus.SCHEDULED.value,
            ConsultationStatus.CONFIRMED.value,
        ):
            raise BadRequestException(
                f"Cannot cancel consultation in state '{consultation.status}'",
                error_code="INVALID_STATE_TRANSITION",
            )

        consultation.status = ConsultationStatus.CANCELLED.value
        consultation.cancelled_at = utcnow()
        consultation.cancellation_reason = reason

        # Release slot
        slot = await self.repo.get_slot_by_id(consultation.availability_slot_id)
        if slot:
            slot.status = SlotStatus.AVAILABLE.value

        # Log event
        await self.repo.create_booking_event(
            consultation_id=consultation.id,
            event_type="BOOKING_CANCELLED",
            payload={"reason": reason, "cancelled_by": str(current_user.id)},
        )

        await self.session.commit()
        return ConsultationResponse.model_validate(consultation)

    async def start_consultation(
        self,
        consultation_id: UUID,
        current_user: User,
    ) -> ConsultationResponse:
        """Mark consultation IN_PROGRESS (Doctor-only)."""
        consultation = await self.get_consultation(consultation_id, current_user)

        if current_user.role != UserRole.DOCTOR.value:
            raise ForbiddenException("Only the assigned doctor can start a consultation")

        # State machine transition: SCHEDULED or CONFIRMED -> IN_PROGRESS
        if consultation.status not in (
            ConsultationStatus.SCHEDULED.value,
            ConsultationStatus.CONFIRMED.value,
        ):
            raise BadRequestException(
                f"Cannot transition consultation from '{consultation.status}' to IN_PROGRESS",
                error_code="INVALID_STATE_TRANSITION",
            )

        consultation.status = ConsultationStatus.IN_PROGRESS.value
        consultation.started_at = utcnow()

        await self.repo.create_booking_event(
            consultation_id=consultation.id,
            event_type="CONSULTATION_STARTED",
            payload={"started_by": str(current_user.id)},
        )

        await self.session.commit()
        return ConsultationResponse.model_validate(consultation)

    async def complete_consultation(
        self,
        consultation_id: UUID,
        current_user: User,
    ) -> ConsultationResponse:
        """Mark consultation COMPLETED (Doctor-only)."""
        consultation = await self.get_consultation(consultation_id, current_user)

        if current_user.role != UserRole.DOCTOR.value:
            raise ForbiddenException("Only the assigned doctor can complete a consultation")

        # State machine transition: IN_PROGRESS -> COMPLETED
        if consultation.status != ConsultationStatus.IN_PROGRESS.value:
            raise BadRequestException(
                f"Cannot transition consultation from '{consultation.status}' to COMPLETED",
                error_code="INVALID_STATE_TRANSITION",
            )

        consultation.status = ConsultationStatus.COMPLETED.value
        consultation.completed_at = utcnow()

        await self.repo.create_booking_event(
            consultation_id=consultation.id,
            event_type="CONSULTATION_COMPLETED",
            payload={"completed_by": str(current_user.id)},
        )

        await self.session.commit()
        return ConsultationResponse.model_validate(consultation)

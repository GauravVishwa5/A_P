"""FastAPI REST router for doctor availability scheduling."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import get_current_active_doctor
from app.modules.availability.schemas import (
    AvailabilitySlotBatchCreateRequest,
    AvailabilitySlotResponse,
    SlotStatusUpdateRequest,
)
from app.modules.availability.service import AvailabilityService
from app.modules.doctors.models import Doctor

router = APIRouter(tags=["Availability"])


@router.post(
    "/api/v1/doctors/me/availability",
    response_model=list[AvailabilitySlotResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Batch create availability slots for authenticated doctor",
)
async def create_my_availability_slots(
    request: AvailabilitySlotBatchCreateRequest,
    doctor: Doctor = Depends(get_current_active_doctor),
    db: AsyncSession = Depends(get_db_session),
) -> list[AvailabilitySlotResponse]:
    """Create non-overlapping schedule slots for calling doctor."""
    service = AvailabilityService(db)
    return await service.create_slots(doctor.id, request)


@router.get(
    "/api/v1/doctors/{doctor_id}/availability",
    response_model=list[AvailabilitySlotResponse],
    summary="List available booking slots for a doctor",
)
async def get_doctor_availability(
    doctor_id: UUID,
    from_time: datetime | None = Query(
        default=None, description="Filter slots starting at or after timestamp"
    ),
    to_time: datetime | None = Query(
        default=None, description="Filter slots ending at or before timestamp"
    ),
    db: AsyncSession = Depends(get_db_session),
) -> list[AvailabilitySlotResponse]:
    """Retrieve all active available slots for public/patient booking."""
    service = AvailabilityService(db)
    return await service.get_available_slots(doctor_id, from_time, to_time)


@router.patch(
    "/api/v1/availability/{slot_id}",
    response_model=AvailabilitySlotResponse,
    summary="Update availability slot status",
)
async def update_availability_slot(
    slot_id: UUID,
    request: SlotStatusUpdateRequest,
    doctor: Doctor = Depends(get_current_active_doctor),
    db: AsyncSession = Depends(get_db_session),
) -> AvailabilitySlotResponse:
    """Modify availability slot status (e.g. mark CANCELLED)."""
    service = AvailabilityService(db)
    return await service.update_slot_status(doctor.id, slot_id, request.status)


@router.delete(
    "/api/v1/availability/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an available slot",
)
async def delete_availability_slot(
    slot_id: UUID,
    doctor: Doctor = Depends(get_current_active_doctor),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Delete an unbooked availability slot."""
    service = AvailabilityService(db)
    await service.delete_slot(doctor.id, slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

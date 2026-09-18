"""Pydantic schemas for consultation booking and lifecycle management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.constants import ConsultationStatus


class BookingRequest(BaseModel):
    """Payload to book an available doctor slot."""

    model_config = ConfigDict(extra="forbid")

    doctor_id: UUID
    slot_id: UUID
    reason: str | None = Field(default=None, max_length=500)


class ConsultationCancelRequest(BaseModel):
    """Payload to cancel an upcoming consultation."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class ConsultationResponse(BaseModel):
    """Public consultation representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    doctor_id: UUID
    availability_slot_id: UUID
    status: ConsultationStatus
    scheduled_start: datetime
    scheduled_end: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    meeting_reference: str | None = None
    created_at: datetime
    updated_at: datetime

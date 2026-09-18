"""Pydantic schemas for doctor availability scheduling."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.constants import SlotStatus


class AvailabilitySlotCreateItem(BaseModel):
    """Single availability time interval definition."""

    model_config = ConfigDict(extra="forbid")

    start_time: datetime = Field(description="Slot start time in UTC")
    end_time: datetime = Field(description="Slot end time in UTC")

    @model_validator(mode="after")
    def validate_time_window(self) -> "AvailabilitySlotCreateItem":
        if self.end_time <= self.start_time:
            raise ValueError("Slot end_time must be strictly after start_time")
        return self


class AvailabilitySlotBatchCreateRequest(BaseModel):
    """Batch slot creation payload."""

    model_config = ConfigDict(extra="forbid")

    slots: list[AvailabilitySlotCreateItem] = Field(
        min_length=1, max_length=50, description="List of non-overlapping slots"
    )


class AvailabilitySlotResponse(BaseModel):
    """Public representation of an availability slot."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doctor_id: UUID
    start_time: datetime
    end_time: datetime
    status: SlotStatus
    created_at: datetime
    updated_at: datetime


class SlotStatusUpdateRequest(BaseModel):
    """Payload to update slot status."""

    model_config = ConfigDict(extra="forbid")

    status: SlotStatus

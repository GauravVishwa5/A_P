"""Pydantic schemas for user profile data and updates."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProfileUpdateRequest(BaseModel):
    """Payload to update personal user profile attributes."""

    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, max_length=32)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=32)
    address: str | None = None


class ProfileResponse(BaseModel):
    """Public profile representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    first_name: str
    last_name: str
    phone_number: str | None
    date_of_birth: date | None
    gender: str | None
    address: str | None
    created_at: datetime
    updated_at: datetime

"""Pydantic schemas for doctor profiles, directory listing, and updates."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DoctorCreateRequest(BaseModel):
    """Payload to register/initialize a doctor profile."""

    model_config = ConfigDict(extra="forbid")

    specialization: str = Field(min_length=2, max_length=100)
    license_number: str = Field(min_length=2, max_length=100)
    experience_years: int = Field(default=0, ge=0)
    consultation_fee: Decimal = Field(ge=Decimal("0.00"))
    bio: str | None = None
    languages: list[str] = Field(default_factory=list)


class DoctorUpdateRequest(BaseModel):
    """Payload to modify doctor profile details."""

    model_config = ConfigDict(extra="forbid")

    specialization: str | None = Field(default=None, min_length=2, max_length=100)
    experience_years: int | None = Field(default=None, ge=0)
    consultation_fee: Decimal | None = Field(default=None, ge=Decimal("0.00"))
    bio: str | None = None
    languages: list[str] | None = None
    is_available: bool | None = None


class DoctorResponse(BaseModel):
    """Public representation of doctor professional profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    specialization: str
    license_number: str
    experience_years: int
    consultation_fee: Decimal
    bio: str | None
    languages: list[str]
    rating: Decimal
    total_reviews: int
    is_available: bool
    created_at: datetime
    updated_at: datetime

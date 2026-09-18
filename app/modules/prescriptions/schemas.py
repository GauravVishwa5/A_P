"""Pydantic schemas for medical prescriptions and structured medication data."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MedicationItem(BaseModel):
    """Structured medication item with clinical dosing parameters."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150, description="Medication or formulation name")
    dosage: str = Field(
        min_length=1, max_length=100, description="Dose per administration (e.g. 500mg, 2 tabs)"
    )
    frequency: str = Field(
        min_length=1, max_length=100, description="Frequency (e.g. Twice daily after food)"
    )
    duration: str = Field(
        min_length=1, max_length=100, description="Duration of therapy (e.g. 14 days)"
    )
    instructions: str | None = Field(
        default=None, max_length=500, description="Special administration instructions"
    )


class PrescriptionCreateRequest(BaseModel):
    """Request payload to issue an immutable medical prescription."""

    model_config = ConfigDict(extra="forbid")

    diagnosis: str = Field(min_length=3, max_length=1000, description="Primary clinical diagnosis")
    medications: list[MedicationItem] = Field(
        min_length=1, description="List of prescribed medications"
    )
    notes: str | None = Field(
        default=None, max_length=2000, description="Dietary and lifestyle advice"
    )


class PrescriptionResponse(BaseModel):
    """Public digital prescription representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    doctor_id: UUID
    patient_id: UUID
    diagnosis: str
    medications: list[MedicationItem]
    notes: str | None = None
    created_at: datetime

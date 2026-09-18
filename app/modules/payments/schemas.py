"""Pydantic schemas for payment initiation, status tracking, and refunds."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.constants import PaymentProvider, PaymentStatus


class PaymentInitiateRequest(BaseModel):
    """Payload to initiate payment for a scheduled consultation."""

    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=Decimal("0.00"), description="Positive payment amount")
    currency: str = Field(
        default="INR", min_length=3, max_length=3, description="ISO 4217 3-letter currency code"
    )
    mock_mode: str | None = Field(
        default=None, description="Testing scenario override: SUCCESS, FAILURE, TIMEOUT"
    )


class PaymentRefundRequest(BaseModel):
    """Payload to issue refund for a settled payment."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500, description="Audit reason for refund")


class PaymentResponse(BaseModel):
    """Public representation of payment ledger entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    patient_id: UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    provider: PaymentProvider
    transaction_reference: str | None = None
    idempotency_key: str | None = None
    created_at: datetime
    updated_at: datetime

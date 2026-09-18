"""SQLAlchemy ORM models for payments and settlement records."""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.constants import PaymentProvider, PaymentStatus
from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.consultations.models import Consultation


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Payment transaction associated with a consultation."""

    __tablename__ = "payments"

    consultation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consultations.id"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=PaymentStatus.INITIATED, nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(
        String(64), default=PaymentProvider.MOCK_PAYMENT, nullable=False
    )
    transaction_reference: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_payment_amount"),
        CheckConstraint(
            "status IN ('INITIATED', 'SUCCESS', 'FAILED', 'REFUNDED')",
            name="chk_payment_status",
        ),
        Index("idx_payments_consultation_status", "consultation_id", "status"),
    )

    # Relationships
    consultation: Mapped["Consultation"] = relationship("Consultation", back_populates="payments")
    patient: Mapped["User"] = relationship("User")

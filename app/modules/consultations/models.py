"""SQLAlchemy ORM models for consultations, idempotency keys, and booking events."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.constants import ConsultationStatus
from app.common.utils import utcnow
from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.availability.models import AvailabilitySlot
    from app.modules.doctors.models import Doctor
    from app.modules.payments.models import Payment
    from app.modules.prescriptions.models import Prescription


class Consultation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Consultation booking entity representing doctor-patient encounter."""

    __tablename__ = "consultations"

    patient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    doctor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("doctors.id"),
        nullable=False,
        index=True,
    )
    availability_slot_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("availability_slots.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), default=ConsultationStatus.SCHEDULED, nullable=False, index=True
    )
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_reference: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("scheduled_end > scheduled_start", name="chk_consultation_time"),
        CheckConstraint(
            "status IN ('SCHEDULED', 'CONFIRMED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="chk_consultation_status",
        ),
        # Partial unique index guaranteeing no two active consultations can share the same slot
        Index(
            "uq_consultations_slot_active",
            "availability_slot_id",
            unique=True,
            postgresql_where=(status != ConsultationStatus.CANCELLED),
        ),
        Index("idx_consultations_patient_start", "patient_id", scheduled_start.desc()),
        Index("idx_consultations_doctor_start", "doctor_id", scheduled_start.desc()),
    )

    # Relationships
    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    doctor: Mapped["Doctor"] = relationship("Doctor", foreign_keys=[doctor_id])
    availability_slot: Mapped["AvailabilitySlot"] = relationship(
        "AvailabilitySlot", back_populates="consultation"
    )
    prescription: Mapped["Prescription | None"] = relationship(
        "Prescription", back_populates="consultation", uselist=False
    )
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="consultation")
    booking_events: Mapped[list["BookingEvent"]] = relationship(
        "BookingEvent", back_populates="consultation", cascade="all, delete-orphan"
    )


class IdempotencyKey(Base, UUIDPrimaryKeyMixin):
    """Persistent store for idempotent request deduplication and response caching."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (Index("idx_idempotency_lookup", "key", "user_id"),)


class BookingEvent(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail for consultation booking events."""

    __tablename__ = "booking_events"

    consultation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Relationship
    consultation: Mapped["Consultation"] = relationship(
        "Consultation", back_populates="booking_events"
    )

"""SQLAlchemy ORM models for doctor schedule availability slots."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.constants import SlotStatus
from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.consultations.models import Consultation
    from app.modules.doctors.models import Doctor


class AvailabilitySlot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Doctor availability time slot for booking."""

    __tablename__ = "availability_slots"

    doctor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=SlotStatus.AVAILABLE, nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="chk_slot_time"),
        CheckConstraint(
            "status IN ('AVAILABLE', 'HELD', 'BOOKED', 'CANCELLED')",
            name="chk_slot_status",
        ),
        UniqueConstraint("doctor_id", "start_time", name="uq_doctor_slot_time"),
        Index("idx_slots_doctor_start", "doctor_id", "start_time"),
    )

    # Relationships
    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="availability_slots")
    consultation: Mapped["Consultation | None"] = relationship(
        "Consultation", back_populates="availability_slot", uselist=False
    )

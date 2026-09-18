"""SQLAlchemy ORM models for doctor profiles and directories."""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.availability.models import AvailabilitySlot
    from app.modules.consultations.models import Consultation


class Doctor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Professional doctor profile associated with a User of role DOCTOR."""

    __tablename__ = "doctors"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    specialization: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    license_number: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    experience_years: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultation_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), index=True, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"), default=list, nullable=False
    )
    rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("5.00"), index=True, nullable=False
    )
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("consultation_fee >= 0", name="chk_doctor_fee"),
        CheckConstraint("experience_years >= 0", name="chk_doctor_experience"),
        Index("idx_doctors_rating_desc", rating.desc()),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="doctor")
    availability_slots: Mapped[list["AvailabilitySlot"]] = relationship(
        "AvailabilitySlot", back_populates="doctor", cascade="all, delete-orphan"
    )
    consultations: Mapped[list["Consultation"]] = relationship(
        "Consultation", back_populates="doctor"
    )

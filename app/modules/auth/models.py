"""SQLAlchemy ORM models for authentication and identity management."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.constants import UserRole
from app.common.utils import generate_uuid, utcnow
from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.doctors.models import Doctor
    from app.modules.users.models import Profile


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User account entity storing credentials, role, and MFA configuration."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.PATIENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('PATIENT', 'DOCTOR', 'ADMIN')", name="chk_user_role"),
    )

    # Relationships
    profile: Mapped["Profile | None"] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    doctor: Mapped["Doctor | None"] = relationship(
        "Doctor", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base, UUIDPrimaryKeyMixin):
    """Opaque refresh token representation stored as SHA-256 hash."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    family_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        default=generate_uuid,
        nullable=False,
        index=True,
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (Index("idx_refresh_tokens_lookup", "token_hash", "is_revoked"),)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

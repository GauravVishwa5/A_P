"""SQLAlchemy ORM models for async notifications and delivery logs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constants import NotificationChannel, NotificationStatus
from app.common.utils import utcnow
from app.core.database import Base, UUIDPrimaryKeyMixin


class Notification(Base, UUIDPrimaryKeyMixin):
    """Notification entity queued for asynchronous delivery."""

    __tablename__ = "notifications"

    recipient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(
        String(32), default=NotificationChannel.EMAIL, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=NotificationStatus.PENDING, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_notifications_recipient_status", "recipient_id", "status"),)

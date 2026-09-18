"""Repository for notification record management."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import NotificationStatus
from app.modules.notifications.models import Notification


class NotificationRepository:
    """Encapsulates database operations for notification records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, notification: Notification) -> Notification:
        """Insert a new notification record."""
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        """Retrieve notification by ID."""
        result = await self.session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def list_pending(self, limit: int = 50) -> Sequence[Notification]:
        """Fetch pending notifications awaiting delivery."""
        result = await self.session.execute(
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING.value)
            .order_by(Notification.created_at.asc())
            .limit(limit)
        )
        return result.scalars().all()

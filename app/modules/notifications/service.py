"""Service layer for creating, dispatching, and updating notifications."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import NotificationChannel, NotificationStatus
from app.common.utils import utcnow
from app.modules.notifications.models import Notification
from app.modules.notifications.repository import NotificationRepository

logger = logging.getLogger(__name__)


class NotificationService:
    """Orchestrates notification lifecycle and dispatching."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)

    async def enqueue_notification(
        self,
        recipient_id: UUID,
        type_: str,
        title: str,
        body: str,
        channel: NotificationChannel = NotificationChannel.EMAIL,
    ) -> Notification:
        """Create pending notification record in authoritative database."""
        notification = Notification(
            recipient_id=recipient_id,
            type=type_,
            channel=channel.value,
            title=title,
            body=body,
            status=NotificationStatus.PENDING.value,
        )
        created = await self.repo.create(notification)
        logger.info(
            f"Notification queued: id={created.id} recipient={recipient_id} "
            f"type={type_} channel={channel.value}"
        )
        return created

    async def mark_delivered(self, notification_id: UUID) -> Notification | None:
        """Mark notification as successfully sent."""
        notification = await self.repo.get_by_id(notification_id)
        if notification:
            notification.status = NotificationStatus.SENT.value
            notification.sent_at = utcnow()
            await self.session.commit()
            logger.info(f"Notification delivered: id={notification_id}")
        return notification

    async def mark_failed(self, notification_id: UUID) -> Notification | None:
        """Mark notification as failed after exhaustive retries."""
        notification = await self.repo.get_by_id(notification_id)
        if notification:
            notification.status = NotificationStatus.FAILED.value
            await self.session.commit()
            logger.error(f"Notification marked failed: id={notification_id}")
        return notification

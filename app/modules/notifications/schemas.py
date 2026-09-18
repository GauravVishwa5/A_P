"""Pydantic schemas for asynchronous notifications."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.common.constants import NotificationChannel, NotificationStatus


class NotificationResponse(BaseModel):
    """Public representation of a system notification."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recipient_id: UUID
    type: str
    channel: NotificationChannel
    title: str
    body: str
    status: NotificationStatus
    created_at: datetime
    sent_at: datetime | None = None

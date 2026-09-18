"""Pydantic schemas for audit trail records, compliance logs, and filters."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    """Public representation of an immutable audit trail entry."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    actor_id: UUID | None = None
    actor_role: str | None = None
    action: str
    resource_type: str
    resource_id: str
    ip_address: str | None = None
    user_agent: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime


class AuditLogFilter(BaseModel):
    """Query filters for compliance log auditing."""

    actor_id: UUID | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    status: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

"""Service layer for compliance auditing and audit trail queries."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse, PaginationParams
from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditLogFilter, AuditLogResponse

logger = logging.getLogger(__name__)


class AuditService:
    """Orchestrates structured audit record generation and compliance retrieval."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AuditRepository(session)

    async def record_event(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        status: str,
        actor_id: UUID | None = None,
        actor_role: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Create and persist an immutable audit trail entry."""
        audit_log = AuditLog(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            metadata_=metadata or {},
        )
        created = await self.repo.create(audit_log)
        logger.info(
            f"Audit recorded: action={action} resource={resource_type}:{resource_id} "
            f"actor={actor_id} status={status}"
        )
        return created

    async def list_audit_logs(
        self,
        filters: AuditLogFilter | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResponse[AuditLogResponse]:
        """Query compliance audit trail entries."""
        params = pagination or PaginationParams(page=1, page_size=20)
        items, total = await self.repo.list_logs(filters=filters, pagination=params)
        responses = [AuditLogResponse.model_validate(item) for item in items]
        return PaginatedResponse.create(
            items=responses,
            total=total,
            params=params,
        )

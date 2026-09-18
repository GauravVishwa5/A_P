"""Repository for audit trail persistence and historical querying."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginationParams
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogFilter


class AuditRepository:
    """Encapsulates database operations for immutable audit logs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, audit_log: AuditLog) -> AuditLog:
        """Insert a new immutable audit record."""
        self.session.add(audit_log)
        await self.session.flush()
        return audit_log

    async def get_by_id(self, log_id: UUID) -> AuditLog | None:
        """Retrieve audit log entry by primary key."""
        result = await self.session.execute(select(AuditLog).where(AuditLog.id == log_id))
        return result.scalar_one_or_none()

    async def list_logs(
        self,
        filters: AuditLogFilter | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[AuditLog], int]:
        """Query audit records with filtering and pagination."""
        query: Select[tuple[AuditLog]] = select(AuditLog)
        count_query = select(func.count(AuditLog.id))

        if filters:
            if filters.actor_id:
                query = query.where(AuditLog.actor_id == filters.actor_id)
                count_query = count_query.where(AuditLog.actor_id == filters.actor_id)
            if filters.action:
                query = query.where(AuditLog.action == filters.action)
                count_query = count_query.where(AuditLog.action == filters.action)
            if filters.resource_type:
                query = query.where(AuditLog.resource_type == filters.resource_type)
                count_query = count_query.where(AuditLog.resource_type == filters.resource_type)
            if filters.resource_id:
                query = query.where(AuditLog.resource_id == filters.resource_id)
                count_query = count_query.where(AuditLog.resource_id == filters.resource_id)
            if filters.status:
                query = query.where(AuditLog.status == filters.status)
                count_query = count_query.where(AuditLog.status == filters.status)
            if filters.start_time:
                query = query.where(AuditLog.created_at >= filters.start_time)
                count_query = count_query.where(AuditLog.created_at >= filters.start_time)
            if filters.end_time:
                query = query.where(AuditLog.created_at <= filters.end_time)
                count_query = count_query.where(AuditLog.created_at <= filters.end_time)

        total = await self.session.scalar(count_query) or 0

        query = query.order_by(AuditLog.created_at.desc())

        if pagination:
            query = query.offset(pagination.offset).limit(pagination.page_size)

        result = await self.session.execute(query)
        items = result.scalars().all()
        return items, total

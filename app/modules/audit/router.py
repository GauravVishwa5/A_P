"""FastAPI REST router for system audit trail and compliance queries."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import UserRole
from app.common.pagination import PaginatedResponse, PaginationParams
from app.core.database import get_db_session
from app.core.dependencies import require_roles
from app.modules.audit.schemas import AuditLogFilter, AuditLogResponse
from app.modules.audit.service import AuditService
from app.modules.auth.models import User

router = APIRouter(prefix="/api/v1/audit", tags=["Audit & Compliance"])


@router.get(
    "/logs",
    response_model=PaginatedResponse[AuditLogResponse],
    summary="List immutable audit trail records (Admin-only)",
)
async def list_audit_logs(
    filters: AuditLogFilter = Depends(),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[AuditLogResponse]:
    """Retrieve compliance logs with granular actor, action, and resource filtering."""
    service = AuditService(db)
    return await service.list_audit_logs(filters=filters, pagination=pagination)

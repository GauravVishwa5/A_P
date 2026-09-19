"""FastAPI REST router for administrative operations and business analytics."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import UserRole
from app.core.database import get_db_session
from app.core.dependencies import require_roles
from app.modules.admin.schemas import AdminAnalyticsResponse
from app.modules.admin.service import AdminAnalyticsService
from app.modules.auth.models import User

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Operations & Analytics"])


@router.get(
    "/analytics",
    response_model=AdminAnalyticsResponse,
    summary="Retrieve platform-wide business analytics (Admin-only)",
)
async def get_platform_analytics(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
) -> AdminAnalyticsResponse:
    """Compute aggregate platform KPIs including user distributions, consultation statuses,
    gross/net revenues, and clinical documentation metrics directly from the database engine.
    """
    service = AdminAnalyticsService(db)
    return await service.get_analytics()

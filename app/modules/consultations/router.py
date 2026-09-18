"""FastAPI REST router for consultation booking and lifecycle endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import ConsultationStatus, UserRole
from app.common.exceptions import BadRequestException
from app.common.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
)
from app.core.database import get_db_session
from app.core.dependencies import get_current_user, require_roles
from app.modules.auth.models import User
from app.modules.consultations.schemas import (
    BookingRequest,
    ConsultationCancelRequest,
    ConsultationResponse,
)
from app.modules.consultations.service import ConsultationService

router = APIRouter(prefix="/api/v1/consultations", tags=["Consultations"])


@router.post(
    "",
    response_model=ConsultationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book a consultation slot with idempotency",
)
async def book_consultation(
    request: BookingRequest,
    response: Response,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", description="Unique client key for deduplication"
    ),
    current_user: User = Depends(require_roles(UserRole.PATIENT)),
    db: AsyncSession = Depends(get_db_session),
) -> ConsultationResponse:
    """Atomically schedule a doctor consultation slot with idempotency guarantee."""
    if not idempotency_key or not idempotency_key.strip():
        raise BadRequestException(
            "Idempotency-Key header is required for consultation creation",
            error_code="MISSING_IDEMPOTENCY_KEY",
        )

    service = ConsultationService(db)
    result, status_code = await service.book_consultation(
        patient=current_user,
        request=request,
        idempotency_key=idempotency_key.strip(),
    )
    response.status_code = status_code
    return result


@router.get(
    "",
    response_model=PaginatedResponse[ConsultationResponse],
    summary="List consultations for authenticated user",
)
async def list_my_consultations(
    status_filter: ConsultationStatus | None = Query(
        default=None, alias="status", description="Filter by consultation status"
    ),
    pagination: PaginationParams = Depends(get_pagination_params),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[ConsultationResponse]:
    """Retrieve paginated consultation history scoped to the caller's role."""
    service = ConsultationService(db)
    return await service.list_consultations(
        current_user=current_user,
        status_filter=status_filter,
        pagination=pagination,
    )


@router.get(
    "/{consultation_id}",
    response_model=ConsultationResponse,
    summary="Get consultation details by ID",
)
async def get_consultation_by_id(
    consultation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConsultationResponse:
    """Retrieve full consultation details enforcing RBAC / IDOR ownership."""
    service = ConsultationService(db)
    consultation = await service.get_consultation(consultation_id, current_user)
    return ConsultationResponse.model_validate(consultation)


@router.post(
    "/{consultation_id}/cancel",
    response_model=ConsultationResponse,
    summary="Cancel upcoming consultation",
)
async def cancel_consultation(
    consultation_id: UUID,
    request: ConsultationCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ConsultationResponse:
    """Cancel scheduled consultation and release the booked slot."""
    service = ConsultationService(db)
    return await service.cancel_consultation(
        consultation_id=consultation_id,
        reason=request.reason,
        current_user=current_user,
    )


@router.post(
    "/{consultation_id}/start",
    response_model=ConsultationResponse,
    summary="Start consultation (Doctor-only)",
)
async def start_consultation(
    consultation_id: UUID,
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: AsyncSession = Depends(get_db_session),
) -> ConsultationResponse:
    """Mark consultation as IN_PROGRESS by the assigned doctor."""
    service = ConsultationService(db)
    return await service.start_consultation(
        consultation_id=consultation_id,
        current_user=current_user,
    )


@router.post(
    "/{consultation_id}/complete",
    response_model=ConsultationResponse,
    summary="Complete consultation (Doctor-only)",
)
async def complete_consultation(
    consultation_id: UUID,
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: AsyncSession = Depends(get_db_session),
) -> ConsultationResponse:
    """Mark consultation as COMPLETED by the assigned doctor."""
    service = ConsultationService(db)
    return await service.complete_consultation(
        consultation_id=consultation_id,
        current_user=current_user,
    )

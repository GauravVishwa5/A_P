"""FastAPI REST router for doctor directory search and profile management."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import UserRole
from app.common.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
)
from app.core.database import get_db_session
from app.core.dependencies import require_roles
from app.modules.auth.models import User
from app.modules.doctors.schemas import (
    DoctorCreateRequest,
    DoctorResponse,
    DoctorUpdateRequest,
)
from app.modules.doctors.service import DoctorService

router = APIRouter(prefix="/api/v1/doctors", tags=["Doctors"])


@router.get(
    "",
    response_model=PaginatedResponse[DoctorResponse],
    summary="Search and filter active doctors",
)
async def search_doctors(
    specialization: str | None = Query(default=None, description="Filter by specialization"),
    max_fee: Decimal | None = Query(default=None, ge=0.0, description="Maximum consultation fee"),
    min_rating: Decimal | None = Query(default=None, ge=0.0, le=5.0, description="Minimum rating"),
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[DoctorResponse]:
    """Discover doctors by specialization, maximum fee, and minimum rating."""
    service = DoctorService(db)
    return await service.search_doctors(
        specialization=specialization,
        max_fee=max_fee,
        min_rating=min_rating,
        pagination=pagination,
    )


@router.get(
    "/{doctor_id}",
    response_model=DoctorResponse,
    summary="Get doctor profile details by ID",
)
async def get_doctor_by_id(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db_session),
) -> DoctorResponse:
    """Retrieve full professional profile for a specific doctor."""
    service = DoctorService(db)
    doctor = await service.get_doctor_by_id(doctor_id)
    return DoctorResponse.model_validate(doctor)


@router.post(
    "/me",
    response_model=DoctorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize current user's doctor profile",
)
async def create_my_doctor_profile(
    request: DoctorCreateRequest,
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: AsyncSession = Depends(get_db_session),
) -> DoctorResponse:
    """Register professional details for doctor account."""
    service = DoctorService(db)
    doctor = await service.create_doctor_profile(current_user.id, request)
    return DoctorResponse.model_validate(doctor)


@router.patch(
    "/me",
    response_model=DoctorResponse,
    summary="Update current user's doctor profile",
)
async def update_my_doctor_profile(
    request: DoctorUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: AsyncSession = Depends(get_db_session),
) -> DoctorResponse:
    """Update professional details for authenticated doctor caller."""
    service = DoctorService(db)
    doctor = await service.update_my_doctor_profile(current_user.id, request)
    return DoctorResponse.model_validate(doctor)

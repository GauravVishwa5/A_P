"""FastAPI REST router for medical prescriptions."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import UserRole
from app.core.database import get_db_session
from app.core.dependencies import get_current_user, require_roles
from app.modules.auth.models import User
from app.modules.prescriptions.schemas import (
    PrescriptionCreateRequest,
    PrescriptionResponse,
)
from app.modules.prescriptions.service import PrescriptionService

router = APIRouter(tags=["Prescriptions"])


@router.post(
    "/api/v1/consultations/{consultation_id}/prescriptions",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue prescription for consultation (Doctor-only)",
)
async def issue_prescription(
    consultation_id: UUID,
    request: PrescriptionCreateRequest,
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: AsyncSession = Depends(get_db_session),
) -> PrescriptionResponse:
    """Create an immutable clinical prescription for a completed or in-progress encounter."""
    service = PrescriptionService(db)
    return await service.issue_prescription(
        consultation_id=consultation_id,
        request=request,
        current_user=current_user,
    )


@router.get(
    "/api/v1/consultations/{consultation_id}/prescriptions",
    response_model=PrescriptionResponse,
    summary="Get prescription for a consultation",
)
async def get_consultation_prescription(
    consultation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> PrescriptionResponse:
    """Retrieve prescription issued for a specific consultation."""
    service = PrescriptionService(db)
    return await service.get_prescription_by_consultation(
        consultation_id=consultation_id,
        current_user=current_user,
    )


@router.get(
    "/api/v1/prescriptions/{prescription_id}",
    response_model=PrescriptionResponse,
    summary="Get prescription details by ID",
)
async def get_prescription_by_id(
    prescription_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> PrescriptionResponse:
    """Retrieve digital prescription by primary key with IDOR authorization."""
    service = PrescriptionService(db)
    return await service.get_prescription_by_id(
        prescription_id=prescription_id,
        current_user=current_user,
    )

"""FastAPI REST router for payment processing and refund endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import UserRole
from app.common.exceptions import BadRequestException
from app.core.database import get_db_session
from app.core.dependencies import get_current_user, require_roles
from app.modules.auth.models import User
from app.modules.payments.schemas import (
    PaymentInitiateRequest,
    PaymentRefundRequest,
    PaymentResponse,
)
from app.modules.payments.service import PaymentService

router = APIRouter(tags=["Payments"])


@router.post(
    "/api/v1/consultations/{consultation_id}/payments",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process consultation payment with idempotency",
)
async def process_consultation_payment(
    consultation_id: UUID,
    request: PaymentInitiateRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Unique client key for payment deduplication",
    ),
    current_user: User = Depends(require_roles(UserRole.PATIENT)),
    db: AsyncSession = Depends(get_db_session),
) -> PaymentResponse:
    """Charge for an upcoming consultation with strict idempotency and decoupled gateway calls."""
    if not idempotency_key or not idempotency_key.strip():
        raise BadRequestException(
            "Idempotency-Key header is required for payment processing",
            error_code="MISSING_IDEMPOTENCY_KEY",
        )

    service = PaymentService(db)
    return await service.initiate_payment(
        consultation_id=consultation_id,
        request=request,
        idempotency_key=idempotency_key.strip(),
        current_user=current_user,
    )


@router.get(
    "/api/v1/consultations/{consultation_id}/payments",
    response_model=list[PaymentResponse],
    summary="List payment attempts for a consultation",
)
async def list_consultation_payments(
    consultation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[PaymentResponse]:
    """Retrieve payment transaction history for a consultation."""
    service = PaymentService(db)
    return await service.list_payments_for_consultation(
        consultation_id=consultation_id,
        current_user=current_user,
    )


@router.post(
    "/api/v1/payments/{payment_id}/refund",
    response_model=PaymentResponse,
    summary="Refund settled payment (Admin-only)",
)
async def refund_payment(
    payment_id: UUID,
    request: PaymentRefundRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db_session),
) -> PaymentResponse:
    """Issue refund for a previously captured consultation payment."""
    service = PaymentService(db)
    return await service.refund_payment(
        payment_id=payment_id,
        request=request,
        current_user=current_user,
    )

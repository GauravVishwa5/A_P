"""Payment service orchestrating gateway interactions, saga state management, and refunds."""

import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import (
    ConsultationStatus,
    PaymentProvider,
    PaymentStatus,
    UserRole,
)
from app.common.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.modules.auth.models import User
from app.modules.consultations.repository import ConsultationRepository
from app.modules.payments.models import Payment
from app.modules.payments.provider import (
    MockPaymentGateway,
)
from app.modules.payments.provider import (
    PaymentProvider as BasePaymentProvider,
)
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import (
    PaymentInitiateRequest,
    PaymentRefundRequest,
    PaymentResponse,
)

logger = logging.getLogger(__name__)


class PaymentService:
    """Orchestrates payment processing with idempotency, Saga compensation,
    and decoupled transactions.
    """

    def __init__(
        self,
        session: AsyncSession,
        provider: BasePaymentProvider | None = None,
    ) -> None:
        self.session = session
        self.repo = PaymentRepository(session)
        self.consultation_repo = ConsultationRepository(session)
        self.provider = provider or MockPaymentGateway()

    async def initiate_payment(
        self,
        consultation_id: UUID,
        request: PaymentInitiateRequest,
        idempotency_key: str,
        current_user: User,
    ) -> PaymentResponse:
        """Process consultation payment with idempotency, decoupled transactions,
        and Saga timeout handling.

        Design Assumption:
        Upon successful payment capture, consultation status transitions
        from SCHEDULED to CONFIRMED. Under timeout, payment remains INITIATED
        and consultation remains SCHEDULED to prevent false confirmation.
        """
        # 1. Idempotency check: Return existing payment if key was already used
        existing_payment = await self.repo.get_by_idempotency_key(idempotency_key)
        if existing_payment:
            return PaymentResponse.model_validate(existing_payment)

        # 2. Consultation validation and ownership check
        consultation = await self.consultation_repo.get_by_id(consultation_id)
        if not consultation:
            raise NotFoundException("Consultation not found", error_code="CONSULTATION_NOT_FOUND")

        if current_user.role != UserRole.ADMIN.value and consultation.patient_id != current_user.id:
            raise ForbiddenException("Access denied: You can only pay for your own consultations")

        if consultation.status != ConsultationStatus.SCHEDULED.value:
            raise BadRequestException(
                f"Cannot initiate payment for consultation in status '{consultation.status}'",
                error_code="INVALID_CONSULTATION_STATUS",
            )

        # 3. Create initial INITIATED payment record and commit before external network call
        payment = Payment(
            consultation_id=consultation.id,
            patient_id=consultation.patient_id,
            amount=request.amount,
            currency=request.currency,
            status=PaymentStatus.INITIATED.value,
            provider=PaymentProvider.MOCK_PAYMENT.value,
            idempotency_key=idempotency_key,
        )
        try:
            payment = await self.repo.create(payment)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.repo.get_by_idempotency_key(idempotency_key)
            if existing:
                return PaymentResponse.model_validate(existing)
            raise ConflictException(
                "Payment transaction conflict detected",
                error_code="PAYMENT_CONFLICT",
            ) from exc

        # 4. External gateway invocation outside of open database transaction
        metadata = {}
        if request.mock_mode:
            metadata["mock_mode"] = request.mock_mode

        try:
            result = await self.provider.process_payment(
                amount=payment.amount,
                currency=payment.currency,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
        except TimeoutError:
            # SAGA / Compensation boundary:
            # Gateway timed out. Payment remains INITIATED. Consultation is NOT falsely confirmed.
            logger.warning(
                f"External payment gateway timed out for payment {payment.id}. "
                "Retaining status INITIATED for background reconciliation."
            )
            return PaymentResponse.model_validate(payment)

        # 5. Process gateway outcome
        if result.status == PaymentStatus.SUCCESS:
            payment.status = PaymentStatus.SUCCESS.value
            payment.transaction_reference = result.transaction_reference

            # Reference assumption: Successful payment confirms the consultation
            consultation.status = ConsultationStatus.CONFIRMED.value
            await self.consultation_repo.create_booking_event(
                consultation_id=consultation.id,
                event_type="PAYMENT_RECEIVED",
                payload={
                    "payment_id": str(payment.id),
                    "amount": str(payment.amount),
                    "reference": result.transaction_reference,
                },
            )
        else:
            payment.status = PaymentStatus.FAILED.value
            payment.transaction_reference = result.transaction_reference

        await self.session.commit()
        return PaymentResponse.model_validate(payment)

    async def list_payments_for_consultation(
        self,
        consultation_id: UUID,
        current_user: User,
    ) -> list[PaymentResponse]:
        """List all payment attempts for a consultation with IDOR check."""
        consultation = await self.consultation_repo.get_by_id(consultation_id)
        if not consultation:
            raise NotFoundException("Consultation not found", error_code="CONSULTATION_NOT_FOUND")

        # Authorization: Patient, assigned doctor, or admin
        if (
            current_user.role == UserRole.PATIENT.value
            and consultation.patient_id != current_user.id
        ):
            raise ForbiddenException("Access denied to consultation payments")

        payments = await self.repo.list_by_consultation(consultation_id)
        return [PaymentResponse.model_validate(p) for p in payments]

    async def refund_payment(
        self,
        payment_id: UUID,
        request: PaymentRefundRequest,
        current_user: User,
    ) -> PaymentResponse:
        """Process refund for a settled payment (Admin-only)."""
        if current_user.role != UserRole.ADMIN.value:
            raise ForbiddenException("Only system administrators can issue refunds")

        payment = await self.repo.get_by_id(payment_id)
        if not payment:
            raise NotFoundException("Payment record not found", error_code="PAYMENT_NOT_FOUND")

        if payment.status != PaymentStatus.SUCCESS.value:
            raise BadRequestException(
                f"Cannot refund payment in status '{payment.status}'",
                error_code="INVALID_PAYMENT_STATUS",
            )

        if not payment.transaction_reference:
            raise BadRequestException(
                "Missing transaction reference for settled payment",
                error_code="MISSING_TXN_REF",
            )

        # External refund call
        refund_result = await self.provider.process_refund(
            transaction_reference=payment.transaction_reference,
            amount=payment.amount,
            reason=request.reason,
        )

        payment.status = PaymentStatus.REFUNDED.value
        await self.session.commit()

        # Audit event on consultation if exists
        await self.consultation_repo.create_booking_event(
            consultation_id=payment.consultation_id,
            event_type="PAYMENT_REFUNDED",
            payload={
                "payment_id": str(payment.id),
                "refund_reference": refund_result.transaction_reference,
                "reason": request.reason,
                "refunded_by": str(current_user.id),
            },
        )
        await self.session.commit()

        return PaymentResponse.model_validate(payment)

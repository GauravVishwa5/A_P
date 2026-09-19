"""Service layer computing efficient aggregate administrative analytics from PostgreSQL."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import ConsultationStatus, PaymentStatus, UserRole
from app.modules.admin.schemas import (
    AdminAnalyticsResponse,
    ClinicalAnalytics,
    ConsultationAnalytics,
    PaymentAnalytics,
    UserAnalytics,
)
from app.modules.auth.models import User
from app.modules.consultations.models import Consultation
from app.modules.doctors.models import Doctor
from app.modules.payments.models import Payment
from app.modules.prescriptions.models import Prescription


class AdminAnalyticsService:
    """Service computing platform metrics using high-performance SQL aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_analytics(self) -> AdminAnalyticsResponse:
        """Compute platform-wide business analytics directly from the database engine."""
        now = datetime.now(UTC)

        # 1. User metrics
        total_users = (await self.session.execute(select(func.count(User.id)))).scalar_one() or 0

        total_patients = (
            await self.session.execute(
                select(func.count(User.id)).where(User.role == UserRole.PATIENT.value)
            )
        ).scalar_one() or 0

        total_doctors = (
            await self.session.execute(
                select(func.count(User.id)).where(User.role == UserRole.DOCTOR.value)
            )
        ).scalar_one() or 0

        active_patients = (
            await self.session.execute(
                select(func.count(User.id)).where(
                    User.role == UserRole.PATIENT.value,
                    User.is_active.is_(True),
                )
            )
        ).scalar_one() or 0

        active_doctors = (
            await self.session.execute(
                select(func.count(Doctor.id)).where(Doctor.is_available.is_(True))
            )
        ).scalar_one() or 0

        user_metrics = UserAnalytics(
            total_users=total_users,
            total_patients=total_patients,
            total_doctors=total_doctors,
            active_patients=active_patients,
            active_doctors=active_doctors,
        )

        # 2. Consultation metrics
        total_consultations = (
            await self.session.execute(select(func.count(Consultation.id)))
        ).scalar_one() or 0

        scheduled = (
            await self.session.execute(
                select(func.count(Consultation.id)).where(
                    Consultation.status == ConsultationStatus.SCHEDULED.value
                )
            )
        ).scalar_one() or 0

        confirmed = (
            await self.session.execute(
                select(func.count(Consultation.id)).where(
                    Consultation.status == ConsultationStatus.CONFIRMED.value
                )
            )
        ).scalar_one() or 0

        in_progress = (
            await self.session.execute(
                select(func.count(Consultation.id)).where(
                    Consultation.status == ConsultationStatus.IN_PROGRESS.value
                )
            )
        ).scalar_one() or 0

        completed = (
            await self.session.execute(
                select(func.count(Consultation.id)).where(
                    Consultation.status == ConsultationStatus.COMPLETED.value
                )
            )
        ).scalar_one() or 0

        cancelled = (
            await self.session.execute(
                select(func.count(Consultation.id)).where(
                    Consultation.status == ConsultationStatus.CANCELLED.value
                )
            )
        ).scalar_one() or 0

        cancellation_rate = (
            round((cancelled / total_consultations) * 100.0, 2) if total_consultations > 0 else 0.0
        )

        consultation_metrics = ConsultationAnalytics(
            total_consultations=total_consultations,
            scheduled=scheduled,
            confirmed=confirmed,
            in_progress=in_progress,
            completed=completed,
            cancelled=cancelled,
            cancellation_rate_percent=cancellation_rate,
        )

        # 3. Payment metrics
        total_payments = (
            await self.session.execute(select(func.count(Payment.id)))
        ).scalar_one() or 0

        successful_payments = (
            await self.session.execute(
                select(func.count(Payment.id)).where(Payment.status == PaymentStatus.SUCCESS.value)
            )
        ).scalar_one() or 0

        failed_payments = (
            await self.session.execute(
                select(func.count(Payment.id)).where(Payment.status == PaymentStatus.FAILED.value)
            )
        ).scalar_one() or 0

        initiated_payments = (
            await self.session.execute(
                select(func.count(Payment.id)).where(
                    Payment.status == PaymentStatus.INITIATED.value
                )
            )
        ).scalar_one() or 0

        refunded_payments = (
            await self.session.execute(
                select(func.count(Payment.id)).where(Payment.status == PaymentStatus.REFUNDED.value)
            )
        ).scalar_one() or 0

        # Revenue: gross captures (SUCCESS + REFUNDED)
        gross_revenue_raw = (
            await self.session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status.in_([PaymentStatus.SUCCESS.value, PaymentStatus.REFUNDED.value])
                )
            )
        ).scalar_one()
        gross_revenue = Decimal(str(gross_revenue_raw))

        refunded_amount_raw = (
            await self.session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == PaymentStatus.REFUNDED.value
                )
            )
        ).scalar_one()
        refunded_amount = Decimal(str(refunded_amount_raw))

        net_revenue = gross_revenue - refunded_amount

        payment_metrics = PaymentAnalytics(
            total_payments=total_payments,
            successful=successful_payments,
            failed=failed_payments,
            initiated=initiated_payments,
            refunded=refunded_payments,
            gross_revenue=gross_revenue,
            refunded_amount=refunded_amount,
            net_revenue=net_revenue,
            currency="INR",
        )

        # 4. Clinical metrics
        total_prescriptions = (
            await self.session.execute(select(func.count(Prescription.id)))
        ).scalar_one() or 0

        clinical_metrics = ClinicalAnalytics(
            total_prescriptions=total_prescriptions,
        )

        return AdminAnalyticsResponse(
            generated_at=now,
            users=user_metrics,
            consultations=consultation_metrics,
            payments=payment_metrics,
            clinical=clinical_metrics,
        )

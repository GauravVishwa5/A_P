"""ARQ background worker for notification delivery and payment reconciliation."""

import asyncio
import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from arq.typing import WorkerSettingsBase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.constants import ConsultationStatus, PaymentStatus
from app.common.utils import utcnow
from app.core.config import get_settings
from app.modules.consultations.models import BookingEvent, Consultation
from app.modules.notifications.service import NotificationService
from app.modules.payments.models import Payment
from app.modules.payments.provider import MockPaymentGateway

logger = logging.getLogger("app.workers")


async def startup(ctx: dict[Any, Any]) -> None:
    """Initialize database sessionmaker on worker process startup."""
    settings = get_settings()
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    ctx["engine"] = engine
    ctx["session_maker"] = session_maker
    ctx["payment_provider"] = MockPaymentGateway()
    logger.info("Worker process initialized with database engine")


async def shutdown(ctx: dict[Any, Any]) -> None:
    """Gracefully dispose database engine on worker shutdown."""
    engine = ctx.get("engine")
    if engine:
        await engine.dispose()
    logger.info("Worker process shut down cleanly")


async def send_notification_job(ctx: dict[Any, Any], notification_id: str) -> bool:
    """Asynchronously deliver a queued notification with retry simulation."""
    session_maker: async_sessionmaker[AsyncSession] = ctx["session_maker"]
    nid = UUID(notification_id)

    async with session_maker() as session:
        service = NotificationService(session)
        try:
            # Simulate network dispatch (e.g. SES or Twilio)
            await asyncio.sleep(0.05)
            await service.mark_delivered(nid)
            logger.info(f"Worker delivered notification {notification_id}")
            return True
        except Exception as exc:
            logger.error(f"Failed to deliver notification {notification_id}: {exc}")
            await service.mark_failed(nid)
            raise


async def reconcile_stuck_payments_job(ctx: dict[Any, Any]) -> int:
    """Periodic cron job scanning for INITIATED payments past timeout threshold."""
    session_maker: async_sessionmaker[AsyncSession] = ctx["session_maker"]
    cutoff_time = utcnow() - timedelta(minutes=5)
    reconciled_count = 0

    async with session_maker() as session:
        # Find initiated payments older than cutoff
        stmt = (
            select(Payment)
            .where(
                Payment.status == PaymentStatus.INITIATED.value,
                Payment.created_at <= cutoff_time,
            )
            .limit(50)
        )
        result = await session.execute(stmt)
        stuck_payments = result.scalars().all()

        for payment in stuck_payments:
            logger.info(f"Reconciling stuck payment: id={payment.id} amount={payment.amount}")
            # In production, query external payment gateway by payment.idempotency_key
            # For mock/simulation, expired initiated payments are marked FAILED to free state
            payment.status = PaymentStatus.FAILED.value

            consultation = await session.get(Consultation, payment.consultation_id)
            if consultation and consultation.status == ConsultationStatus.SCHEDULED.value:
                event = BookingEvent(
                    consultation_id=consultation.id,
                    event_type="PAYMENT_RECONCILIATION_FAILED",
                    payload={"payment_id": str(payment.id), "reason": "Gateway timeout exceeded"},
                )
                session.add(event)

            reconciled_count += 1

        if reconciled_count > 0:
            await session.commit()
            logger.info(f"Reconciled {reconciled_count} stuck payments")

    return reconciled_count


settings = get_settings()


class WorkerSettings(WorkerSettingsBase):
    """ARQ Worker configuration specification."""

    functions = [send_notification_job, reconcile_stuck_payments_job]
    cron_jobs = [
        cron(reconcile_stuck_payments_job, minute=set(range(0, 60, 5))),
    ]
    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
    on_startup = startup  # type: ignore[assignment]
    on_shutdown = shutdown  # type: ignore[assignment]
    max_jobs = 20
    job_timeout = 300


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)

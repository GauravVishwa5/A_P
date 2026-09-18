"""Database repository for payment ledger persistence and queries."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Payment


class PaymentRepository:
    """Encapsulates transactional database access for payment records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payment: Payment) -> Payment:
        """Persist a newly initiated payment."""
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        """Retrieve payment by primary key."""
        stmt = select(Payment).where(Payment.id == payment_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        """Retrieve payment by client idempotency key."""
        stmt = select(Payment).where(Payment.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_consultation(self, consultation_id: UUID) -> list[Payment]:
        """Query all payment attempts for a consultation."""
        stmt = (
            select(Payment)
            .where(Payment.consultation_id == consultation_id)
            .order_by(Payment.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, payment: Payment) -> Payment:
        """Flush changes to existing payment record."""
        await self.session.flush()
        return payment

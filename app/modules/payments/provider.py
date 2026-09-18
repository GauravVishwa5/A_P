"""Payment gateway provider abstractions and deterministic mock implementations."""

import asyncio
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from app.common.constants import PaymentStatus


class PaymentResult(BaseModel):
    """Normalized payment transaction outcome."""

    status: PaymentStatus
    transaction_reference: str
    message: str
    raw_response: dict[str, Any]


class PaymentProvider(ABC):
    """Abstract interface decoupling business services from third-party payment gateways."""

    @abstractmethod
    async def process_payment(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        """Process charge with external payment network."""
        pass

    @abstractmethod
    async def process_refund(
        self,
        transaction_reference: str,
        amount: Decimal,
        reason: str | None = None,
    ) -> PaymentResult:
        """Process refund with external payment network."""
        pass


class MockPaymentGateway(PaymentProvider):
    """High-fidelity mock gateway supporting success, failure, and timeout scenarios."""

    def __init__(self, mode: str = "SUCCESS", latency_ms: int = 10) -> None:
        self.mode = mode.upper()
        self.latency_ms = latency_ms

    async def process_payment(
        self,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        """Simulate external gateway charge processing."""
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        # Allow mode override via metadata if provided by test harness
        active_mode = metadata.get("mock_mode", self.mode).upper() if metadata else self.mode

        if active_mode == "TIMEOUT":
            raise TimeoutError("External payment gateway did not respond within configured timeout")

        if active_mode == "FAILURE":
            return PaymentResult(
                status=PaymentStatus.FAILED,
                transaction_reference=f"MOCK-FAIL-{uuid4().hex[:12].upper()}",
                message="Payment declined by mock issuing bank",
                raw_response={"code": "CARD_DECLINED", "declined": True},
            )

        # Default: SUCCESS
        return PaymentResult(
            status=PaymentStatus.SUCCESS,
            transaction_reference=f"MOCK-TXN-{uuid4().hex[:12].upper()}",
            message="Payment captured successfully",
            raw_response={
                "code": "00",
                "approved": True,
                "amount": str(amount),
                "currency": currency,
            },
        )

    async def process_refund(
        self,
        transaction_reference: str,
        amount: Decimal,
        reason: str | None = None,
    ) -> PaymentResult:
        """Simulate refund processing."""
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        return PaymentResult(
            status=PaymentStatus.REFUNDED,
            transaction_reference=f"MOCK-REF-{uuid4().hex[:12].upper()}",
            message="Refund processed successfully",
            raw_response={
                "original_txn": transaction_reference,
                "refund_amount": str(amount),
                "reason": reason,
            },
        )

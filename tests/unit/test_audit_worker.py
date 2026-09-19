"""Unit and integration tests for Audit, Worker, and Observability infrastructure."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import NotificationChannel, NotificationStatus, PaymentStatus, UserRole
from app.core.tracing import get_current_trace_context, setup_tracing
from app.modules.audit.service import AuditService
from app.modules.auth.models import User
from app.modules.availability.models import AvailabilitySlot
from app.modules.consultations.models import Consultation
from app.modules.doctors.models import Doctor
from app.modules.notifications.service import NotificationService
from app.modules.payments.models import Payment
from app.workers.worker import reconcile_stuck_payments_job, send_notification_job


async def get_token_for(async_client: AsyncClient, email: str, password: str, role: str) -> str:
    """Helper to register and log in a user, returning access token."""
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "role": role},
    )
    assert reg.status_code == 201

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    return login.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_audit_service_and_api(db_session: AsyncSession, async_client: AsyncClient):
    """Verify audit record creation, filtering, and admin-only API access."""
    audit_service = AuditService(db_session)
    actor_id = uuid4()

    # 1. Record compliance events
    log1 = await audit_service.record_event(
        action="USER_LOGIN",
        resource_type="USER",
        resource_id=str(actor_id),
        status="SUCCESS",
        actor_id=actor_id,
        actor_role=UserRole.PATIENT.value,
        ip_address="192.168.1.10",
        metadata={"auth_method": "PASSWORD"},
    )
    log2 = await audit_service.record_event(
        action="CONSULTATION_BOOKED",
        resource_type="CONSULTATION",
        resource_id=str(uuid4()),
        status="SUCCESS",
        actor_id=actor_id,
        actor_role=UserRole.PATIENT.value,
        ip_address="192.168.1.10",
    )
    await db_session.commit()
    assert log1.id is not None
    assert log2.id is not None

    # 2. Query via service
    res = await audit_service.list_audit_logs()
    assert res.total >= 2

    # 3. Test API endpoint access control
    patient_token = await get_token_for(
        async_client,
        f"patient.audit.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    admin_token = await get_token_for(
        async_client,
        f"admin.audit.{uuid4().hex[:6]}@amrutam.co.in",
        "SecurePassword123!",
        UserRole.ADMIN.value,
    )

    # Patient -> 403 Forbidden
    forbidden_res = await async_client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert forbidden_res.status_code == 403

    # Admin -> 200 OK
    admin_res = await async_client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_res.status_code == 200
    data = admin_res.json()
    assert "items" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_notification_service_and_worker_job(db_session: AsyncSession):
    """Verify notification queueing and ARQ worker delivery execution."""
    notification_service = NotificationService(db_session)
    recipient_id = uuid4()

    # Need user in DB for foreign key constraint if enforced
    user = User(
        id=recipient_id,
        email=f"notif.{uuid4().hex[:6]}@example.com",
        password_hash="dummy_hash",
        role=UserRole.PATIENT.value,
    )
    db_session.add(user)
    await db_session.commit()

    # Enqueue notification
    notif = await notification_service.enqueue_notification(
        recipient_id=recipient_id,
        type_="BOOKING_CONFIRMATION",
        title="Consultation Confirmed",
        body="Your Ayurveda consultation has been scheduled.",
        channel=NotificationChannel.EMAIL,
    )
    await db_session.commit()
    assert notif.status == NotificationStatus.PENDING.value

    # Execute worker job with mock session maker context
    class MockSessionMaker:
        def __init__(self, session: AsyncSession) -> None:
            self.session = session

        def __call__(self):
            return self

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    ctx = {"session_maker": MockSessionMaker(db_session)}
    delivered = await send_notification_job(ctx, str(notif.id))
    assert delivered is True

    # Verify status changed to SENT
    refreshed = await notification_service.repo.get_by_id(notif.id)
    assert refreshed is not None
    assert refreshed.status == NotificationStatus.SENT.value
    assert refreshed.sent_at is not None


@pytest.mark.asyncio
async def test_worker_reconcile_stuck_payments(db_session: AsyncSession):
    """Verify ARQ worker reconciliation job identifies and expires stuck INITIATED payments."""
    patient_id = uuid4()
    doc_user_id = uuid4()

    patient = User(
        id=patient_id,
        email=f"pat.rec.{uuid4().hex[:6]}@example.com",
        password_hash="dummy",
        role=UserRole.PATIENT.value,
    )
    doc_user = User(
        id=doc_user_id,
        email=f"doc.rec.{uuid4().hex[:6]}@example.com",
        password_hash="dummy",
        role=UserRole.DOCTOR.value,
    )
    db_session.add_all([patient, doc_user])
    await db_session.flush()

    doctor = Doctor(
        user_id=doc_user_id,
        license_number=f"LIC-REC-{uuid4().hex[:6]}",
        specialization="Dravyaguna",
        experience_years=5,
        consultation_fee=500.0,
        languages=["English"],
    )
    db_session.add(doctor)
    await db_session.flush()

    slot = AvailabilitySlot(
        doctor_id=doctor.id,
        start_time=datetime.now(UTC) + timedelta(days=1),
        end_time=datetime.now(UTC) + timedelta(days=1, minutes=30),
        status="BOOKED",
    )
    db_session.add(slot)
    await db_session.flush()

    consultation = Consultation(
        patient_id=patient.id,
        doctor_id=doctor.id,
        availability_slot_id=slot.id,
        scheduled_start=slot.start_time,
        scheduled_end=slot.end_time,
        status="SCHEDULED",
    )
    db_session.add(consultation)
    await db_session.flush()

    # Create a stuck payment created 10 minutes ago
    stuck_payment = Payment(
        consultation_id=consultation.id,
        patient_id=patient.id,
        amount=500.00,
        currency="INR",
        status=PaymentStatus.INITIATED.value,
        provider="MOCK_PAYMENT",
        idempotency_key=str(uuid4()),
        created_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db_session.add(stuck_payment)
    await db_session.commit()

    class MockSessionMaker:
        def __init__(self, session: AsyncSession) -> None:
            self.session = session

        def __call__(self):
            return self

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    ctx = {"session_maker": MockSessionMaker(db_session)}
    reconciled_count = await reconcile_stuck_payments_job(ctx)
    assert reconciled_count == 1

    # Verify payment marked FAILED
    await db_session.refresh(stuck_payment)
    assert stuck_payment.status == PaymentStatus.FAILED.value


def test_tracing_context_and_setup(app_instance):
    """Verify tracing initialization and context retrieval utility."""
    setup_tracing(app_instance, "test-service")
    ctx = get_current_trace_context()
    assert isinstance(ctx, dict)

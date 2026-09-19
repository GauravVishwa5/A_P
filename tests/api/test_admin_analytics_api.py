"""Comprehensive tests for Admin Business Analytics and JWT Multi-Key Rotation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from jose import jwt

from app.common.constants import ConsultationStatus, PaymentStatus, UserRole
from app.core.config import get_settings
from app.core.security import create_jwt_token, decode_jwt_token
from app.modules.auth.models import User
from app.modules.availability.models import AvailabilitySlot
from app.modules.consultations.models import Consultation
from app.modules.doctors.models import Doctor
from app.modules.payments.models import Payment
from app.modules.prescriptions.models import Prescription
from tests.conftest import db_session_factory

settings = get_settings()


@pytest.mark.asyncio
async def test_admin_analytics_unauthenticated(async_client: AsyncClient) -> None:
    """Verify unauthenticated requests to admin analytics are rejected with 401."""
    response = await async_client.get("/api/v1/admin/analytics")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_analytics_forbidden_for_patient(async_client: AsyncClient) -> None:
    """Verify PATIENT role cannot access admin analytics and receives 403."""
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"patient_analytics_{uuid4().hex[:6]}@test.com",
            "password": "SecurePassword123!",
            "role": UserRole.PATIENT.value,
        },
    )
    assert reg.status_code == 201

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": reg.json()["email"], "password": "SecurePassword123!"},
    )
    token = login.json()["tokens"]["access_token"]

    response = await async_client.get(
        "/api/v1/admin/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_analytics_forbidden_for_doctor(async_client: AsyncClient) -> None:
    """Verify DOCTOR role cannot access admin analytics and receives 403."""
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"doctor_analytics_{uuid4().hex[:6]}@test.com",
            "password": "SecurePassword123!",
            "role": UserRole.DOCTOR.value,
        },
    )
    assert reg.status_code == 201

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": reg.json()["email"], "password": "SecurePassword123!"},
    )
    token = login.json()["tokens"]["access_token"]

    response = await async_client.get(
        "/api/v1/admin/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_analytics_success_and_aggregations(async_client: AsyncClient) -> None:
    """Verify ADMIN role receives aggregate platform analytics computed from database."""
    # 1. Register and authenticate an ADMIN user
    admin_reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"admin_analytics_{uuid4().hex[:6]}@test.com",
            "password": "AdminPassword123!",
            "role": UserRole.ADMIN.value,
        },
    )
    assert admin_reg.status_code == 201

    admin_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_reg.json()["email"], "password": "AdminPassword123!"},
    )
    admin_token = admin_login.json()["tokens"]["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Query analytics initially
    res_initial = await async_client.get("/api/v1/admin/analytics", headers=admin_headers)
    assert res_initial.status_code == 200
    data_initial = res_initial.json()

    assert "generated_at" in data_initial
    assert "users" in data_initial
    assert "consultations" in data_initial
    assert "payments" in data_initial
    assert "clinical" in data_initial

    # 3. Seed controlled entities via database
    async with db_session_factory() as session:
        # Create a doctor user and doctor record
        doc_user = User(
            email=f"doc_agg_{uuid4().hex[:6]}@test.com",
            password_hash="mock_hash",
            role=UserRole.DOCTOR.value,
            is_active=True,
        )
        session.add(doc_user)
        await session.flush()

        doc = Doctor(
            user_id=doc_user.id,
            specialization="Ayurveda",
            license_number=f"LIC-AGG-{uuid4().hex[:6]}",
            experience_years=5,
            consultation_fee=Decimal("500.00"),
            is_available=True,
        )
        session.add(doc)
        await session.flush()

        # Create patient user
        pat_user = User(
            email=f"pat_agg_{uuid4().hex[:6]}@test.com",
            password_hash="mock_hash",
            role=UserRole.PATIENT.value,
            is_active=True,
        )
        session.add(pat_user)
        await session.flush()

        # Create availability slot
        slot = AvailabilitySlot(
            doctor_id=doc.id,
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            status="BOOKED",
        )
        session.add(slot)
        await session.flush()

        # Create completed consultation
        consultation = Consultation(
            patient_id=pat_user.id,
            doctor_id=doc.id,
            availability_slot_id=slot.id,
            status=ConsultationStatus.COMPLETED.value,
            scheduled_start=slot.start_time,
            scheduled_end=slot.end_time,
        )
        session.add(consultation)
        await session.flush()

        # Create payment
        payment = Payment(
            consultation_id=consultation.id,
            patient_id=pat_user.id,
            amount=Decimal("500.00"),
            currency="INR",
            status=PaymentStatus.SUCCESS.value,
            transaction_reference=f"TXN-AGG-{uuid4().hex[:8]}",
        )
        session.add(payment)

        # Create prescription
        prescription = Prescription(
            consultation_id=consultation.id,
            doctor_id=doc.id,
            patient_id=pat_user.id,
            diagnosis="Vata dosha imbalance",
            medications=[{"name": "Ashwagandha", "dosage": "500mg"}],
        )
        session.add(prescription)
        await session.commit()

    # 4. Fetch updated analytics and verify aggregations
    res_updated = await async_client.get("/api/v1/admin/analytics", headers=admin_headers)
    assert res_updated.status_code == 200
    data = res_updated.json()

    assert data["users"]["total_users"] >= 3
    assert data["users"]["total_patients"] >= 1
    assert data["users"]["total_doctors"] >= 1
    assert data["users"]["active_doctors"] >= 1

    assert data["consultations"]["total_consultations"] >= 1
    assert data["consultations"]["completed"] >= 1

    assert data["payments"]["total_payments"] >= 1
    assert data["payments"]["successful"] >= 1
    assert float(data["payments"]["gross_revenue"]) >= 500.0
    assert float(data["payments"]["net_revenue"]) >= 500.0
    assert data["payments"]["currency"] == "INR"

    assert data["clinical"]["total_prescriptions"] >= 1


def test_jwt_multi_key_rotation_and_verification() -> None:
    """Verify JWT key rotation with multi-key registry and grace-period acceptance."""
    # 1. Generate active token with current kid
    active_token = create_jwt_token(
        subject=uuid4(),
        role=UserRole.PATIENT.value,
        email="patient.active@test.com",
    )
    decoded_active = decode_jwt_token(active_token)
    assert decoded_active["email"] == "patient.active@test.com"

    # 2. Simulate a previous key configured in settings.JWT_PREVIOUS_KEYS
    old_kid = "v0"
    old_secret = "old-secret-key-from-previous-rotation-epoch!!"
    settings.JWT_PREVIOUS_KEYS[old_kid] = old_secret

    # Generate token signed with the previous key
    now = datetime.now(UTC)
    old_payload = {
        "sub": str(uuid4()),
        "role": UserRole.DOCTOR.value,
        "email": "doctor.previous@test.com",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "iss": settings.APP_NAME,
    }
    old_token = jwt.encode(
        old_payload,
        old_secret,
        algorithm="HS256",
        headers={"kid": old_kid, "alg": "HS256"},
    )

    # Decode old token: must successfully validate using the previous key registry
    decoded_old = decode_jwt_token(old_token)
    assert decoded_old["email"] == "doctor.previous@test.com"
    assert decoded_old["role"] == UserRole.DOCTOR.value

    # 3. Unknown kid must be rejected with INVALID_TOKEN_KID
    unrecognized_token = jwt.encode(
        old_payload,
        "random-key",
        algorithm="HS256",
        headers={"kid": "unknown-kid-v99", "alg": "HS256"},
    )
    with pytest.raises(Exception) as exc_info:
        decode_jwt_token(unrecognized_token)
    assert "INVALID_TOKEN_KID" in str(exc_info.value) or "Unrecognized" in str(exc_info.value)

    # 4. Token without kid must be rejected
    missing_kid_token = jwt.encode(
        old_payload,
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(Exception) as exc_info2:
        decode_jwt_token(missing_kid_token)
    assert "MISSING_TOKEN_KID" in str(exc_info2.value) or "missing" in str(exc_info2.value).lower()

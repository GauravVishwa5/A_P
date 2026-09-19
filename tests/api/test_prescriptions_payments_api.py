"""Integration tests for Prescriptions and Payments domain APIs."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.common.constants import ConsultationStatus, PaymentStatus, UserRole


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


async def setup_doctor_and_slot(async_client: AsyncClient) -> tuple[str, str, str]:
    """Helper to set up an active doctor with an availability slot.

    Returns (doc_token, doctor_id, slot_id).
    """
    doc_token = await get_token_for(
        async_client,
        f"dr.rx.{uuid4().hex[:6]}@amrutam.co.in",
        "SecurePassword123!",
        UserRole.DOCTOR.value,
    )
    headers = {"Authorization": f"Bearer {doc_token}"}

    doc_res = await async_client.post(
        "/api/v1/doctors/me",
        json={
            "license_number": f"LIC-{uuid4().hex[:8]}",
            "specialization": "Kayachikitsa",
            "languages": ["English", "Sanskrit"],
            "experience_years": 8,
            "consultation_fee": "750.00",
        },
        headers=headers,
    )
    assert doc_res.status_code == 201
    doctor_id = doc_res.json()["id"]

    slot_start = datetime.now(UTC) + timedelta(days=3)
    slot_end = slot_start + timedelta(minutes=30)
    slot_res = await async_client.post(
        "/api/v1/doctors/me/availability",
        json={
            "slots": [
                {
                    "start_time": slot_start.isoformat(),
                    "end_time": slot_end.isoformat(),
                }
            ]
        },
        headers=headers,
    )
    assert slot_res.status_code == 201
    slot_id = slot_res.json()[0]["id"]

    return doc_token, doctor_id, slot_id


async def book_consultation(
    async_client: AsyncClient, patient_token: str, doctor_id: str, slot_id: str
) -> dict:
    """Helper to book a consultation for a patient."""
    headers = {
        "Authorization": f"Bearer {patient_token}",
        "Idempotency-Key": str(uuid4()),
    }
    res = await async_client.post(
        "/api/v1/consultations",
        json={
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "reason": "Initial Ayurveda consultation for stress and insomnia",
        },
        headers=headers,
    )
    assert res.status_code == 201
    return res.json()


# ============================================================================
# PRESCRIPTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_prescription_lifecycle_and_immutability(async_client: AsyncClient):
    """Verify prescription creation on completed consultation and verify strict immutability."""
    doc_token, doctor_id, slot_id = await setup_doctor_and_slot(async_client)
    patient_token = await get_token_for(
        async_client,
        f"patient.rx.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )

    consultation = await book_consultation(async_client, patient_token, doctor_id, slot_id)
    consultation_id = consultation["id"]

    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    patient_headers = {"Authorization": f"Bearer {patient_token}"}

    # 1. Attempting to issue prescription while SCHEDULED fails (400)
    rx_payload = {
        "diagnosis": "Vata imbalance with Pitta aggravation",
        "notes": "Follow Sattvic diet and avoid cold foods",
        "medications": [
            {
                "name": "Ashwagandha Churna",
                "dosage": "3g",
                "frequency": "Twice daily with warm milk",
                "duration": "30 days",
                "instructions": "Take after dinner",
            }
        ],
    }
    premature_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/prescriptions",
        json=rx_payload,
        headers=doc_headers,
    )
    assert premature_res.status_code == 400
    assert premature_res.json()["error_code"] == "INVALID_CONSULTATION_STATUS"

    # 2. Advance consultation: SCHEDULED -> IN_PROGRESS -> COMPLETED
    start_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/start",
        headers=doc_headers,
    )
    assert start_res.status_code == 200

    complete_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/complete",
        headers=doc_headers,
    )
    assert complete_res.status_code == 200

    # 3. Doctor issues prescription on COMPLETED consultation (201)
    rx_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/prescriptions",
        json=rx_payload,
        headers=doc_headers,
    )
    assert rx_res.status_code == 201
    rx_data = rx_res.json()
    prescription_id = rx_data["id"]
    assert rx_data["consultation_id"] == consultation_id
    assert rx_data["diagnosis"] == rx_payload["diagnosis"]
    assert len(rx_data["medications"]) == 1
    assert rx_data["medications"][0]["name"] == "Ashwagandha Churna"

    # 4. Immutability: issuing a second prescription for the same consultation fails (409 Conflict)
    duplicate_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/prescriptions",
        json=rx_payload,
        headers=doc_headers,
    )
    assert duplicate_res.status_code == 409
    assert duplicate_res.json()["error_code"] == "PRESCRIPTION_ALREADY_EXISTS"

    # 5. Patient can view the prescription by consultation ID
    patient_get = await async_client.get(
        f"/api/v1/consultations/{consultation_id}/prescriptions",
        headers=patient_headers,
    )
    assert patient_get.status_code == 200
    assert patient_get.json()["id"] == prescription_id

    # 6. Patient can view prescription by prescription ID
    by_id_get = await async_client.get(
        f"/api/v1/prescriptions/{prescription_id}",
        headers=patient_headers,
    )
    assert by_id_get.status_code == 200
    assert by_id_get.json()["diagnosis"] == rx_payload["diagnosis"]


@pytest.mark.asyncio
async def test_prescription_idor_and_authorization(async_client: AsyncClient):
    """Verify other patients/doctors cannot access or issue prescriptions for foreign consultations.
    IDOR boundary test: wrong patient, wrong doctor both get 403.
    """
    doc_token1, doctor_id1, slot_id = await setup_doctor_and_slot(async_client)
    doc_token2, _, _ = await setup_doctor_and_slot(async_client)
    patient_token1 = await get_token_for(
        async_client,
        f"patient.idor1.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    patient_token2 = await get_token_for(
        async_client,
        f"patient.idor2.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )

    consultation = await book_consultation(async_client, patient_token1, doctor_id1, slot_id)
    consultation_id = consultation["id"]

    # Transition to IN_PROGRESS by doctor 1
    await async_client.post(
        f"/api/v1/consultations/{consultation_id}/start",
        headers={"Authorization": f"Bearer {doc_token1}"},
    )

    rx_payload = {
        "diagnosis": "Stress headache",
        "medications": [
            {
                "name": "Brahmi Vati",
                "dosage": "1 tab",
                "frequency": "Once daily",
                "duration": "14 days",
            }
        ],
    }

    # Doctor 2 tries to issue prescription for Doctor 1's consultation -> 403 Forbidden
    doc2_attempt = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/prescriptions",
        json=rx_payload,
        headers={"Authorization": f"Bearer {doc_token2}"},
    )
    assert doc2_attempt.status_code == 403

    # Patient tries to issue prescription -> 403 Forbidden
    patient_attempt = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/prescriptions",
        json=rx_payload,
        headers={"Authorization": f"Bearer {patient_token1}"},
    )
    assert patient_attempt.status_code == 403

    # Doctor 1 issues valid prescription
    issued = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/prescriptions",
        json=rx_payload,
        headers={"Authorization": f"Bearer {doc_token1}"},
    )
    assert issued.status_code == 201
    rx_id = issued.json()["id"]

    # Patient 2 tries to read Patient 1's prescription -> 403 Forbidden
    unauthorized_read = await async_client.get(
        f"/api/v1/prescriptions/{rx_id}",
        headers={"Authorization": f"Bearer {patient_token2}"},
    )
    assert unauthorized_read.status_code == 403


# ============================================================================
# PAYMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_payment_success_and_idempotency(async_client: AsyncClient):
    """Verify successful payment transitions consultation to CONFIRMED and replays idempotently."""
    _, doctor_id, slot_id = await setup_doctor_and_slot(async_client)
    patient_token = await get_token_for(
        async_client,
        f"patient.pay.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    consultation = await book_consultation(async_client, patient_token, doctor_id, slot_id)
    consultation_id = consultation["id"]

    idempotency_key = str(uuid4())
    headers = {
        "Authorization": f"Bearer {patient_token}",
        "Idempotency-Key": idempotency_key,
    }
    pay_payload = {
        "amount": "750.00",
        "currency": "INR",
        "mock_mode": "SUCCESS",
    }

    # 1. Process payment (SUCCESS)
    pay_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/payments",
        json=pay_payload,
        headers=headers,
    )
    assert pay_res.status_code == 201
    pay_data = pay_res.json()
    payment_id = pay_data["id"]
    assert pay_data["status"] == PaymentStatus.SUCCESS.value
    assert pay_data["amount"] == "750.00"
    assert pay_data["transaction_reference"].startswith("MOCK-TXN-")

    # 2. Consultation status transitioned to CONFIRMED
    consultation_res = await async_client.get(
        f"/api/v1/consultations/{consultation_id}",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert consultation_res.status_code == 200
    assert consultation_res.json()["status"] == ConsultationStatus.CONFIRMED.value

    # 3. Idempotent replay with same key returns identical payment without second charge
    replay_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/payments",
        json=pay_payload,
        headers=headers,
    )
    assert replay_res.status_code == 201
    assert replay_res.json()["id"] == payment_id
    assert replay_res.json()["status"] == PaymentStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_payment_failure_and_timeout_saga(async_client: AsyncClient):
    """Verify payment failure and gateway timeout do not falsely confirm consultation."""
    _, doc_id1, slot_id1 = await setup_doctor_and_slot(async_client)
    _, doc_id2, slot_id2 = await setup_doctor_and_slot(async_client)

    patient_token = await get_token_for(
        async_client,
        f"patient.fail.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )

    # --- Scenario A: Payment FAILURE ---
    c1 = await book_consultation(async_client, patient_token, doc_id1, slot_id1)
    c1_id = c1["id"]

    fail_res = await async_client.post(
        f"/api/v1/consultations/{c1_id}/payments",
        json={"amount": "750.00", "currency": "INR", "mock_mode": "FAILURE"},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert fail_res.status_code == 201
    assert fail_res.json()["status"] == PaymentStatus.FAILED.value

    # Consultation stays SCHEDULED (not CONFIRMED)
    c1_check = await async_client.get(
        f"/api/v1/consultations/{c1_id}",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert c1_check.json()["status"] == ConsultationStatus.SCHEDULED.value

    # --- Scenario B: Gateway TIMEOUT (Saga handling) ---
    c2 = await book_consultation(async_client, patient_token, doc_id2, slot_id2)
    c2_id = c2["id"]

    timeout_res = await async_client.post(
        f"/api/v1/consultations/{c2_id}/payments",
        json={"amount": "750.00", "currency": "INR", "mock_mode": "TIMEOUT"},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert timeout_res.status_code == 201
    # Remains INITIATED pending background reconciliation
    assert timeout_res.json()["status"] == PaymentStatus.INITIATED.value

    # Consultation stays SCHEDULED
    c2_check = await async_client.get(
        f"/api/v1/consultations/{c2_id}",
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert c2_check.json()["status"] == ConsultationStatus.SCHEDULED.value


@pytest.mark.asyncio
async def test_payment_admin_refund(async_client: AsyncClient):
    """Verify only admins can refund a captured payment and transitions to REFUNDED."""
    _, doctor_id, slot_id = await setup_doctor_and_slot(async_client)
    patient_token = await get_token_for(
        async_client,
        f"patient.ref.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    admin_token = await get_token_for(
        async_client,
        f"admin.pay.{uuid4().hex[:6]}@amrutam.co.in",
        "SecurePassword123!",
        UserRole.ADMIN.value,
    )

    consultation = await book_consultation(async_client, patient_token, doctor_id, slot_id)
    c_id = consultation["id"]

    # Capture payment
    pay_res = await async_client.post(
        f"/api/v1/consultations/{c_id}/payments",
        json={"amount": "750.00", "currency": "INR", "mock_mode": "SUCCESS"},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert pay_res.status_code == 201
    payment_id = pay_res.json()["id"]

    # 1. Non-admin attempting refund -> 403 Forbidden
    unauth_refund = await async_client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"reason": "Patient requested cancellation"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert unauth_refund.status_code == 403

    # 2. Admin refund -> 200 OK, status REFUNDED
    refund_res = await async_client.post(
        f"/api/v1/payments/{payment_id}/refund",
        json={"reason": "Administrative goodwill refund"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert refund_res.status_code == 200
    assert refund_res.json()["status"] == PaymentStatus.REFUNDED.value

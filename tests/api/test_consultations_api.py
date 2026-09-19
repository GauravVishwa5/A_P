"""API integration tests for consultation booking, idempotency, and lifecycle state transitions."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.common.constants import ConsultationStatus, SlotStatus, UserRole


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
    """Helper to set up an active doctor with a future availability slot.

    Returns (doctor_token, doctor_id, slot_id).
    """
    doc_token = await get_token_for(
        async_client,
        f"dr.booking.{uuid4().hex[:6]}@amrutam.co.in",
        "SecurePassword123!",
        UserRole.DOCTOR.value,
    )
    headers = {"Authorization": f"Bearer {doc_token}"}

    doc_res = await async_client.post(
        "/api/v1/doctors/me",
        json={
            "license_number": f"LIC-{uuid4().hex[:8]}",
            "specialization": "Ayurvedic Medicine",
            "languages": ["English", "Hindi"],
            "experience_years": 10,
            "consultation_fee": "800.00",
        },
        headers=headers,
    )
    assert doc_res.status_code == 201
    doctor_id = doc_res.json()["id"]

    slot_start = datetime.now(UTC) + timedelta(days=2)
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


@pytest.mark.asyncio
async def test_booking_happy_path_and_idempotency(async_client: AsyncClient):
    """Verify standard booking, slot status transition, and deterministic idempotency caching."""
    patient_token = await get_token_for(
        async_client,
        f"pat.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    headers = {"Authorization": f"Bearer {patient_token}"}
    _, doctor_id, slot_id = await setup_doctor_and_slot(async_client)

    booking_payload = {
        "doctor_id": doctor_id,
        "slot_id": slot_id,
        "reason": "Consultation regarding seasonal allergies and diet plan.",
    }
    idem_key = f"idem-key-{uuid4()}"

    # 1. Missing Idempotency-Key header returns 400 BAD_REQUEST
    bad_res = await async_client.post(
        "/api/v1/consultations",
        json=booking_payload,
        headers=headers,
    )
    assert bad_res.status_code == 400
    assert bad_res.json()["error_code"] == "MISSING_IDEMPOTENCY_KEY"

    # 2. First booking with Idempotency-Key succeeds with 201
    res1 = await async_client.post(
        "/api/v1/consultations",
        json=booking_payload,
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert res1.status_code == 201
    booking1 = res1.json()
    assert booking1["status"] == ConsultationStatus.SCHEDULED.value
    assert booking1["doctor_id"] == doctor_id
    assert booking1["availability_slot_id"] == slot_id
    consultation_id = booking1["id"]

    # 3. Same key + same payload: Returns cached 201 response with same consultation ID
    res2 = await async_client.post(
        "/api/v1/consultations",
        json=booking_payload,
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert res2.status_code == 201
    assert res2.json()["id"] == consultation_id

    # 4. Same key + different payload: Returns 422 Unprocessable Entity
    altered_payload = {**booking_payload, "reason": "Different modified payload!"}
    res3 = await async_client.post(
        "/api/v1/consultations",
        json=altered_payload,
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert res3.status_code == 422
    assert res3.json()["error_code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"


@pytest.mark.asyncio
async def test_slot_already_booked_conflict(async_client: AsyncClient):
    """Verify that a second patient attempting to book an already booked slot receives 409."""
    patient1_token = await get_token_for(
        async_client,
        f"pat1.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    patient2_token = await get_token_for(
        async_client,
        f"pat2.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    _, doctor_id, slot_id = await setup_doctor_and_slot(async_client)

    payload = {"doctor_id": doctor_id, "slot_id": slot_id}

    # Patient 1 books slot
    res1 = await async_client.post(
        "/api/v1/consultations",
        json=payload,
        headers={"Authorization": f"Bearer {patient1_token}", "Idempotency-Key": f"key-{uuid4()}"},
    )
    assert res1.status_code == 201

    # Patient 2 tries to book the same slot
    res2 = await async_client.post(
        "/api/v1/consultations",
        json=payload,
        headers={"Authorization": f"Bearer {patient2_token}", "Idempotency-Key": f"key-{uuid4()}"},
    )
    assert res2.status_code == 409
    assert res2.json()["error_code"] == "SLOT_ALREADY_BOOKED"


@pytest.mark.asyncio
async def test_consultation_lifecycle_and_state_machine(async_client: AsyncClient):
    """Verify SCHEDULED -> IN_PROGRESS -> COMPLETED and rejection of invalid transitions."""
    doc_token, doctor_id, slot_id = await setup_doctor_and_slot(async_client)
    patient_token = await get_token_for(
        async_client,
        f"pat.life.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )

    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    pat_headers = {"Authorization": f"Bearer {patient_token}"}

    # 1. Patient schedules consultation
    book_res = await async_client.post(
        "/api/v1/consultations",
        json={"doctor_id": doctor_id, "slot_id": slot_id},
        headers={**pat_headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    assert book_res.status_code == 201
    consultation_id = book_res.json()["id"]

    # 2. Patient cannot start consultation (only assigned doctor can)
    forbidden_start = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/start",
        headers=pat_headers,
    )
    assert forbidden_start.status_code == 403

    # 3. Doctor starts consultation: SCHEDULED -> IN_PROGRESS
    start_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/start",
        headers=doc_headers,
    )
    assert start_res.status_code == 200
    assert start_res.json()["status"] == ConsultationStatus.IN_PROGRESS.value
    assert start_res.json()["started_at"] is not None

    # 4. Doctor completes consultation: IN_PROGRESS -> COMPLETED
    complete_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/complete",
        headers=doc_headers,
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == ConsultationStatus.COMPLETED.value
    assert complete_res.json()["completed_at"] is not None

    # 5. Invalid transition: COMPLETED consultation cannot be cancelled
    cancel_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/cancel",
        json={"reason": "Need refund after completion"},
        headers=pat_headers,
    )
    assert cancel_res.status_code == 400
    assert cancel_res.json()["error_code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_cancellation_releases_slot(async_client: AsyncClient):
    """Verify that cancelling a scheduled consultation releases the slot back to AVAILABLE."""
    doc_token, doctor_id, slot_id = await setup_doctor_and_slot(async_client)
    patient_token = await get_token_for(
        async_client,
        f"pat.cancel.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    pat_headers = {"Authorization": f"Bearer {patient_token}"}

    # Book consultation
    book_res = await async_client.post(
        "/api/v1/consultations",
        json={"doctor_id": doctor_id, "slot_id": slot_id},
        headers={**pat_headers, "Idempotency-Key": f"key-{uuid4()}"},
    )
    assert book_res.status_code == 201
    consultation_id = book_res.json()["id"]

    # Cancel consultation
    cancel_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/cancel",
        json={"reason": "Emergency work conflict"},
        headers=pat_headers,
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == ConsultationStatus.CANCELLED.value

    # Verify slot is back to AVAILABLE
    avail_res = await async_client.get(f"/api/v1/doctors/{doctor_id}/availability")
    assert avail_res.status_code == 200
    slots = avail_res.json()
    assert any(s["id"] == slot_id and s["status"] == SlotStatus.AVAILABLE.value for s in slots)


@pytest.mark.asyncio
async def test_idor_protection_for_consultations(async_client: AsyncClient):
    """Verify IDOR protection: A patient cannot view or cancel another patient's consultation."""
    _, doctor_id, slot_id = await setup_doctor_and_slot(async_client)
    patient_owner = await get_token_for(
        async_client,
        f"owner.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )
    patient_attacker = await get_token_for(
        async_client,
        f"attacker.{uuid4().hex[:6]}@example.com",
        "SecurePassword123!",
        UserRole.PATIENT.value,
    )

    # Owner books consultation
    book_res = await async_client.post(
        "/api/v1/consultations",
        json={"doctor_id": doctor_id, "slot_id": slot_id},
        headers={"Authorization": f"Bearer {patient_owner}", "Idempotency-Key": f"key-{uuid4()}"},
    )
    consultation_id = book_res.json()["id"]

    # Attacker tries to view consultation -> 403 Forbidden
    get_res = await async_client.get(
        f"/api/v1/consultations/{consultation_id}",
        headers={"Authorization": f"Bearer {patient_attacker}"},
    )
    assert get_res.status_code == 403

    # Attacker tries to cancel consultation -> 403 Forbidden
    cancel_res = await async_client.post(
        f"/api/v1/consultations/{consultation_id}/cancel",
        json={"reason": "Malicious cancellation attempt"},
        headers={"Authorization": f"Bearer {patient_attacker}"},
    )
    assert cancel_res.status_code == 403

"""Mandatory concurrency test: 100 simultaneous requests racing for the same slot.

Expected Result:
- 201 Created: Exactly 1
- 409 Conflict: Exactly 99
- Direct database verification:
  - consultation count for slot == 1
  - slot status == 'BOOKED'
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.common.constants import SlotStatus, UserRole
from app.core.security import create_jwt_token
from app.modules.auth.models import User
from app.modules.availability.models import AvailabilitySlot
from app.modules.consultations.models import Consultation
from tests.conftest import db_session_factory


@pytest.mark.asyncio
async def test_100_concurrent_booking_race_for_same_slot(async_client: AsyncClient):
    """Execute 100 concurrent booking attempts for the exact same doctor slot."""
    # 1. Setup Doctor with a future slot directly via API
    doc_reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"dr.race.{uuid4().hex[:6]}@amrutam.co.in",
            "password": "SecurePassword123!",
            "role": UserRole.DOCTOR.value,
        },
    )
    assert doc_reg.status_code == 201
    doc_login = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": doc_reg.json()["email"],
            "password": "SecurePassword123!",
        },
    )
    doc_token = doc_login.json()["tokens"]["access_token"]
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    doc_profile = await async_client.post(
        "/api/v1/doctors/me",
        json={
            "license_number": f"RACE-LIC-{uuid4().hex[:8]}",
            "specialization": "Panchakarma Concurrency Specialist",
            "languages": ["English", "Hindi"],
            "experience_years": 12,
            "consultation_fee": "1200.00",
        },
        headers=doc_headers,
    )
    assert doc_profile.status_code == 201
    doctor_id = doc_profile.json()["id"]

    slot_start = datetime.now(UTC) + timedelta(days=3)
    slot_end = slot_start + timedelta(minutes=45)
    slots_res = await async_client.post(
        "/api/v1/doctors/me/availability",
        json={
            "slots": [
                {
                    "start_time": slot_start.isoformat(),
                    "end_time": slot_end.isoformat(),
                }
            ]
        },
        headers=doc_headers,
    )
    assert slots_res.status_code == 201
    slot_id = slots_res.json()[0]["id"]

    # 2. Pre-generate 100 registered patient accounts and valid JWTs
    patient_tokens: list[str] = []
    async with db_session_factory() as session:
        for i in range(100):
            patient = User(
                email=f"patient_race_{i}_{uuid4().hex[:6]}@example.com",
                password_hash="mock_argon2_hash",
                role=UserRole.PATIENT.value,
                is_active=True,
            )
            session.add(patient)
            await session.flush()
            token = create_jwt_token(
                subject=patient.id,
                role=UserRole.PATIENT.value,
                email=patient.email,
            )
            patient_tokens.append(token)
        await session.commit()

    assert len(patient_tokens) == 100

    # 3. Fire 100 simultaneous booking requests with different idempotency keys
    booking_payload = {
        "doctor_id": doctor_id,
        "slot_id": slot_id,
        "reason": "Simultaneous booking race test",
    }

    async def attempt_booking(token: str, request_index: int):
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"race-key-{request_index}-{uuid4()}",
        }
        return await async_client.post(
            "/api/v1/consultations",
            json=booking_payload,
            headers=headers,
        )

    race_tasks = [attempt_booking(patient_tokens[i], i) for i in range(100)]
    responses = await asyncio.gather(*race_tasks)

    # 4. Assert exact HTTP status code distributions: 1 × 201, 99 × 409
    status_codes = [r.status_code for r in responses]
    created_count = status_codes.count(201)
    conflict_count = status_codes.count(409)

    assert created_count == 1, (
        f"Expected exactly 1 successful booking (201), got {created_count}. "
        f"Status breakdown: {status_codes}"
    )
    assert conflict_count == 99, (
        f"Expected exactly 99 conflicts (409), got {conflict_count}. "
        f"Status breakdown: {status_codes}"
    )

    # 5. Direct Database Invariant Verification
    async with db_session_factory() as session:
        # Check consultation count for slot == 1
        count_stmt = select(func.count(Consultation.id)).where(
            Consultation.availability_slot_id == UUID(slot_id)
        )
        consultation_count = (await session.execute(count_stmt)).scalar_one()
        assert consultation_count == 1, (
            f"Database invariant violated: expected 1 consultation row, found {consultation_count}"
        )

        # Check slot status == BOOKED
        slot_stmt = select(AvailabilitySlot).where(
            AvailabilitySlot.id == UUID(slot_id)
        )
        slot = (await session.execute(slot_stmt)).scalar_one()
        assert slot.status == SlotStatus.BOOKED.value, (
            f"Database invariant violated: slot status expected BOOKED, got {slot.status}"
        )

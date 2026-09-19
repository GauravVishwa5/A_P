"""API integration tests for Users, Doctors, and Availability Slot management."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.common.constants import UserRole


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
async def test_user_profile_workflow(async_client: AsyncClient):
    """Verify getting and updating the authenticated user's profile."""
    token = await get_token_for(
        async_client, "patient.profile@example.com", "SecurePassword123!", UserRole.PATIENT.value
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fetch current user profile
    res = await async_client.get("/api/v1/users/me", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "user_id" in data
    assert "first_name" in data

    # 2. Update profile details
    update_payload = {
        "first_name": "Rohan",
        "last_name": "Sharma",
        "phone_number": "+919876543210",
        "date_of_birth": "1995-05-15",
        "gender": "male",
        "address": "123 Ayurvedic Way, Rishikesh",
    }
    update_res = await async_client.patch("/api/v1/users/me", json=update_payload, headers=headers)
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["first_name"] == "Rohan"
    assert updated_data["last_name"] == "Sharma"
    assert updated_data["phone_number"] == "+919876543210"
    assert updated_data["address"] == "123 Ayurvedic Way, Rishikesh"


@pytest.mark.asyncio
async def test_doctor_onboarding_and_directory(async_client: AsyncClient):
    """Verify doctor onboarding, directory search, and profile retrieval."""
    doc_token = await get_token_for(
        async_client, "dr.ayur@amrutam.co.in", "SecurePassword123!", UserRole.DOCTOR.value
    )
    headers = {"Authorization": f"Bearer {doc_token}"}

    # 1. Onboard doctor details
    onboard_payload = {
        "license_number": "AYUSH-998877",
        "specialization": "Panchakarma",
        "languages": ["English", "Hindi", "Sanskrit"],
        "experience_years": 8,
        "consultation_fee": "750.00",
        "bio": "Experienced Ayurvedic physician specializing in chronic detox.",
    }
    onboard_res = await async_client.post(
        "/api/v1/doctors/me", json=onboard_payload, headers=headers
    )
    assert onboard_res.status_code == 201
    doc_data = onboard_res.json()
    assert doc_data["license_number"] == "AYUSH-998877"
    assert doc_data["specialization"] == "Panchakarma"
    assert Decimal(str(doc_data["consultation_fee"])) == Decimal("750.00")
    doctor_id = doc_data["id"]

    # 2. Fetch doctor profile by ID
    get_res = await async_client.get(f"/api/v1/doctors/{doctor_id}")
    assert get_res.status_code == 200
    assert get_res.json()["license_number"] == "AYUSH-998877"

    # 3. Search directory with specialization
    search_res = await async_client.get("/api/v1/doctors?specialization=Panchakarma&max_fee=1000")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data["items"]) >= 1
    assert any(d["id"] == doctor_id for d in search_data["items"])

    # 4. Search with fee filter below consultation fee should not find this doctor
    search_res_cheap = await async_client.get("/api/v1/doctors?max_fee=500")
    assert search_res_cheap.status_code == 200
    assert not any(d["id"] == doctor_id for d in search_res_cheap.json()["items"])


@pytest.mark.asyncio
async def test_availability_slots_and_overlap_prevention(async_client: AsyncClient):
    """Verify availability slot creation, query, and strict overlap prevention."""
    doc_token = await get_token_for(
        async_client, "dr.slots@amrutam.co.in", "SecurePassword123!", UserRole.DOCTOR.value
    )
    headers = {"Authorization": f"Bearer {doc_token}"}

    onboard_res = await async_client.post(
        "/api/v1/doctors/me",
        json={
            "license_number": "AYUSH-SLOTS-001",
            "specialization": "Dravyaguna",
            "languages": ["Hindi"],
            "experience_years": 5,
            "consultation_fee": "500.00",
        },
        headers=headers,
    )
    assert onboard_res.status_code == 201
    doc_id = onboard_res.json()["id"]

    # 1. Create non-overlapping slots
    now = datetime.now(UTC) + timedelta(days=1)
    slot1_start = now.replace(minute=0, second=0, microsecond=0)
    slot1_end = slot1_start + timedelta(minutes=30)

    slot2_start = slot1_end + timedelta(minutes=10)
    slot2_end = slot2_start + timedelta(minutes=30)

    create_res = await async_client.post(
        "/api/v1/doctors/me/availability",
        json={
            "slots": [
                {"start_time": slot1_start.isoformat(), "end_time": slot1_end.isoformat()},
                {"start_time": slot2_start.isoformat(), "end_time": slot2_end.isoformat()},
            ]
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    created_slots = create_res.json()
    assert len(created_slots) == 2

    # 2. Query slots for this doctor
    list_res = await async_client.get(f"/api/v1/doctors/{doc_id}/availability")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 2

    # 3. Attempt to create an overlapping slot (starts inside slot 1)
    overlapping_start = slot1_start + timedelta(minutes=15)
    overlapping_end = overlapping_start + timedelta(minutes=30)

    overlap_res = await async_client.post(
        "/api/v1/doctors/me/availability",
        json={
            "slots": [
                {
                    "start_time": overlapping_start.isoformat(),
                    "end_time": overlapping_end.isoformat(),
                },
            ]
        },
        headers=headers,
    )
    assert overlap_res.status_code == 409
    error_detail = overlap_res.json()
    assert error_detail["error_code"] == "AVAILABILITY_OVERLAP"


@pytest.mark.asyncio
async def test_patient_cannot_create_availability(async_client: AsyncClient):
    """Verify RBAC: Patients cannot create availability slots."""
    patient_token = await get_token_for(
        async_client, "patient.rbac@example.com", "SecurePassword123!", UserRole.PATIENT.value
    )
    headers = {"Authorization": f"Bearer {patient_token}"}
    now = datetime.now(UTC) + timedelta(days=2)
    res = await async_client.post(
        "/api/v1/doctors/me/availability",
        json={
            "slots": [
                {
                    "start_time": now.isoformat(),
                    "end_time": (now + timedelta(minutes=30)).isoformat(),
                }
            ]
        },
        headers=headers,
    )
    # Role check requires DOCTOR, patient should get 403 Forbidden
    assert res.status_code == 403

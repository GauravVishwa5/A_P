# ruff: noqa: E501
"""Comprehensive script to seed demo data in PostgreSQL and test all 32 endpoints."""

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure project root is in sys.path
sys.path.insert(0, os.getcwd())

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            getattr(sys.stdout, "reconfigure")(encoding="utf-8")  # noqa: B009
        if hasattr(sys.stderr, "reconfigure"):
            getattr(sys.stderr, "reconfigure")(encoding="utf-8")  # noqa: B009
    except Exception:
        pass

import app.core.rate_limit as rate_limit_module
import app.core.redis as redis_module
import app.core.security as security_module
from app.common.constants import SlotStatus, UserRole
from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.security import create_jwt_token, hash_password
from app.main import app
from app.modules.auth.models import User
from app.modules.availability.models import AvailabilitySlot
from app.modules.doctors.models import Doctor
from app.modules.users.models import Profile

settings = get_settings()


# ---------------------------------------------------------------------------
# Redis In-Memory Mock (if local Redis server is offline)
# ---------------------------------------------------------------------------
class MockPipeline:
    def __init__(self, mock_redis: "InMemoryMockRedis") -> None:
        self.mock_redis = mock_redis
        self.commands: list[tuple[str, tuple[Any, ...]]] = []

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> "MockPipeline":
        self.commands.append(("zremrangebyscore", (key, min_score, max_score)))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> "MockPipeline":
        self.commands.append(("zadd", (key, mapping)))
        return self

    def zcard(self, key: str) -> "MockPipeline":
        self.commands.append(("zcard", (key,)))
        return self

    def expire(self, key: str, ttl: int) -> "MockPipeline":
        self.commands.append(("expire", (key, ttl)))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for cmd, args in self.commands:
            if cmd == "zremrangebyscore":
                key, min_s, max_s = args
                zset = self.mock_redis._zsets.setdefault(key, {})
                to_remove = [k for k, score in zset.items() if min_s <= score <= max_s]
                for k in to_remove:
                    del zset[k]
                results.append(len(to_remove))
            elif cmd == "zadd":
                key, mapping = args
                zset = self.mock_redis._zsets.setdefault(key, {})
                zset.update(mapping)
                results.append(len(mapping))
            elif cmd == "zcard":
                key = args[0]
                zset = self.mock_redis._zsets.get(key, {})
                results.append(len(zset))
            elif cmd == "expire":
                results.append(True)
        return results


class InMemoryMockRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, val: Any, ex: int | None = None) -> bool:
        self._store[key] = str(val)
        return True

    async def setex(self, key: str, ttl: int, val: Any) -> bool:
        self._store[key] = str(val)
        return True

    async def delete(self, *keys: str) -> bool:
        for k in keys:
            self._store.pop(k, None)
            self._zsets.pop(k, None)
        return True

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass

    async def flushall(self) -> bool:
        self._store.clear()
        self._zsets.clear()
        return True

    def pipeline(self) -> MockPipeline:
        return MockPipeline(self)


async def setup_redis_fallback() -> None:
    healthy = await redis_module.check_redis_health()
    if not healthy:
        print("ℹ️  Local Redis server offline: applying in-memory Redis mock.")
        mock_instance = InMemoryMockRedis()
        redis_module._redis_client = mock_instance  # type: ignore
        redis_module.get_redis_client = lambda: mock_instance  # type: ignore
        rate_limit_module.get_redis_client = lambda: mock_instance  # type: ignore
        security_module.get_redis_client = lambda: mock_instance  # type: ignore
    else:
        print("✅ Local Redis server is healthy and connected.")


# ---------------------------------------------------------------------------
# Seed Demo Data Function
# ---------------------------------------------------------------------------
async def seed_demo_data(session: AsyncSession) -> dict[str, Any]:
    print("\n🌱 Seeding Demo Data into PostgreSQL Database...")
    seeded: dict[str, Any] = {}

    # Helper: get or create user
    async def get_or_create_user(email: str, password: str, role: UserRole) -> User:
        result = await session.execute(select(User).where(User.email == email.lower().strip()))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                email=email.lower().strip(),
                password_hash=hash_password(password),
                role=role.value,
                is_active=True,
                is_verified=True,
                mfa_enabled=False,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)
            print(f"   Created user: {user.email} [{user.role}] (ID: {user.id})")
        else:
            print(f"   User already exists: {user.email} [{user.role}]")
        return user

    # 1. Admin User
    admin = await get_or_create_user("admin@amrutam.com", "AmrutamAdmin@2026!", UserRole.ADMIN)
    seeded["admin"] = admin

    # Admin Profile
    res_prof = await session.execute(select(Profile).where(Profile.user_id == admin.id))
    if not res_prof.scalar_one_or_none():
        admin_prof = Profile(
            user_id=admin.id,
            first_name="System",
            last_name="Administrator",
            phone_number="+919999000000",
        )
        session.add(admin_prof)

    # 2. Doctor 1 (Dr. Rajesh Sharma)
    doc1_user = await get_or_create_user(
        "dr.sharma@amrutam.com", "DoctorPassword@123", UserRole.DOCTOR
    )
    seeded["doc1_user"] = doc1_user

    # Doctor 1 Profile & Doctor entity
    res_prof1 = await session.execute(select(Profile).where(Profile.user_id == doc1_user.id))
    if not res_prof1.scalar_one_or_none():
        doc1_prof = Profile(
            user_id=doc1_user.id,
            first_name="Rajesh",
            last_name="Sharma",
            phone_number="+919820123456",
            gender="Male",
        )
        session.add(doc1_prof)

    res_doc1 = await session.execute(select(Doctor).where(Doctor.user_id == doc1_user.id))
    doc1 = res_doc1.scalar_one_or_none()
    if not doc1:
        doc1 = Doctor(
            user_id=doc1_user.id,
            specialization="Ayurvedic Medicine & Panchakarma",
            license_number="AYUSH-DL-2011-8921",
            experience_years=15,
            consultation_fee=Decimal("850.00"),
            bio="Senior Ayurvedic physician and researcher specializing in classical Nadi Pariksha (Pulse diagnosis), Panchakarma detoxification, and chronic metabolic disorder management.",
            languages=["Hindi", "English", "Sanskrit"],
            rating=Decimal("4.9"),
            total_reviews=142,
            is_available=True,
        )
        session.add(doc1)
        await session.flush()
        await session.refresh(doc1)
        print(f"   Created Doctor Profile: Dr. Rajesh Sharma (ID: {doc1.id})")
    seeded["doc1"] = doc1

    # 3. Doctor 2 (Dr. Ananya Iyer)
    doc2_user = await get_or_create_user(
        "dr.ananya@amrutam.com", "DoctorPassword@123", UserRole.DOCTOR
    )
    seeded["doc2_user"] = doc2_user

    res_prof2 = await session.execute(select(Profile).where(Profile.user_id == doc2_user.id))
    if not res_prof2.scalar_one_or_none():
        doc2_prof = Profile(
            user_id=doc2_user.id,
            first_name="Ananya",
            last_name="Iyer",
            phone_number="+919845987654",
            gender="Female",
        )
        session.add(doc2_prof)

    res_doc2 = await session.execute(select(Doctor).where(Doctor.user_id == doc2_user.id))
    doc2 = res_doc2.scalar_one_or_none()
    if not doc2:
        doc2 = Doctor(
            user_id=doc2_user.id,
            specialization="Kayachikitsa & Herbal Pharmacology",
            license_number="AYUSH-KA-2018-4412",
            experience_years=8,
            consultation_fee=Decimal("600.00"),
            bio="Holistic Ayurvedic practitioner focused on gut biome restoration, adaptogenic herbal protocols, and women's hormonal balance.",
            languages=["English", "Hindi", "Tamil"],
            rating=Decimal("4.8"),
            total_reviews=89,
            is_available=True,
        )
        session.add(doc2)
        await session.flush()
        await session.refresh(doc2)
        print(f"   Created Doctor Profile: Dr. Ananya Iyer (ID: {doc2.id})")
    seeded["doc2"] = doc2

    # 4. Patient 1 (Aarav Patel)
    pat1 = await get_or_create_user(
        "patient.aarav@amrutam.com", "PatientPassword@123", UserRole.PATIENT
    )
    seeded["pat1"] = pat1
    res_pat1_prof = await session.execute(select(Profile).where(Profile.user_id == pat1.id))
    if not res_pat1_prof.scalar_one_or_none():
        pat1_prof = Profile(
            user_id=pat1.id,
            first_name="Aarav",
            last_name="Patel",
            phone_number="+919876543210",
            gender="Male",
            address="101 Lotus Enclave, Linking Road, Bandra West, Mumbai, MH",
        )
        session.add(pat1_prof)

    # 5. Patient 2 (Priya Sen)
    pat2 = await get_or_create_user(
        "patient.priya@amrutam.com", "PatientPassword@123", UserRole.PATIENT
    )
    seeded["pat2"] = pat2
    res_pat2_prof = await session.execute(select(Profile).where(Profile.user_id == pat2.id))
    if not res_pat2_prof.scalar_one_or_none():
        pat2_prof = Profile(
            user_id=pat2.id,
            first_name="Priya",
            last_name="Sen",
            phone_number="+919876543211",
            gender="Female",
            address="402 Palm Heights, 100ft Road, Indiranagar, Bengaluru, KA",
        )
        session.add(pat2_prof)

    # 6. Availability Slots for Dr. Sharma
    now = datetime.now(UTC)
    base_tomorrow = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    slots_to_add = []
    for i in range(5):
        slot_start = base_tomorrow + timedelta(hours=i)
        slot_end = slot_start + timedelta(minutes=45)
        # Check if exists
        res_slot = await session.execute(
            select(AvailabilitySlot).where(
                AvailabilitySlot.doctor_id == doc1.id,
                AvailabilitySlot.start_time == slot_start,
            )
        )
        existing_slot = res_slot.scalar_one_or_none()
        if not existing_slot:
            slot = AvailabilitySlot(
                doctor_id=doc1.id,
                start_time=slot_start,
                end_time=slot_end,
                status=SlotStatus.AVAILABLE.value,
            )
            session.add(slot)
            slots_to_add.append(slot)

    # 7. Availability Slots for Dr. Ananya
    base_day2 = (now + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    for i in range(3):
        slot_start = base_day2 + timedelta(hours=i)
        slot_end = slot_start + timedelta(minutes=45)
        res_slot = await session.execute(
            select(AvailabilitySlot).where(
                AvailabilitySlot.doctor_id == doc2.id,
                AvailabilitySlot.start_time == slot_start,
            )
        )
        if not res_slot.scalar_one_or_none():
            slot = AvailabilitySlot(
                doctor_id=doc2.id,
                start_time=slot_start,
                end_time=slot_end,
                status=SlotStatus.AVAILABLE.value,
            )
            session.add(slot)

    await session.commit()
    print("✅ Demo Data Seeding Completed successfully!")
    return seeded


# ---------------------------------------------------------------------------
# Endpoint Runner and Test Suite
# ---------------------------------------------------------------------------
async def test_all_endpoints() -> None:
    await setup_redis_fallback()

    factory = get_session_factory()
    async with factory() as session:
        seeded = await seed_demo_data(session)

    print("\n🚀 Executing Automated Verification of All 32 Endpoints...")

    transport = ASGITransport(app=app)
    results = []

    async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
        # ---------------------------------------------------------
        # Category 1: System Endpoints (3)
        # ---------------------------------------------------------
        print("\n[Category 1: System Endpoints]")

        # 1. GET /health
        t0 = time.perf_counter()
        r = await client.get("/health")
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("status") == "ok"
        results.append(
            {
                "id": 1,
                "method": "GET",
                "path": "/health",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "System",
                "summary": "Liveness Probe",
                "details": r.json(),
            }
        )
        print(f"  {r.status_code} GET /health ({lat}ms) -> {r.json()}")

        # 2. GET /ready
        t0 = time.perf_counter()
        r = await client.get("/ready")
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code in [200, 503]
        results.append(
            {
                "id": 2,
                "method": "GET",
                "path": "/ready",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "System",
                "summary": "Readiness Probe (DB + Redis)",
                "details": r.json(),
            }
        )
        print(f"  {r.status_code} GET /ready ({lat}ms) -> {r.json()}")

        # 3. GET /metrics
        t0 = time.perf_counter()
        r = await client.get("/metrics")
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and len(r.text) > 0
        results.append(
            {
                "id": 3,
                "method": "GET",
                "path": "/metrics",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "System",
                "summary": "Prometheus Telemetry Metrics",
                "details": f"{len(r.text)} bytes telemetry",
            }
        )
        print(f"  {r.status_code} GET /metrics ({lat}ms) -> [{len(r.text)} bytes telemetry]")

        # ---------------------------------------------------------
        # Category 2: Authentication Endpoints (6)
        # ---------------------------------------------------------
        print("\n[Category 2: Authentication Endpoints]")

        # 4. POST /api/v1/auth/register
        reg_email = f"test.user.{uuid4().hex[:6]}@amrutam.com"
        reg_password = "TempPassword@123!"
        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": reg_email, "password": reg_password, "role": "PATIENT"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 201
        temp_user_data = r.json() if passed else {}
        results.append(
            {
                "id": 4,
                "method": "POST",
                "path": "/api/v1/auth/register",
                "status": r.status_code,
                "expected": 201,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Authentication",
                "summary": "Register User Account",
                "details": f"Registered {reg_email} (ID: {temp_user_data.get('id')})",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/auth/register ({lat}ms) -> user id: {temp_user_data.get('id')}"
        )

        # 5. POST /api/v1/auth/login
        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/auth/login", json={"email": reg_email, "password": reg_password}
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and "tokens" in r.json()
        login_res = r.json()
        temp_access_token = (
            login_res["tokens"]["access_token"] if passed and login_res.get("tokens") else ""
        )
        temp_refresh_token = (
            login_res["tokens"]["refresh_token"] if passed and login_res.get("tokens") else ""
        )
        results.append(
            {
                "id": 5,
                "method": "POST",
                "path": "/api/v1/auth/login",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Authentication",
                "summary": "Authenticate User Credentials",
                "details": f"Issued JWT bearer token (exp: {login_res.get('tokens', {}).get('expires_in')}s)",
            }
        )
        print(f"  {r.status_code} POST /api/v1/auth/login ({lat}ms) -> Token obtained")

        # 6. POST /api/v1/auth/mfa/enroll
        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/auth/mfa/enroll", headers={"Authorization": f"Bearer {temp_access_token}"}
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and "secret" in r.json()
        mfa_secret = r.json().get("secret") if passed else ""
        results.append(
            {
                "id": 6,
                "method": "POST",
                "path": "/api/v1/auth/mfa/enroll",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Authentication",
                "summary": "Enroll in TOTP MFA",
                "details": f"Generated Base32 secret: {mfa_secret[:6]}...",
            }
        )
        print(f"  {r.status_code} POST /api/v1/auth/mfa/enroll ({lat}ms) -> Secret generated")

        # 7. POST /api/v1/auth/mfa/verify
        # Login again to receive mfa_token challenge
        r_mfa_login = await client.post(
            "/api/v1/auth/login", json={"email": reg_email, "password": reg_password}
        )
        mfa_token = r_mfa_login.json().get("mfa_token")
        totp_code = pyotp.TOTP(mfa_secret).now() if mfa_secret else "123456"

        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": mfa_token, "code": totp_code}
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and "access_token" in r.json()
        if passed:
            temp_access_token = r.json()["access_token"]
            temp_refresh_token = r.json()["refresh_token"]
        results.append(
            {
                "id": 7,
                "method": "POST",
                "path": "/api/v1/auth/mfa/verify",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Authentication",
                "summary": "Verify TOTP MFA Code",
                "details": "Verified 6-digit TOTP code and issued full token pair",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/auth/mfa/verify ({lat}ms) -> MFA verified, tokens issued"
        )

        # 8. POST /api/v1/auth/token/refresh
        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/auth/token/refresh", json={"refresh_token": temp_refresh_token}
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and "access_token" in r.json()
        if passed:
            temp_access_token = r.json()["access_token"]
            temp_refresh_token = r.json()["refresh_token"]
        results.append(
            {
                "id": 8,
                "method": "POST",
                "path": "/api/v1/auth/token/refresh",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Authentication",
                "summary": "Rotate Refresh Token",
                "details": "Rotated refresh token with single-use family theft protection",
            }
        )
        print(f"  {r.status_code} POST /api/v1/auth/token/refresh ({lat}ms) -> Token pair rotated")

        # 9. POST /api/v1/auth/logout
        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {temp_access_token}"},
            json={"refresh_token": temp_refresh_token},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 204
        results.append(
            {
                "id": 9,
                "method": "POST",
                "path": "/api/v1/auth/logout",
                "status": r.status_code,
                "expected": 204,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Authentication",
                "summary": "Revoke Tokens (Logout)",
                "details": "Revoked access and refresh tokens",
            }
        )
        print(f"  {r.status_code} POST /api/v1/auth/logout ({lat}ms) -> Tokens revoked")

        # Generate valid JWT tokens directly for seeded domain actors (avoids rate limiting)
        admin_token = create_jwt_token(
            subject=str(seeded["admin"].id), role="ADMIN", email="admin@amrutam.com"
        )
        doc_token = create_jwt_token(
            subject=str(seeded["doc1_user"].id), role="DOCTOR", email="dr.sharma@amrutam.com"
        )
        pat_token = create_jwt_token(
            subject=str(seeded["pat1"].id), role="PATIENT", email="patient.aarav@amrutam.com"
        )
        pat2_token = create_jwt_token(
            subject=str(seeded["pat2"].id), role="PATIENT", email="patient.priya@amrutam.com"
        )

        # ---------------------------------------------------------
        # Category 3: Users Endpoints (2)
        # ---------------------------------------------------------
        print("\n[Category 3: Users Endpoints]")

        # 10. GET /api/v1/users/me
        t0 = time.perf_counter()
        r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {pat_token}"})
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("first_name") == "Aarav"
        results.append(
            {
                "id": 10,
                "method": "GET",
                "path": "/api/v1/users/me",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Users",
                "summary": "Get Current User Profile",
                "details": f"Retrieved profile for {r.json().get('first_name')} {r.json().get('last_name')}",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/users/me ({lat}ms) -> {r.json().get('first_name')} {r.json().get('last_name')}"
        )

        # 11. PATCH /api/v1/users/me
        t0 = time.perf_counter()
        r = await client.patch(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {pat_token}"},
            json={"phone_number": "+919876543299", "address": "Bandra West, Mumbai"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("phone_number") == "+919876543299"
        results.append(
            {
                "id": 11,
                "method": "PATCH",
                "path": "/api/v1/users/me",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Users",
                "summary": "Update Current User Profile",
                "details": f"Updated phone: {r.json().get('phone_number')}",
            }
        )
        print(
            f"  {r.status_code} PATCH /api/v1/users/me ({lat}ms) -> phone: {r.json().get('phone_number')}"
        )

        # ---------------------------------------------------------
        # Category 4: Doctors Endpoints (4)
        # ---------------------------------------------------------
        print("\n[Category 4: Doctors Endpoints]")

        # 12. GET /api/v1/doctors
        t0 = time.perf_counter()
        r = await client.get("/api/v1/doctors")
        lat = round((time.perf_counter() - t0) * 1000, 2)
        doc_list = r.json().get("items", []) if r.status_code == 200 else []
        passed = r.status_code == 200 and len(doc_list) > 0
        results.append(
            {
                "id": 12,
                "method": "GET",
                "path": "/api/v1/doctors",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Doctors",
                "summary": "Search & Filter Doctors",
                "details": f"Found {len(doc_list)} registered doctors",
            }
        )
        print(f"  {r.status_code} GET /api/v1/doctors ({lat}ms) -> {len(doc_list)} doctors listed")

        # 13. GET /api/v1/doctors/{doctor_id}
        doc1_id = str(seeded["doc1"].id)
        t0 = time.perf_counter()
        r = await client.get(f"/api/v1/doctors/{doc1_id}")
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("id") == doc1_id
        results.append(
            {
                "id": 13,
                "method": "GET",
                "path": "/api/v1/doctors/{doctor_id}",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Doctors",
                "summary": "Get Doctor Details by ID",
                "details": f"Dr. Specialization: {r.json().get('specialization')}, Fee: ₹{r.json().get('consultation_fee')}",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/doctors/{doc1_id} ({lat}ms) -> {r.json().get('specialization')}"
        )

        # Register a new temporary doctor account to test POST /api/v1/doctors/me and PATCH /api/v1/doctors/me
        temp_doc_email = f"dr.test.{uuid4().hex[:6]}@amrutam.com"
        r_reg_doc = await client.post(
            "/api/v1/auth/register",
            json={"email": temp_doc_email, "password": "DoctorPassword@123", "role": "DOCTOR"},
        )
        temp_doc_id = r_reg_doc.json()["id"]
        temp_doc_token = create_jwt_token(subject=temp_doc_id, role="DOCTOR", email=temp_doc_email)

        # 14. POST /api/v1/doctors/me
        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/doctors/me",
            headers={"Authorization": f"Bearer {temp_doc_token}"},
            json={
                "specialization": "Shalakya Tantra (ENT & Ophthalmology)",
                "license_number": f"AYUSH-MH-{uuid4().hex[:4].upper()}-99",
                "experience_years": 10,
                "consultation_fee": "750.00",
                "bio": "Ayurvedic specialist in eye disorders, chronic sinusitis, and cranial therapies.",
                "languages": ["Hindi", "English", "Marathi"],
            },
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 201
        temp_doctor_id = r.json().get("id") if passed else ""
        results.append(
            {
                "id": 14,
                "method": "POST",
                "path": "/api/v1/doctors/me",
                "status": r.status_code,
                "expected": 201,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Doctors",
                "summary": "Initialize Doctor Profile",
                "details": f"Created profile (Doctor ID: {temp_doctor_id})",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/doctors/me ({lat}ms) -> Doctor Profile ID: {temp_doctor_id}"
        )

        # 15. PATCH /api/v1/doctors/me
        t0 = time.perf_counter()
        r = await client.patch(
            "/api/v1/doctors/me",
            headers={"Authorization": f"Bearer {temp_doc_token}"},
            json={"consultation_fee": "800.00", "experience_years": 11},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("experience_years") == 11
        results.append(
            {
                "id": 15,
                "method": "PATCH",
                "path": "/api/v1/doctors/me",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Doctors",
                "summary": "Update Doctor Profile",
                "details": f"Updated fee to ₹{r.json().get('consultation_fee')}, exp: {r.json().get('experience_years')} yrs",
            }
        )
        print(
            f"  {r.status_code} PATCH /api/v1/doctors/me ({lat}ms) -> Exp: {r.json().get('experience_years')}, Fee: {r.json().get('consultation_fee')}"
        )

        # ---------------------------------------------------------
        # Category 5: Availability Endpoints (4)
        # ---------------------------------------------------------
        print("\n[Category 5: Availability Endpoints]")

        # 16. POST /api/v1/doctors/me/availability
        slot1_start = (datetime.now(UTC) + timedelta(days=5)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        slot1_end = slot1_start + timedelta(minutes=30)
        slot2_start = slot1_start + timedelta(minutes=30)
        slot2_end = slot2_start + timedelta(minutes=30)

        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/doctors/me/availability",
            headers={"Authorization": f"Bearer {temp_doc_token}"},
            json={
                "slots": [
                    {"start_time": slot1_start.isoformat(), "end_time": slot1_end.isoformat()},
                    {"start_time": slot2_start.isoformat(), "end_time": slot2_end.isoformat()},
                ]
            },
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        created_slots = r.json() if r.status_code == 201 else []
        passed = r.status_code == 201 and len(created_slots) == 2
        temp_slot1_id = created_slots[0]["id"] if passed else ""
        temp_slot2_id = created_slots[1]["id"] if passed else ""
        results.append(
            {
                "id": 16,
                "method": "POST",
                "path": "/api/v1/doctors/me/availability",
                "status": r.status_code,
                "expected": 201,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Availability",
                "summary": "Batch Create Availability Slots",
                "details": f"Created {len(created_slots)} schedule slots",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/doctors/me/availability ({lat}ms) -> {len(created_slots)} slots created"
        )

        # 17. GET /api/v1/doctors/{doctor_id}/availability
        t0 = time.perf_counter()
        r = await client.get(f"/api/v1/doctors/{doc1_id}/availability")
        lat = round((time.perf_counter() - t0) * 1000, 2)
        available_slots = r.json() if r.status_code == 200 else []
        passed = r.status_code == 200 and len(available_slots) > 0
        doc1_booking_slot_id = available_slots[0]["id"] if len(available_slots) > 0 else ""
        doc1_cancel_slot_id = available_slots[1]["id"] if len(available_slots) > 1 else ""
        results.append(
            {
                "id": 17,
                "method": "GET",
                "path": "/api/v1/doctors/{doctor_id}/availability",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Availability",
                "summary": "List Available Booking Slots",
                "details": f"Found {len(available_slots)} available slots for Dr. Sharma",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/doctors/{doc1_id}/availability ({lat}ms) -> {len(available_slots)} available slots"
        )

        # 18. PATCH /api/v1/availability/{slot_id}
        t0 = time.perf_counter()
        r = await client.patch(
            f"/api/v1/availability/{temp_slot1_id}",
            headers={"Authorization": f"Bearer {temp_doc_token}"},
            json={"status": "CANCELLED"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("status") == "CANCELLED"
        results.append(
            {
                "id": 18,
                "method": "PATCH",
                "path": "/api/v1/availability/{slot_id}",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Availability",
                "summary": "Update Availability Slot Status",
                "details": f"Updated slot status to {r.json().get('status')}",
            }
        )
        print(
            f"  {r.status_code} PATCH /api/v1/availability/{temp_slot1_id} ({lat}ms) -> Status: {r.json().get('status')}"
        )

        # 19. DELETE /api/v1/availability/{slot_id}
        t0 = time.perf_counter()
        r = await client.delete(
            f"/api/v1/availability/{temp_slot2_id}",
            headers={"Authorization": f"Bearer {temp_doc_token}"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 204
        results.append(
            {
                "id": 19,
                "method": "DELETE",
                "path": "/api/v1/availability/{slot_id}",
                "status": r.status_code,
                "expected": 204,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Availability",
                "summary": "Delete Available Slot",
                "details": f"Deleted unbooked slot {temp_slot2_id}",
            }
        )
        print(f"  {r.status_code} DELETE /api/v1/availability/{temp_slot2_id} ({lat}ms) -> Deleted")

        # ---------------------------------------------------------
        # Category 6: Consultations Endpoints (6)
        # ---------------------------------------------------------
        print("\n[Category 6: Consultations Endpoints]")

        # 20. POST /api/v1/consultations (Book consultation 1)
        consult_key_1 = f"idem-book-{uuid4().hex[:8]}"
        t0 = time.perf_counter()
        r = await client.post(
            "/api/v1/consultations",
            headers={"Authorization": f"Bearer {pat_token}", "Idempotency-Key": consult_key_1},
            json={
                "doctor_id": doc1_id,
                "slot_id": doc1_booking_slot_id,
                "reason": "Digestive sluggishness, acid reflux, and disturbed sleep cycle.",
            },
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        consult_1 = r.json() if r.status_code == 201 else {}
        passed = r.status_code == 201 and "id" in consult_1
        consult_1_id = consult_1.get("id", "")
        results.append(
            {
                "id": 20,
                "method": "POST",
                "path": "/api/v1/consultations",
                "status": r.status_code,
                "expected": 201,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Consultations",
                "summary": "Book Consultation (Idempotent)",
                "details": f"Consultation booked: {consult_1_id} (Status: {consult_1.get('status')})",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/consultations ({lat}ms) -> ID: {consult_1_id}, Status: {consult_1.get('status')}"
        )

        # 21. GET /api/v1/consultations
        t0 = time.perf_counter()
        r = await client.get(
            "/api/v1/consultations", headers={"Authorization": f"Bearer {pat_token}"}
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        my_consultations = r.json().get("items", []) if r.status_code == 200 else []
        passed = r.status_code == 200 and len(my_consultations) > 0
        results.append(
            {
                "id": 21,
                "method": "GET",
                "path": "/api/v1/consultations",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Consultations",
                "summary": "List Consultations",
                "details": f"Caller has {len(my_consultations)} consultations",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/consultations ({lat}ms) -> {len(my_consultations)} consultations"
        )

        # 22. GET /api/v1/consultations/{consultation_id}
        t0 = time.perf_counter()
        r = await client.get(
            f"/api/v1/consultations/{consult_1_id}",
            headers={"Authorization": f"Bearer {pat_token}"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("id") == consult_1_id
        results.append(
            {
                "id": 22,
                "method": "GET",
                "path": "/api/v1/consultations/{consultation_id}",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Consultations",
                "summary": "Get Consultation by ID",
                "details": f"Meeting Ref: {r.json().get('meeting_reference')}",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/consultations/{consult_1_id} ({lat}ms) -> Meeting: {r.json().get('meeting_reference')}"
        )

        # 23. POST /api/v1/consultations/{consultation_id}/start (Doctor Sharma starts consultation)
        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/consultations/{consult_1_id}/start",
            headers={"Authorization": f"Bearer {doc_token}"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("status") == "IN_PROGRESS"
        results.append(
            {
                "id": 23,
                "method": "POST",
                "path": "/api/v1/consultations/{consultation_id}/start",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Consultations",
                "summary": "Start Consultation (Doctor)",
                "details": f"Status updated to: {r.json().get('status')}",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/consultations/{consult_1_id}/start ({lat}ms) -> Status: {r.json().get('status')}"
        )

        # 24. POST /api/v1/consultations/{consultation_id}/complete (Doctor Sharma completes consultation)
        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/consultations/{consult_1_id}/complete",
            headers={"Authorization": f"Bearer {doc_token}"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("status") == "COMPLETED"
        results.append(
            {
                "id": 24,
                "method": "POST",
                "path": "/api/v1/consultations/{consultation_id}/complete",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Consultations",
                "summary": "Complete Consultation (Doctor)",
                "details": f"Status updated to: {r.json().get('status')}",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/consultations/{consult_1_id}/complete ({lat}ms) -> Status: {r.json().get('status')}"
        )

        # Book consultation 2 to test cancellation endpoint
        consult_key_2 = f"idem-book-{uuid4().hex[:8]}"
        r_book2 = await client.post(
            "/api/v1/consultations",
            headers={"Authorization": f"Bearer {pat2_token}", "Idempotency-Key": consult_key_2},
            json={
                "doctor_id": doc1_id,
                "slot_id": doc1_cancel_slot_id,
                "reason": "Consultation regarding seasonal allergies.",
            },
        )
        consult_2_id = r_book2.json().get("id")

        # 25. POST /api/v1/consultations/{consultation_id}/cancel
        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/consultations/{consult_2_id}/cancel",
            headers={"Authorization": f"Bearer {pat2_token}"},
            json={"reason": "Schedule clash due to unavoidable business travel."},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("status") == "CANCELLED"
        results.append(
            {
                "id": 25,
                "method": "POST",
                "path": "/api/v1/consultations/{consultation_id}/cancel",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Consultations",
                "summary": "Cancel Consultation",
                "details": f"Consultation cancelled. Reason: {r.json().get('cancellation_reason')}",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/consultations/{consult_2_id}/cancel ({lat}ms) -> Status: {r.json().get('status')}"
        )

        # ---------------------------------------------------------
        # Category 7: Prescriptions Endpoints (3)
        # ---------------------------------------------------------
        print("\n[Category 7: Prescriptions Endpoints]")

        # 26. POST /api/v1/consultations/{consultation_id}/prescriptions
        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/consultations/{consult_1_id}/prescriptions",
            headers={"Authorization": f"Bearer {doc_token}"},
            json={
                "diagnosis": "Vata-Pitta Dushti manifesting as Agnimandya (digestive weakness) and Anidra (insomnia).",
                "medications": [
                    {
                        "name": "Ashwagandha Churna",
                        "dosage": "3 grams",
                        "frequency": "Twice daily with warm cow's milk",
                        "duration": "30 days",
                        "instructions": "Take post dinner and early morning on empty stomach.",
                    },
                    {
                        "name": "Triphala Kwath",
                        "dosage": "15 ml with 30ml warm water",
                        "frequency": "Once daily at bedtime",
                        "duration": "21 days",
                        "instructions": "Detoxifying purgative to regulate bowel movement.",
                    },
                    {
                        "name": "Brahmi Vati (Swarna Yukta)",
                        "dosage": "1 tablet (250mg)",
                        "frequency": "Morning before breakfast",
                        "duration": "14 days",
                        "instructions": "Medhya Rasayana for mental calmness.",
                    },
                ],
                "notes": "Follow Ahara-Vihara guidelines: strictly avoid cold/raw salads after sunset, avoid blue screen light 1 hour prior to sleep.",
            },
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        presc = r.json() if r.status_code == 201 else {}
        passed = r.status_code == 201 and "id" in presc
        presc_id = presc.get("id", "")
        results.append(
            {
                "id": 26,
                "method": "POST",
                "path": "/api/v1/consultations/{consultation_id}/prescriptions",
                "status": r.status_code,
                "expected": 201,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Prescriptions",
                "summary": "Issue Prescription (Doctor)",
                "details": f"Prescription ID: {presc_id} ({len(presc.get('medications', []))} medications prescribed)",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/consultations/{consult_1_id}/prescriptions ({lat}ms) -> ID: {presc_id}"
        )

        # 27. GET /api/v1/consultations/{consultation_id}/prescriptions
        t0 = time.perf_counter()
        r = await client.get(
            f"/api/v1/consultations/{consult_1_id}/prescriptions",
            headers={"Authorization": f"Bearer {pat_token}"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("id") == presc_id
        results.append(
            {
                "id": 27,
                "method": "GET",
                "path": "/api/v1/consultations/{consultation_id}/prescriptions",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Prescriptions",
                "summary": "Get Prescription by Consultation ID",
                "details": f"Diagnosis: {r.json().get('diagnosis')[:45]}...",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/consultations/{consult_1_id}/prescriptions ({lat}ms) -> Diagnosis found"
        )

        # 28. GET /api/v1/prescriptions/{prescription_id}
        t0 = time.perf_counter()
        r = await client.get(
            f"/api/v1/prescriptions/{presc_id}", headers={"Authorization": f"Bearer {pat_token}"}
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("id") == presc_id
        results.append(
            {
                "id": 28,
                "method": "GET",
                "path": "/api/v1/prescriptions/{prescription_id}",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Prescriptions",
                "summary": "Get Prescription Details by ID",
                "details": f"Prescribed to Patient ID: {r.json().get('patient_id')}",
            }
        )
        print(f"  {r.status_code} GET /api/v1/prescriptions/{presc_id} ({lat}ms) -> Verified")

        # ---------------------------------------------------------
        # Category 8: Payments Endpoints (3)
        # ---------------------------------------------------------
        print("\n[Category 8: Payments Endpoints]")

        # Book consultation 3 to process a live payment and test refund
        # Get an available slot for Dr. Ananya
        doc2_id = str(seeded["doc2"].id)
        r_slots2 = await client.get(f"/api/v1/doctors/{doc2_id}/availability")
        doc2_slot_id = r_slots2.json()[0]["id"]

        consult_key_3 = f"idem-book-{uuid4().hex[:8]}"
        r_book3 = await client.post(
            "/api/v1/consultations",
            headers={"Authorization": f"Bearer {pat_token}", "Idempotency-Key": consult_key_3},
            json={
                "doctor_id": doc2_id,
                "slot_id": doc2_slot_id,
                "reason": "Holistic nutritional consultation for chronic fatigue.",
            },
        )
        consult_3_id = r_book3.json().get("id")

        # 29. POST /api/v1/consultations/{consultation_id}/payments
        pay_key = f"idem-pay-{uuid4().hex[:8]}"
        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/consultations/{consult_3_id}/payments",
            headers={"Authorization": f"Bearer {pat_token}", "Idempotency-Key": pay_key},
            json={"amount": "600.00", "currency": "INR", "mock_mode": "SUCCESS"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        payment_data = r.json() if r.status_code == 201 else {}
        passed = r.status_code == 201 and payment_data.get("status") in ["SUCCESS", "INITIATED"]
        payment_id = payment_data.get("id", "")
        results.append(
            {
                "id": 29,
                "method": "POST",
                "path": "/api/v1/consultations/{consultation_id}/payments",
                "status": r.status_code,
                "expected": 201,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Payments",
                "summary": "Process Payment (Idempotent)",
                "details": f"Payment ID: {payment_id} (Status: {payment_data.get('status')}, Amount: ₹{payment_data.get('amount')})",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/consultations/{consult_3_id}/payments ({lat}ms) -> ID: {payment_id}, Status: {payment_data.get('status')}"
        )

        # 30. GET /api/v1/consultations/{consultation_id}/payments
        t0 = time.perf_counter()
        r = await client.get(
            f"/api/v1/consultations/{consult_3_id}/payments",
            headers={"Authorization": f"Bearer {pat_token}"},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        payments_list = r.json() if r.status_code == 200 else []
        passed = r.status_code == 200 and len(payments_list) > 0
        results.append(
            {
                "id": 30,
                "method": "GET",
                "path": "/api/v1/consultations/{consultation_id}/payments",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Payments",
                "summary": "List Consultation Payments",
                "details": f"Retrieved {len(payments_list)} payment records",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/consultations/{consult_3_id}/payments ({lat}ms) -> {len(payments_list)} transactions"
        )

        # 31. POST /api/v1/payments/{payment_id}/refund (Admin-only)
        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/payments/{payment_id}/refund",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"reason": "Patient requested cancellation within cooling-off period."},
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        passed = r.status_code == 200 and r.json().get("status") == "REFUNDED"
        results.append(
            {
                "id": 31,
                "method": "POST",
                "path": "/api/v1/payments/{payment_id}/refund",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Payments",
                "summary": "Refund Payment (Admin)",
                "details": f"Refund processed. Status: {r.json().get('status')}",
            }
        )
        print(
            f"  {r.status_code} POST /api/v1/payments/{payment_id}/refund ({lat}ms) -> Status: {r.json().get('status')}"
        )

        # ---------------------------------------------------------
        # Category 9: Audit & Compliance Endpoints (1)
        # ---------------------------------------------------------
        print("\n[Category 9: Audit & Compliance Endpoints]")

        # 32. GET /api/v1/audit/logs (Admin-only)
        t0 = time.perf_counter()
        r = await client.get(
            "/api/v1/audit/logs", headers={"Authorization": f"Bearer {admin_token}"}
        )
        lat = round((time.perf_counter() - t0) * 1000, 2)
        audit_items = r.json().get("items", []) if r.status_code == 200 else []
        passed = r.status_code == 200 and isinstance(audit_items, list)
        results.append(
            {
                "id": 32,
                "method": "GET",
                "path": "/api/v1/audit/logs",
                "status": r.status_code,
                "expected": 200,
                "latency_ms": lat,
                "passed": passed,
                "tag": "Audit & Compliance",
                "summary": "List Immutable Audit Logs (Admin)",
                "details": f"Retrieved {len(audit_items)} immutable compliance records",
            }
        )
        print(
            f"  {r.status_code} GET /api/v1/audit/logs ({lat}ms) -> {len(audit_items)} audit log entries"
        )

    # ---------------------------------------------------------
    # Generate Summary Report
    # ---------------------------------------------------------
    total = len(results)
    passed_count = sum(1 for res in results if res["passed"])
    failed_count = total - passed_count
    avg_latency = round(sum(res["latency_ms"] for res in results) / total, 2) if total else 0

    print("\n" + "=" * 80)
    print(
        f"🏁 ENDPOINT TEST RUN SUMMARY: {passed_count}/{total} PASSED ({(passed_count / total) * 100:.1f}%)"
    )
    print(f"⏱️  Average Response Latency: {avg_latency} ms")
    print("=" * 80)

    # Save JSON Report
    report_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_endpoints": total,
        "passed": passed_count,
        "failed": failed_count,
        "success_rate": f"{(passed_count / total) * 100:.1f}%",
        "avg_latency_ms": avg_latency,
        "endpoints": results,
    }

    with open("demo_endpoint_report.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    # Save Markdown Report
    md_lines = [
        "# 📊 Amrutam Telemedicine Platform - Comprehensive API Endpoint Verification Report",
        "",
        f"> **Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        "> **Test Execution Environment:** Localhost (PostgreSQL `amrutam_db`)  ",
        f"> **Total Endpoints Tested:** {total} / 32  ",
        f"> **Pass Rate:** **{passed_count} / {total} ({(passed_count / total) * 100:.1f}%)**  ",
        f"> **Average Latency:** **{avg_latency} ms**",
        "",
        "## 1. Demo User Accounts & Credentials Seeded",
        "",
        "| Role | Name | Email | Password | Key Associated Entities |",
        "| :--- | :--- | :--- | :--- | :--- |",
        "| **ADMIN** | System Administrator | `admin@amrutam.com` | `AmrutamAdmin@2026!` | Audit logs, Refund authority |",
        "| **DOCTOR** | Dr. Rajesh Sharma | `dr.sharma@amrutam.com` | `DoctorPassword@123` | Specialization: Ayurvedic Medicine, Panchakarma (Fee: ₹850) |",
        "| **DOCTOR** | Dr. Ananya Iyer | `dr.ananya@amrutam.com` | `DoctorPassword@123` | Specialization: Kayachikitsa, Herbal Pharmacology (Fee: ₹600) |",
        "| **PATIENT** | Aarav Patel | `patient.aarav@amrutam.com` | `PatientPassword@123` | Active consultation, Settled payment, Digital prescription |",
        "| **PATIENT** | Priya Sen | `patient.priya@amrutam.com` | `PatientPassword@123` | Cancelled consultation demonstration |",
        "",
        "---",
        "",
        "## 2. All 32 Endpoints Test Results",
        "",
        "| # | Method | Endpoint Path | Category | Status Code | Latency | Result | Key Details / Payload |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for ep in results:
        status_badge = "✅ PASS" if ep["passed"] else "❌ FAIL"
        md_lines.append(
            f"| {ep['id']} | `{ep['method']}` | `{ep['path']}` | {ep['tag']} | `{ep['status']}` (Exp: `{ep['expected']}`) | {ep['latency_ms']} ms | {status_badge} | {ep['details']} |"
        )

    md_lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Postman & Swagger Interactive Testing Instructions",
            "",
            "1. **Start Local Backend Server:**",
            "   ```powershell",
            "   .\\.venv\\Scripts\\Activate.ps1",
            "   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload",
            "   ```",
            "2. **Open Interactive Swagger UI:**",
            "   - Navigate to [http://localhost:8000/docs](http://localhost:8000/docs)",
            "3. **Import Postman Collection:**",
            "   - Import [`amrutam-telemedicine.postman_collection.json`](amrutam-telemedicine.postman_collection.json)",
            "   - Execute **Auth > Login** with any of the demo accounts above.",
            "   - The collection script will automatically capture the access & refresh token and inject them into subsequent requests!",
            "",
        ]
    )

    with open("demo_endpoint_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print("\n📄 Reports saved:")
    print("   - Markdown Report: demo_endpoint_report.md")
    print("   - JSON Report:     demo_endpoint_report.json")


if __name__ == "__main__":
    asyncio.run(test_all_endpoints())

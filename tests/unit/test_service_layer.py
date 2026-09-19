"""Unit tests for service layer business logic.

Covers state machines, authorization, and edge cases.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import ConsultationStatus, SlotStatus, UserRole
from app.common.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.security import (
    create_jwt_token,
    decode_jwt_token,
    generate_mfa_secret,
    generate_random_token,
    hash_password,
    hash_refresh_token,
    verify_mfa_totp,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import UserLoginRequest, UserRegisterRequest
from app.modules.auth.service import AuthService
from app.modules.availability.models import AvailabilitySlot
from app.modules.consultations.models import Consultation
from app.modules.consultations.schemas import BookingRequest
from app.modules.consultations.service import ConsultationService
from app.modules.doctors.models import Doctor
from app.modules.prescriptions.schemas import MedicationItem, PrescriptionCreateRequest
from app.modules.prescriptions.service import PrescriptionService

# ============================================================================
# AUTH SERVICE UNIT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_auth_registration_success(db_session: AsyncSession) -> None:
    """Verify user registration stores an Argon2id-hashed password."""
    service = AuthService(db_session)
    request = UserRegisterRequest(
        email="unit.register@example.com",
        password="SecurePassw0rd!",
        role=UserRole.PATIENT,
    )
    user = await service.register(request)
    assert user.id is not None
    assert user.email == "unit.register@example.com"
    assert user.password_hash.startswith("$argon2")
    assert user.role == UserRole.PATIENT.value
    assert user.is_active is True
    assert user.mfa_enabled is False


@pytest.mark.asyncio
async def test_auth_registration_duplicate_email_raises_conflict(db_session: AsyncSession) -> None:
    """Verify duplicate email registration raises ConflictException."""
    service = AuthService(db_session)
    request = UserRegisterRequest(
        email="duplicate@example.com",
        password="SecurePassw0rd!",
        role=UserRole.PATIENT,
    )
    await service.register(request)

    with pytest.raises(ConflictException) as exc_info:
        await service.register(request)
    assert exc_info.value.error_code == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_auth_login_invalid_credentials_raises_unauthorized(db_session: AsyncSession) -> None:
    """Verify invalid credentials raise UnauthorizedException."""
    service = AuthService(db_session)
    request = UserRegisterRequest(
        email="valid@example.com",
        password="CorrectPassword1!",
        role=UserRole.PATIENT,
    )
    await service.register(request)

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login(UserLoginRequest(email="valid@example.com", password="WrongPass!"))
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_auth_login_nonexistent_user_raises_unauthorized(db_session: AsyncSession) -> None:
    """Verify login with unknown email raises UnauthorizedException."""
    service = AuthService(db_session)
    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login(UserLoginRequest(email="ghost@example.com", password="AnyPassword1!"))
    assert exc_info.value.error_code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_auth_mfa_enroll_and_verify(db_session: AsyncSession) -> None:
    """Verify TOTP MFA enrollment generates a valid provisioning URI and secret."""
    service = AuthService(db_session)
    user_req = UserRegisterRequest(
        email="mfa.user@example.com",
        password="StrongMFAPass1!",
        role=UserRole.PATIENT,
    )
    user = await service.register(user_req)
    enroll = await service.enroll_mfa(user.id)

    assert enroll.secret is not None
    assert len(enroll.secret) == 32
    assert "otpauth" in enroll.provisioning_uri
    uri = enroll.provisioning_uri
    assert "mfa.user%40example.com" in uri or "mfa.user" in uri


@pytest.mark.asyncio
async def test_auth_refresh_token_reuse_detection(db_session: AsyncSession) -> None:
    """Verify stolen/reused refresh token triggers family revocation."""
    service = AuthService(db_session)
    user_req = UserRegisterRequest(
        email="reuse.detect@example.com",
        password="SecureToken123!",
        role=UserRole.PATIENT,
    )
    await service.register(user_req)

    # Issue initial token pair via login
    login_response = await service.login(
        UserLoginRequest(email="reuse.detect@example.com", password="SecureToken123!")
    )
    assert login_response.tokens is not None
    raw_refresh = login_response.tokens.refresh_token

    # First refresh: legitimate, consumes the token
    new_tokens = await service.refresh_tokens(raw_refresh)
    assert new_tokens.refresh_token != raw_refresh

    # Second use of the ORIGINAL token: theft detection triggers family revocation
    with pytest.raises(UnauthorizedException) as exc_info:
        await service.refresh_tokens(raw_refresh)
    assert exc_info.value.error_code == "TOKEN_THEFT_DETECTED"


@pytest.mark.asyncio
async def test_auth_logout_revokes_refresh_token(db_session: AsyncSession) -> None:
    """Verify logout properly revokes the refresh token."""
    service = AuthService(db_session)
    user_req = UserRegisterRequest(
        email="logout.test@example.com",
        password="SecureLogout12!",
        role=UserRole.PATIENT,
    )
    await service.register(user_req)

    login_response = await service.login(
        UserLoginRequest(email="logout.test@example.com", password="SecureLogout12!")
    )
    assert login_response.tokens is not None
    refresh_token = login_response.tokens.refresh_token
    access_token = login_response.tokens.access_token

    payload = decode_jwt_token(access_token)
    await service.logout(
        access_token_jti=payload.get("jti"),
        refresh_token_str=refresh_token,
        access_token_exp=payload.get("exp"),
    )

    # Post-logout: refresh token should be revoked
    with pytest.raises(UnauthorizedException):
        await service.refresh_tokens(refresh_token)


# ============================================================================
# SECURITY MODULE UNIT TESTS
# ============================================================================


def test_jwt_with_extra_claims() -> None:
    """Verify extra JWT claims such as type are preserved through decode."""
    user_id = uuid4()
    token = create_jwt_token(
        subject=user_id,
        role="PATIENT",
        email="extra@example.com",
        expires_delta=timedelta(minutes=5),
        extra_claims={"type": "mfa_pending"},
    )
    payload = decode_jwt_token(token)
    assert payload["type"] == "mfa_pending"
    assert payload["sub"] == str(user_id)


def test_refresh_token_hash_consistency() -> None:
    """Verify refresh token hashing is deterministic."""
    raw_token = generate_random_token(48)
    h1 = hash_refresh_token(raw_token)
    h2 = hash_refresh_token(raw_token)
    assert h1 == h2
    assert len(h1) == 64


def test_mfa_invalid_code_rejects() -> None:
    """Verify TOTP verification rejects incorrect codes."""
    secret = generate_mfa_secret()
    assert verify_mfa_totp(secret, "000000") is False
    assert verify_mfa_totp(secret, "999999") is False


# ============================================================================
# CONSULTATION SERVICE STATE MACHINE TESTS
# ============================================================================


async def _create_test_patient(session: AsyncSession) -> User:
    """Helper to persist a test patient user."""
    user = User(
        email=f"patient.{uuid4().hex[:6]}@test.com",
        password_hash=hash_password("TestPass1!"),
        role=UserRole.PATIENT.value,
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_test_doctor_user(session: AsyncSession) -> tuple[User, Doctor]:
    """Helper to persist a test doctor user and doctor profile."""
    user = User(
        email=f"doctor.{uuid4().hex[:6]}@test.com",
        password_hash=hash_password("TestDocPass1!"),
        role=UserRole.DOCTOR.value,
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
    )
    session.add(user)
    await session.flush()

    doctor = Doctor(
        user_id=user.id,
        license_number=f"LIC-{uuid4().hex[:8]}",
        specialization="General Medicine",
        languages=["English"],
        experience_years=5,
        consultation_fee=Decimal("500.00"),
        is_available=True,
    )
    session.add(doctor)
    await session.flush()
    return user, doctor


async def _create_test_slot(session: AsyncSession, doctor: Doctor) -> AvailabilitySlot:
    """Helper to persist a future availability slot."""
    start_time = datetime.now(UTC) + timedelta(days=2)
    slot = AvailabilitySlot(
        doctor_id=doctor.id,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=30),
        status=SlotStatus.AVAILABLE.value,
    )
    session.add(slot)
    await session.flush()
    return slot


async def _create_booked_consultation(
    session: AsyncSession,
    patient: User,
    doctor: Doctor,
    slot: AvailabilitySlot,
    status: str = ConsultationStatus.SCHEDULED.value,
) -> Consultation:
    """Helper to persist a consultation in a given status."""
    slot.status = SlotStatus.BOOKED.value
    consultation = Consultation(
        patient_id=patient.id,
        doctor_id=doctor.id,
        availability_slot_id=slot.id,
        status=status,
        scheduled_start=slot.start_time,
        scheduled_end=slot.end_time,
    )
    session.add(consultation)
    await session.commit()
    return consultation


@pytest.mark.asyncio
async def test_consultation_only_patient_can_book(db_session: AsyncSession) -> None:
    """Verify doctors cannot book consultations (PATIENT-only action)."""
    _, doctor = await _create_test_doctor_user(db_session)
    doctor_user = await db_session.get(User, doctor.user_id)
    assert doctor_user is not None

    slot = await _create_test_slot(db_session, doctor)
    service = ConsultationService(db_session)

    with pytest.raises(ForbiddenException):
        await service.book_consultation(
            patient=doctor_user,
            request=BookingRequest(
                doctor_id=doctor.id,
                slot_id=slot.id,
                reason="Testing",
            ),
            idempotency_key=str(uuid4()),
        )


@pytest.mark.asyncio
async def test_consultation_start_requires_doctor_role(db_session: AsyncSession) -> None:
    """Verify only the assigned doctor can start a consultation."""
    patient = await _create_test_patient(db_session)
    _, doctor = await _create_test_doctor_user(db_session)
    slot = await _create_test_slot(db_session, doctor)
    consultation = await _create_booked_consultation(db_session, patient, doctor, slot)

    service = ConsultationService(db_session)

    # Patient trying to start consultation must fail
    with pytest.raises(ForbiddenException):
        await service.start_consultation(consultation.id, patient)


@pytest.mark.asyncio
async def test_consultation_invalid_state_transition_complete_before_start(
    db_session: AsyncSession,
) -> None:
    """Verify COMPLETED→SCHEDULED/IN_PROGRESS transitions are rejected."""
    patient = await _create_test_patient(db_session)
    doctor_user, doctor = await _create_test_doctor_user(db_session)
    slot = await _create_test_slot(db_session, doctor)

    # Create consultation already COMPLETED
    consultation = await _create_booked_consultation(
        db_session, patient, doctor, slot, ConsultationStatus.COMPLETED.value
    )
    service = ConsultationService(db_session)

    # Cannot start a COMPLETED consultation
    with pytest.raises(BadRequestException) as exc_info:
        await service.start_consultation(consultation.id, doctor_user)
    assert exc_info.value.error_code == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_consultation_cancel_invalid_from_completed(db_session: AsyncSession) -> None:
    """Verify COMPLETED consultations cannot be cancelled."""
    patient = await _create_test_patient(db_session)
    doctor_user, doctor = await _create_test_doctor_user(db_session)
    slot = await _create_test_slot(db_session, doctor)
    consultation = await _create_booked_consultation(
        db_session, patient, doctor, slot, ConsultationStatus.COMPLETED.value
    )

    service = ConsultationService(db_session)

    with pytest.raises(BadRequestException) as exc_info:
        await service.cancel_consultation(consultation.id, "Test cancellation", patient)
    assert exc_info.value.error_code == "INVALID_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_consultation_get_not_found_raises(db_session: AsyncSession) -> None:
    """Verify NotFoundException is raised for unknown consultation IDs."""
    patient = await _create_test_patient(db_session)
    service = ConsultationService(db_session)

    with pytest.raises(NotFoundException):
        await service.get_consultation(uuid4(), patient)


@pytest.mark.asyncio
async def test_consultation_idor_patient_cannot_access_other_patients(
    db_session: AsyncSession,
) -> None:
    """Verify a patient cannot access another patient's consultation (IDOR prevention)."""
    patient1 = await _create_test_patient(db_session)
    patient2 = await _create_test_patient(db_session)
    _, doctor = await _create_test_doctor_user(db_session)
    slot = await _create_test_slot(db_session, doctor)
    consultation = await _create_booked_consultation(db_session, patient1, doctor, slot)

    service = ConsultationService(db_session)

    with pytest.raises(ForbiddenException):
        await service.get_consultation(consultation.id, patient2)


# ============================================================================
# PRESCRIPTION SERVICE UNIT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_prescription_wrong_doctor_raises_forbidden(db_session: AsyncSession) -> None:
    """Verify a doctor cannot issue prescriptions for another doctor's consultation."""
    patient = await _create_test_patient(db_session)
    doctor_user1, doctor1 = await _create_test_doctor_user(db_session)
    doctor_user2, _ = await _create_test_doctor_user(db_session)
    slot = await _create_test_slot(db_session, doctor1)
    consultation = await _create_booked_consultation(
        db_session, patient, doctor1, slot, ConsultationStatus.IN_PROGRESS.value
    )

    service = PrescriptionService(db_session)
    rx_request = PrescriptionCreateRequest(
        diagnosis="Test Diagnosis",
        medications=[
            MedicationItem(
                name="Test Medicine",
                dosage="10mg",
                frequency="Once daily",
                duration="7 days",
            )
        ],
    )

    with pytest.raises(ForbiddenException):
        await service.issue_prescription(consultation.id, rx_request, doctor_user2)


@pytest.mark.asyncio
async def test_prescription_patient_cannot_issue(db_session: AsyncSession) -> None:
    """Verify patients cannot issue prescriptions."""
    patient = await _create_test_patient(db_session)
    _, doctor = await _create_test_doctor_user(db_session)
    slot = await _create_test_slot(db_session, doctor)
    consultation = await _create_booked_consultation(
        db_session, patient, doctor, slot, ConsultationStatus.IN_PROGRESS.value
    )

    service = PrescriptionService(db_session)
    rx_request = PrescriptionCreateRequest(
        diagnosis="Self Diagnosis",
        medications=[
            MedicationItem(
                name="Aspirin",
                dosage="500mg",
                frequency="As needed",
                duration="5 days",
            )
        ],
    )

    with pytest.raises(ForbiddenException):
        await service.issue_prescription(consultation.id, rx_request, patient)


@pytest.mark.asyncio
async def test_prescription_before_consultation_in_progress_fails(
    db_session: AsyncSession,
) -> None:
    """Verify prescriptions cannot be issued for SCHEDULED consultations."""
    patient = await _create_test_patient(db_session)
    doctor_user, doctor = await _create_test_doctor_user(db_session)
    slot = await _create_test_slot(db_session, doctor)
    consultation = await _create_booked_consultation(
        db_session, patient, doctor, slot, ConsultationStatus.SCHEDULED.value
    )

    service = PrescriptionService(db_session)
    rx_request = PrescriptionCreateRequest(
        diagnosis="Premature Diagnosis",
        medications=[
            MedicationItem(
                name="Medicine",
                dosage="10mg",
                frequency="Twice daily",
                duration="10 days",
            )
        ],
    )

    with pytest.raises(BadRequestException) as exc_info:
        await service.issue_prescription(consultation.id, rx_request, doctor_user)
    assert exc_info.value.error_code == "INVALID_CONSULTATION_STATUS"


@pytest.mark.asyncio
async def test_prescription_get_nonexistent_raises(db_session: AsyncSession) -> None:
    """Verify NotFoundException raised for unknown prescription ID."""
    patient = await _create_test_patient(db_session)
    service = PrescriptionService(db_session)

    with pytest.raises(NotFoundException):
        await service.get_prescription_by_id(uuid4(), patient)

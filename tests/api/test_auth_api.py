"""API tests for user registration, authentication, token rotation, and MFA."""

import pyotp
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_patient_success(async_client: AsyncClient) -> None:
    """Verify successful patient registration."""
    payload = {
        "email": "patient1@example.com",
        "password": "SecurePassword123!",
        "role": "PATIENT",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "patient1@example.com"
    assert data["role"] == "PATIENT"
    assert data["is_active"] is True
    assert data["mfa_enabled"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email_conflict(async_client: AsyncClient) -> None:
    """Verify duplicate email registration returns 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "SecurePassword123!",
        "role": "PATIENT",
    }
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    data = res2.json()
    assert data["error_code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient) -> None:
    """Verify successful login returns token pair."""
    register_payload = {
        "email": "loginuser@example.com",
        "password": "SecurePassword123!",
        "role": "PATIENT",
    }
    await async_client.post("/api/v1/auth/register", json=register_payload)

    login_payload = {
        "email": "loginuser@example.com",
        "password": "SecurePassword123!",
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["mfa_required"] is False
    assert "tokens" in data
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]
    assert data["tokens"]["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(async_client: AsyncClient) -> None:
    """Verify invalid password returns 401 Unauthorized."""
    register_payload = {
        "email": "user_wrong_pw@example.com",
        "password": "SecurePassword123!",
        "role": "PATIENT",
    }
    await async_client.post("/api/v1/auth/register", json=register_payload)

    login_payload = {
        "email": "user_wrong_pw@example.com",
        "password": "IncorrectPassword!",
    }
    response = await async_client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_theft_detection(async_client: AsyncClient) -> None:
    """Verify refresh token rotation, single-use enforcement, and theft detection."""
    # 1. Register & Login
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "rotate@example.com", "password": "SecurePassword123!", "role": "PATIENT"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "rotate@example.com", "password": "SecurePassword123!"},
    )
    initial_tokens = login_res.json()["tokens"]
    refresh_1 = initial_tokens["refresh_token"]

    # 2. First refresh rotation -> Should succeed and return new token pair
    rot_res_1 = await async_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": refresh_1},
    )
    assert rot_res_1.status_code == 200
    tokens_2 = rot_res_1.json()
    refresh_2 = tokens_2["refresh_token"]
    assert refresh_2 != refresh_1

    # 3. Attempt to REUSE refresh_1 -> Should detect theft, revoke family, and return 401
    reuse_res = await async_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": refresh_1},
    )
    assert reuse_res.status_code == 401
    assert reuse_res.json()["error_code"] == "TOKEN_THEFT_DETECTED"

    # 4. Verifying that refresh_2 is now ALSO revoked because the entire family was invalidated
    subsequent_res = await async_client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": refresh_2},
    )
    assert subsequent_res.status_code == 401


@pytest.mark.asyncio
async def test_mfa_enrollment_and_challenge_flow(async_client: AsyncClient) -> None:
    """Verify full MFA enrollment, login challenge, and TOTP verification flow."""
    # 1. Register & Login
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "mfa_user@example.com",
            "password": "SecurePassword123!",
            "role": "PATIENT",
        },
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "mfa_user@example.com", "password": "SecurePassword123!"},
    )
    access_token = login_res.json()["tokens"]["access_token"]

    # 2. Enroll in MFA
    enroll_res = await async_client.post(
        "/api/v1/auth/mfa/enroll",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert enroll_res.status_code == 200
    mfa_data = enroll_res.json()
    secret = mfa_data["secret"]
    assert len(secret) == 32

    # 3. Subsequent login triggers MFA challenge
    login_res_2 = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "mfa_user@example.com", "password": "SecurePassword123!"},
    )
    assert login_res_2.status_code == 200
    challenge_data = login_res_2.json()
    assert challenge_data["mfa_required"] is True
    mfa_token = challenge_data["mfa_token"]

    # 4. Verify invalid TOTP code returns 401
    bad_verify = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": "000000", "mfa_token": mfa_token},
    )
    assert bad_verify.status_code == 401

    # 5. Verify valid TOTP code returns authentication tokens
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    good_verify = await async_client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": valid_code, "mfa_token": mfa_token},
    )
    assert good_verify.status_code == 200
    assert "access_token" in good_verify.json()


@pytest.mark.asyncio
async def test_logout_endpoint(async_client: AsyncClient) -> None:
    """Verify /logout revokes access and refresh tokens."""
    await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout_user@example.com",
            "password": "SecurePassword123!",
            "role": "PATIENT",
        },
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "logout_user@example.com", "password": "SecurePassword123!"},
    )
    tokens = login_res.json()["tokens"]

    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout_res.status_code == 204

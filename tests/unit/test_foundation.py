"""Unit tests for Foundation components: health, security, hashing, tokens, and rate limits."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.common.utils import hash_payload, mask_sensitive_value
from app.core.security import (
    create_jwt_token,
    decode_jwt_token,
    generate_mfa_secret,
    hash_password,
    verify_mfa_totp,
    verify_password,
)


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient) -> None:
    """Verify /health liveness probe returns 200 ok."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.asyncio
async def test_metrics_endpoint(async_client: AsyncClient) -> None:
    """Verify /metrics exposes Prometheus metrics."""
    response = await async_client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_custom_request_id_preservation(async_client: AsyncClient) -> None:
    """Verify incoming X-Request-ID header is preserved."""
    custom_id = "test-custom-request-id-12345"
    response = await async_client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_argon2id_password_hashing() -> None:
    """Verify password hashing with Argon2id."""
    password = "MySecurePassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$argon2")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_encode_decode() -> None:
    """Verify JWT creation and claims validation."""
    user_id = uuid4()
    role = "PATIENT"
    email = "patient@example.com"
    token = create_jwt_token(subject=user_id, role=role, email=email)
    payload = decode_jwt_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["role"] == role
    assert payload["email"] == email
    assert "jti" in payload
    assert "exp" in payload


def test_totp_mfa_flow() -> None:
    """Verify TOTP generation and verification."""
    import pyotp

    secret = generate_mfa_secret()
    assert len(secret) == 32
    totp = pyotp.TOTP(secret)
    current_code = totp.now()

    assert verify_mfa_totp(secret, current_code) is True
    assert verify_mfa_totp(secret, "000000") is False


def test_payload_hash_determinism() -> None:
    """Verify payload hashing is deterministic regardless of key order."""
    payload_a = {"b": 2, "a": 1, "c": [1, 2, 3]}
    payload_b = {"a": 1, "c": [1, 2, 3], "b": 2}
    hash_a = hash_payload(payload_a)
    hash_b = hash_payload(payload_b)
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_mask_sensitive_value() -> None:
    """Verify masking utility."""
    val = "4111111111111234"
    masked = mask_sensitive_value(val)
    assert masked == "************1234"
    assert mask_sensitive_value("123") == "****"

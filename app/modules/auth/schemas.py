"""Pydantic schemas for authentication, token exchange, and MFA verification."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.common.constants import UserRole


class UserRegisterRequest(BaseModel):
    """User registration payload with strict input validation."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(description="Unique email address")
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Strong password with minimum 8 characters",
    )
    role: UserRole = Field(
        default=UserRole.PATIENT,
        description="Account role: PATIENT, DOCTOR, or ADMIN",
    )


class UserResponse(BaseModel):
    """Public user response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    created_at: datetime


class UserLoginRequest(BaseModel):
    """User credentials login payload."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Successful authentication token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(BaseModel):
    """Login response supporting immediate token issuance or MFA challenge."""

    mfa_required: bool = False
    mfa_token: str | None = None
    tokens: TokenResponse | None = None


class MFAEnrollResponse(BaseModel):
    """MFA enrollment setup containing TOTP secret and QR URI."""

    secret: str
    provisioning_uri: str


class MFAVerifyRequest(BaseModel):
    """TOTP MFA verification challenge request."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6, description="6-digit TOTP code")
    mfa_token: str = Field(description="Temporary token issued during password verification")


class TokenRefreshRequest(BaseModel):
    """Refresh token rotation request."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class LogoutRequest(BaseModel):
    """Logout request containing the refresh token to revoke."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = None

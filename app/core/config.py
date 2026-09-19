"""Application configuration settings using Pydantic v2 Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """System-wide configuration loaded from environment and .env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    APP_NAME: str = "Amrutam Telemedicine Backend"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # Security & Cryptography
    SECRET_KEY: str = Field(
        default="insecure-dev-secret-key-replace-in-production-min32bytes!!",
        description="Master cryptographic secret key",
    )
    JWT_SECRET_KEY: str = Field(
        default="insecure-dev-jwt-secret-key-replace-in-production-min32!!",
        description="HMAC secret key used for signing JWT access tokens",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_KID: str = "v1"
    JWT_PREVIOUS_KEYS: dict[str, str] = Field(
        default_factory=dict,
        description="Map of previous key identifiers to secrets for rotation grace periods",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MFA_ISSUER: str = "Amrutam Telemedicine"

    # Database (PostgreSQL)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/amrutam_db",
        description="Async PostgreSQL connection URI",
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600

    # Cache & Queue (Redis)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URI",
    )
    REDIS_SOCKET_TIMEOUT: int = 5

    # Rate Limiting (per minute)
    RATE_LIMIT_LOGIN_PER_MIN: int = 5
    RATE_LIMIT_CONSULTATION_PER_MIN: int = 20
    RATE_LIMIT_GENERAL_PER_MIN: int = 100

    # Cross-Origin Resource Sharing
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # Observability
    PROMETHEUS_METRICS_ENABLED: bool = True
    OPENTELEMETRY_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()

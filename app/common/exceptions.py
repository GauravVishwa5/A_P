"""Custom domain exception hierarchy and RFC 7807 problem detail response formatting."""

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """RFC 7807 compliant problem details error response."""

    type: str = Field(default="about:blank", description="URI reference identifying error type")
    title: str = Field(description="Short human-readable summary of problem")
    status: int = Field(description="HTTP status code")
    detail: str = Field(description="Human-readable explanation specific to this occurrence")
    instance: str = Field(description="URI reference identifying specific occurrence")
    error_code: str = Field(description="Machine-readable application error code")
    invalid_params: list[dict[str, Any]] | None = Field(
        default=None, description="Detailed validation error list if applicable"
    )


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        title: str = "Internal Server Error",
        error_code: str = "INTERNAL_SERVER_ERROR",
        invalid_params: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.title = title
        self.error_code = error_code
        self.invalid_params = invalid_params


class NotFoundException(AppException):
    """Resource not found (404)."""

    def __init__(
        self, detail: str = "Resource not found", error_code: str = "RESOURCE_NOT_FOUND"
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            error_code=error_code,
        )


class BadRequestException(AppException):
    """Invalid client request parameters (400)."""

    def __init__(self, detail: str = "Bad request", error_code: str = "BAD_REQUEST") -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Bad Request",
            error_code=error_code,
        )


class ConflictException(AppException):
    """Business invariant or resource state conflict (409)."""

    def __init__(
        self, detail: str = "Conflict with current state", error_code: str = "CONFLICT"
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            title="Conflict",
            error_code=error_code,
        )


class UnauthorizedException(AppException):
    """Authentication required or failed (401)."""

    def __init__(
        self, detail: str = "Authentication required", error_code: str = "UNAUTHORIZED"
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            title="Unauthorized",
            error_code=error_code,
        )


class ForbiddenException(AppException):
    """Insufficient permissions for resource (403)."""

    def __init__(
        self, detail: str = "Forbidden resource access", error_code: str = "FORBIDDEN"
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            title="Forbidden",
            error_code=error_code,
        )


class UnprocessableEntityException(AppException):
    """Semantic request body validation error (422)."""

    def __init__(
        self,
        detail: str = "Unprocessable entity",
        error_code: str = "UNPROCESSABLE_ENTITY",
        invalid_params: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            title="Unprocessable Entity",
            error_code=error_code,
            invalid_params=invalid_params,
        )


class RateLimitException(AppException):
    """Rate limit quota exceeded (429)."""

    def __init__(
        self,
        detail: str = "Rate limit exceeded. Please retry later.",
        retry_after: int = 60,
        error_code: str = "RATE_LIMIT_EXCEEDED",
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            title="Too Many Requests",
            error_code=error_code,
        )
        self.retry_after = retry_after


class ServiceUnavailableException(AppException):
    """Upstream service or dependency unavailable (503)."""

    def __init__(
        self, detail: str = "Service unavailable", error_code: str = "SERVICE_UNAVAILABLE"
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            title="Service Unavailable",
            error_code=error_code,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """FastAPI global exception handler for AppException hierarchy."""
    error = ErrorDetail(
        type=f"https://amrutam.co.in/errors/{exc.error_code.lower()}",
        title=exc.title,
        status=exc.status_code,
        detail=exc.detail,
        instance=request.url.path,
        error_code=exc.error_code,
        invalid_params=exc.invalid_params,
    )
    headers = {}
    if isinstance(exc, RateLimitException):
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=exc.status_code,
        content=error.model_dump(exclude_none=True),
        headers=headers,
    )

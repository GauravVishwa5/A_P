"""Middleware for request correlation, latency metrics, and security headers."""

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import request_id_ctx
from app.core.metrics import http_request_duration_seconds, http_requests_total

logger = logging.getLogger(__name__)
settings = get_settings()


class CorrelationAndMetricsMiddleware(BaseHTTPMiddleware):
    """Injects X-Request-ID, logs latency, and updates Prometheus metrics."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.time()

        # Extract or generate X-Request-ID
        req_id = request.headers.get("X-Request-ID")
        if not req_id:
            req_id = str(uuid4())

        # Bind to context variable for downstream logger calls
        token = request_id_ctx.set(req_id)

        try:
            response = await call_next(request)
        except Exception:
            duration = (time.time() - start_time) * 1000
            logger.exception(
                "Unhandled error during request processing",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": round(duration, 2),
                },
            )
            raise
        finally:
            request_id_ctx.reset(token)

        duration = (time.time() - start_time) * 1000
        duration_sec = duration / 1000.0

        # Inject X-Request-ID into response headers
        response.headers["X-Request-ID"] = req_id

        # Update Prometheus metrics
        endpoint = request.url.path
        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=str(response.status_code),
        ).inc()

        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration_sec)

        # Log request if not health or metrics check
        if not endpoint.startswith(("/health", "/ready", "/metrics")):
            logger.info(
                f"{request.method} {endpoint} -> {response.status_code} ({duration:.2f}ms)",
                extra={
                    "method": request.method,
                    "path": endpoint,
                    "status_code": response.status_code,
                    "duration_ms": round(duration, 2),
                },
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforce defense-in-depth HTTP security headers on all responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if request.url.path in ("/docs", "/redoc", "/openapi.json"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self' https://cdn.jsdelivr.net;"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

"""FastAPI application entrypoint, lifespan manager, and core route registration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.exceptions import AppException, app_exception_handler
from app.core.config import get_settings
from app.core.database import check_database_health, close_database
from app.core.logging import setup_logging
from app.core.metrics import get_metrics_content
from app.core.middleware import CorrelationAndMetricsMiddleware, SecurityHeadersMiddleware
from app.core.redis import check_redis_health, close_redis
from app.core.tracing import setup_tracing
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.availability.router import router as availability_router
from app.modules.consultations.router import router as consultations_router
from app.modules.doctors.router import router as doctors_router
from app.modules.payments.router import router as payments_router
from app.modules.prescriptions.router import router as prescriptions_router
from app.modules.users.router import router as users_router

settings = get_settings()
setup_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing database and Redis connection lifecycles."""
    yield
    await close_database()
    await close_redis()


def create_application() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Production-grade backend for Amrutam Telemedicine Platform",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware Pipeline
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationAndMetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers (AppException typed for Starlette handler registration)
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]

    # Core Health & Observability Endpoints
    @app.get("/health", tags=["System"], summary="Liveness Probe")
    async def liveness_probe() -> dict[str, str]:
        """Verify API container is alive without checking external dependencies."""
        return {"status": "ok"}

    @app.get("/ready", tags=["System"], summary="Readiness Probe")
    async def readiness_probe() -> JSONResponse:
        """Verify critical infrastructure dependencies (PostgreSQL and Redis)."""
        db_healthy = await check_database_health()
        redis_healthy = await check_redis_health()

        is_ready = db_healthy and redis_healthy
        content = {
            "status": "ready" if is_ready else "not_ready",
            "database": db_healthy,
            "redis": redis_healthy,
        }
        status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=status_code, content=content)

    @app.get("/metrics", tags=["System"], summary="Prometheus Metrics")
    async def metrics_probe() -> Response:
        """Expose Prometheus telemetry metrics."""
        content, content_type = get_metrics_content()
        return Response(content=content, media_type=content_type)

    # Register Domain Routers
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(doctors_router)
    app.include_router(availability_router)
    app.include_router(consultations_router)
    app.include_router(prescriptions_router)
    app.include_router(payments_router)
    app.include_router(audit_router)

    # Initialize Distributed Tracing
    setup_tracing(app, settings.APP_NAME)

    return app


app = create_application()

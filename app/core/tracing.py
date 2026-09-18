"""OpenTelemetry distributed tracing setup and instrumentation for FastAPI."""

import logging
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def setup_tracing(app: FastAPI, service_name: str = "amrutam-telemedicine") -> None:
    """Initialize OpenTelemetry tracer provider and instrument FastAPI app."""
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls="health,ready,metrics",
        )
        logger.info(f"OpenTelemetry tracing configured for service: {service_name}")
    except Exception as exc:  # pragma: no cover
        logger.warning(f"OpenTelemetry instrumentation failed or skipped: {exc}")


def get_current_trace_context() -> dict[str, Any]:
    """Retrieve current trace_id and span_id for structured log enrichment."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            return {
                "trace_id": format(ctx.trace_id, "032x"),
                "span_id": format(ctx.span_id, "016x"),
            }
    except Exception:
        pass
    return {}

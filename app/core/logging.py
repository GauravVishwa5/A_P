"""Structured JSON logging with request correlation and sensitive data redaction."""

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

# Context variables for request tracing across async tasks
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
actor_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("actor_id", default="")

SENSITIVE_PATTERNS = [
    re.compile(r'"password"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"token"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"mfa_secret"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r'"secret"\s*:\s*"[^"]*"', re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE),
]

LOG_EXTRA_KEYS = [
    "method",
    "path",
    "status_code",
    "duration_ms",
    "error_code",
    "action",
    "slot_id",
    "doctor_id",
]


def redact_sensitive_data(text: str) -> str:
    """Redact passwords, secrets, and bearer tokens from log text."""
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub('"[REDACTED]"', text)
    return text


class StructuredJsonFormatter(logging.Formatter):
    """Custom formatter producing single-line structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
        }

        # Inject request context if available
        req_id = request_id_ctx.get()
        if req_id:
            log_entry["request_id"] = req_id

        actor_id = actor_id_ctx.get()
        if actor_id:
            log_entry["actor_id"] = actor_id

        # Attach custom extra fields passed during logger calls
        for key in LOG_EXTRA_KEYS:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            log_entry["exception"] = redact_sensitive_data(record.exc_text)

        return json.dumps(log_entry)


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger with structured JSON output."""
    root = logging.getLogger()
    root.setLevel(log_level.upper())

    # Clear existing handlers
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(StructuredJsonFormatter())
    root.addHandler(stream_handler)

    # Silence overly verbose third-party loggers
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

"""Common utility functions for time, hashing, and data masking."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


def utcnow() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def generate_uuid() -> UUID:
    """Generate a random UUIDv4."""
    return uuid4()


def hash_payload(payload: dict[str, Any] | str | bytes) -> str:
    """Generate deterministic SHA-256 hash of a request payload for idempotency checking."""
    if isinstance(payload, dict):
        # Sort keys to ensure deterministic serialization regardless of key order
        serialized = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    elif isinstance(payload, str):
        serialized = payload.encode("utf-8")
    else:
        serialized = payload
    return hashlib.sha256(serialized).hexdigest()


def mask_sensitive_value(val: str, visible_chars: int = 4) -> str:
    """Mask sensitive string (e.g. card/token), showing only the last N characters."""
    if not val or len(val) <= visible_chars:
        return "****"
    return f"{'*' * (len(val) - visible_chars)}{val[-visible_chars:]}"

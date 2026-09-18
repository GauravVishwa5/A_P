"""Redis-backed sliding-window rate limiter with graceful failure handling."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from redis.asyncio import Redis

from app.common.exceptions import RateLimitException
from app.core.config import get_settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()


async def is_rate_limited(
    key: str,
    limit: int,
    window_seconds: int = 60,
    fail_closed: bool = False,
) -> tuple[bool, int]:
    """
    Check if a key has exceeded `limit` requests within `window_seconds` using Redis sliding window.
    Returns: (is_limited, retry_after_seconds)
    """
    try:
        redis: Redis = get_redis_client()
        now = time.time()
        clear_before = now - window_seconds
        pipe = redis.pipeline()

        # Remove requests older than the sliding window
        pipe.zremrangebyscore(key, 0, clear_before)
        # Add current request with current timestamp as score
        pipe.zadd(key, {f"{now}": now})
        # Count requests in window
        pipe.zcard(key)
        # Set expiry for cleanup
        pipe.expire(key, window_seconds + 5)

        results = await pipe.execute()
        current_count = int(results[2])

        if current_count > limit:
            return True, window_seconds
        return False, 0
    except Exception as exc:
        logger.warning(f"Rate limiter Redis error on key {key}: {exc}")
        if fail_closed:
            # Sensitive endpoints (e.g. login) fail closed if Redis is down
            return True, window_seconds
        # General endpoints fail open to maintain availability
        return False, 0


def rate_limiter(
    limit: int,
    key_prefix: str,
    window_seconds: int = 60,
    fail_closed: bool = False,
    identifier_func: Callable[[Request], str] | None = None,
) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency to enforce rate limits per IP or authenticated user."""

    async def dependency(request: Request) -> None:
        if identifier_func:
            ident = identifier_func(request)
        else:
            ident = request.client.host if request.client else "127.0.0.1"

        rate_key = f"rate_limit:{key_prefix}:{ident}"
        limited, retry_after = await is_rate_limited(
            key=rate_key,
            limit=limit,
            window_seconds=window_seconds,
            fail_closed=fail_closed,
        )
        if limited:
            raise RateLimitException(
                detail=f"Too many requests for {key_prefix}. Please wait {retry_after} seconds.",
                retry_after=retry_after,
            )

    return dependency

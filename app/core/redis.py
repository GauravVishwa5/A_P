"""Asynchronous Redis client and connection pool management."""

import logging

from redis.asyncio import ConnectionPool, Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return singleton asynchronous Redis client."""
    global _redis_pool, _redis_client
    if _redis_client is None:
        _redis_pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            decode_responses=True,
            max_connections=50,
        )
        _redis_client = Redis(connection_pool=_redis_pool)
    return _redis_client


async def close_redis() -> None:
    """Close Redis client and connection pool."""
    global _redis_client, _redis_pool
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
    logger.info("Redis connection pool closed.")


async def check_redis_health() -> bool:
    """Execute ping command to verify Redis connectivity."""
    try:
        client = get_redis_client()
        return await client.ping() is True
    except Exception as exc:
        logger.warning(f"Redis health check failed: {exc}")
        return False

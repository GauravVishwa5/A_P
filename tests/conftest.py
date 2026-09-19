import tempfile
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.rate_limit as rate_limit_module
import app.core.redis as redis_module
import app.core.security as security_module
from app.core.database import Base, get_db_session
from app.core.models import *  # noqa: F403
from app.main import app


class MockPipeline:
    """Mock Redis pipeline supporting sliding window zset commands."""

    def __init__(self, mock_redis: "InMemoryMockRedis") -> None:
        self.mock_redis = mock_redis
        self.commands: list[tuple[str, tuple[Any, ...]]] = []

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> "MockPipeline":
        self.commands.append(("zremrangebyscore", (key, min_score, max_score)))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> "MockPipeline":
        self.commands.append(("zadd", (key, mapping)))
        return self

    def zcard(self, key: str) -> "MockPipeline":
        self.commands.append(("zcard", (key,)))
        return self

    def expire(self, key: str, ttl: int) -> "MockPipeline":
        self.commands.append(("expire", (key, ttl)))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for cmd, args in self.commands:
            if cmd == "zremrangebyscore":
                key, min_s, max_s = args
                zset = self.mock_redis._zsets.setdefault(key, {})
                to_remove = [k for k, score in zset.items() if min_s <= score <= max_s]
                for k in to_remove:
                    del zset[k]
                results.append(len(to_remove))
            elif cmd == "zadd":
                key, mapping = args
                zset = self.mock_redis._zsets.setdefault(key, {})
                zset.update(mapping)
                results.append(len(mapping))
            elif cmd == "zcard":
                key = args[0]
                zset = self.mock_redis._zsets.get(key, {})
                results.append(len(zset))
            elif cmd == "expire":
                results.append(True)
        return results


class InMemoryMockRedis:
    """Lightweight pure-Python in-memory mock for Redis without event-loop binding constraints."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, val: Any, ex: int | None = None) -> bool:
        self._store[key] = str(val)
        return True

    async def setex(self, key: str, ttl: int, val: Any) -> bool:
        self._store[key] = str(val)
        return True

    async def delete(self, *keys: str) -> bool:
        for k in keys:
            self._store.pop(k, None)
            self._zsets.pop(k, None)
        return True

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        pass

    async def flushall(self) -> bool:
        self._store.clear()
        self._zsets.clear()
        return True

    def pipeline(self) -> MockPipeline:
        return MockPipeline(self)


mock_redis_instance = InMemoryMockRedis()
redis_module._redis_client = mock_redis_instance  # type: ignore[assignment]
redis_module.get_redis_client = lambda: mock_redis_instance  # type: ignore[assignment,return-value]
rate_limit_module.get_redis_client = lambda: mock_redis_instance  # type: ignore[assignment,return-value]
security_module.get_redis_client = lambda: mock_redis_instance  # type: ignore[assignment,return-value]





_test_db_path = tempfile.mktemp(suffix="_test_telemed.db")
test_engine = create_async_engine(
    f"sqlite+aiosqlite:///{_test_db_path}",
    pool_size=100,
    max_overflow=50,
    echo=False,
)


@event.listens_for(test_engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


db_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
test_session_factory = db_session_factory
test_session_factory.__test__ = False  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_test_database() -> AsyncGenerator[None, None]:
    """Create all tables and reset in-memory state before each test."""
    await mock_redis_instance.flushall()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override get_db_session dependency for tests using in-memory database."""
    async with db_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db_session] = override_get_db


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session for direct unit testing."""
    async with db_session_factory() as session:
        yield session


@pytest.fixture
def app_instance() -> FastAPI:
    """Provide FastAPI application instance for testing."""
    return app


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP client bound to the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

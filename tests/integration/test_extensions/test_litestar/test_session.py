"""Integration tests for Litestar session backend extensions.

These tests run against actual database instances to verify that session backends
work correctly across all supported database backends.
"""

import asyncio
import datetime
import uuid
from collections.abc import AsyncGenerator, Generator
from functools import partial
from typing import Optional
from unittest.mock import Mock

import pytest
from litestar import Litestar, Request, get, post
from litestar.middleware.session import SessionMiddleware
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.stores.base import Store
from litestar.testing import AsyncTestClient
from sqlalchemy import Engine, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.base import UUIDv7Base
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.session import (
    SessionModelMixin,
    SQLAlchemyAsyncSessionBackend,
    SQLAlchemySyncSessionBackend,
)

pytestmark = [
    pytest.mark.integration,
]


class IntegrationTestSessionModel(SessionModelMixin, UUIDv7Base):
    """Test session model for integration tests."""

    __tablename__ = "integration_test_sessions"


@pytest.fixture
def test_session_model() -> type[SessionModelMixin]:
    """Return the test session model."""
    return IntegrationTestSessionModel


@pytest.fixture
def mock_store() -> Store:
    """Create a mock store for testing."""
    return Mock(spec=Store)


# Session backend fixtures
@pytest.fixture
def sync_session_config(engine: Engine) -> SQLAlchemySyncConfig:
    """Create sync config with test engine."""
    return SQLAlchemySyncConfig(
        engine_instance=engine,
        session_dependency_key="db_session",
    )


@pytest.fixture
async def async_session_config(async_engine: AsyncEngine) -> SQLAlchemyAsyncConfig:
    """Create async config with test engine."""
    return SQLAlchemyAsyncConfig(
        engine_instance=async_engine,
        session_dependency_key="db_session",
    )


@pytest.fixture
def sync_session_backend(
    sync_session_config: SQLAlchemySyncConfig, test_session_model: type[SessionModelMixin]
) -> SQLAlchemySyncSessionBackend:
    """Create sync session backend."""
    return SQLAlchemySyncSessionBackend(
        config=ServerSideSessionConfig(max_age=3600),
        alchemy_config=sync_session_config,
        model=test_session_model,
    )


@pytest.fixture
async def async_session_backend(
    async_session_config: SQLAlchemyAsyncConfig, test_session_model: type[SessionModelMixin]
) -> SQLAlchemyAsyncSessionBackend:
    """Create async session backend."""
    return SQLAlchemyAsyncSessionBackend(
        config=ServerSideSessionConfig(max_age=3600),
        alchemy_config=async_session_config,
        model=test_session_model,
    )


# Database setup fixtures
@pytest.fixture
def setup_sync_database(engine: Engine, test_session_model: type[SessionModelMixin]) -> Generator[None, None, None]:
    """Set up database tables for sync tests."""
    test_session_model.metadata.create_all(engine)
    yield
    test_session_model.metadata.drop_all(engine, checkfirst=True)


@pytest.fixture
async def setup_async_database(
    async_engine: AsyncEngine, test_session_model: type[SessionModelMixin]
) -> AsyncGenerator[None, None]:
    """Set up database tables for async tests."""
    async with async_engine.begin() as conn:
        await conn.run_sync(test_session_model.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: test_session_model.metadata.drop_all(sync_conn, checkfirst=True))


def _handle_database_encoding(data: Optional[bytes], expected: bytes, dialect_name: str) -> None:
    """Handle database-specific encoding issues."""
    if dialect_name.startswith("spanner") and data != expected:
        import base64

        # Spanner base64 encodes binary data
        if data:
            try:
                decoded_data = base64.b64decode(data)
                assert decoded_data == expected, f"Expected {expected!r}, got decoded {decoded_data!r} from {data!r}"
            except Exception:
                assert data == expected, f"Spanner: Expected {expected!r}, got {data!r}"
        return

    assert data == expected, f"Expected {expected!r}, got {data!r}"


# Session Backend Tests
async def test_async_session_backend_complete_lifecycle(
    async_session_backend: SQLAlchemyAsyncSessionBackend,
    async_session: AsyncSession,
    mock_store: Store,
    setup_async_database: None,
) -> None:
    """Test complete session lifecycle: create, retrieve, update, delete."""
    session_id = str(uuid.uuid4())
    original_data = b"test_data_123"
    updated_data = b"updated_data_456"

    dialect_name = getattr(async_session.bind.dialect, "name", "")

    # Create session
    await async_session_backend.set(session_id, original_data, mock_store)

    # Retrieve session
    retrieved_data = await async_session_backend.get(session_id, mock_store)
    _handle_database_encoding(retrieved_data, original_data, dialect_name)

    # Update session
    await async_session_backend.set(session_id, updated_data, mock_store)

    # Verify update
    retrieved_data = await async_session_backend.get(session_id, mock_store)
    _handle_database_encoding(retrieved_data, updated_data, dialect_name)

    # Delete session
    await async_session_backend.delete(session_id, mock_store)

    # Verify deletion
    retrieved_data = await async_session_backend.get(session_id, mock_store)
    assert retrieved_data is None


async def test_sync_session_backend_complete_lifecycle(
    sync_session_backend: SQLAlchemySyncSessionBackend,
    session: Session,
    mock_store: Store,
    setup_sync_database: None,
) -> None:
    """Test complete session lifecycle with sync backend."""
    session_id = str(uuid.uuid4())
    original_data = b"sync_test_data"
    updated_data = b"sync_updated_data"

    # Skip mock engines
    if session.bind is not None and getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = getattr(session.bind.dialect, "name", "") if session.bind is not None else ""

    # Create session
    await sync_session_backend.set(session_id, original_data, mock_store)

    # Retrieve session
    retrieved_data = await sync_session_backend.get(session_id, mock_store)
    _handle_database_encoding(retrieved_data, original_data, dialect_name)

    # Update session
    await sync_session_backend.set(session_id, updated_data, mock_store)

    # Verify update
    retrieved_data = await sync_session_backend.get(session_id, mock_store)
    _handle_database_encoding(retrieved_data, updated_data, dialect_name)

    # Delete session
    await sync_session_backend.delete(session_id, mock_store)

    # Verify deletion
    retrieved_data = await sync_session_backend.get(session_id, mock_store)
    assert retrieved_data is None


async def test_async_session_backend_expiration(
    async_engine: AsyncEngine,
    test_session_model: type[SessionModelMixin],
    mock_store: Store,
    setup_async_database: None,
) -> None:
    """Test session expiration handling."""
    # Skip mock engines
    if getattr(async_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    # Create config with very short expiration
    config = SQLAlchemyAsyncConfig(
        engine_instance=async_engine,
        session_dependency_key="db_session",
    )

    backend = SQLAlchemyAsyncSessionBackend(
        config=ServerSideSessionConfig(max_age=1),  # 1 second
        alchemy_config=config,
        model=test_session_model,
    )

    session_id = str(uuid.uuid4())
    data = b"expires_soon"

    # Create session
    await backend.set(session_id, data, mock_store)

    # Verify it exists
    retrieved_data = await backend.get(session_id, mock_store)
    dialect_name = getattr(async_engine.dialect, "name", "")
    _handle_database_encoding(retrieved_data, data, dialect_name)

    # Wait for expiration
    await asyncio.sleep(2)

    # Should return None and delete expired session
    assert await backend.get(session_id, mock_store) is None


async def test_async_session_backend_delete_all(
    async_session_backend: SQLAlchemyAsyncSessionBackend,
    mock_store: Store,
    setup_async_database: None,
) -> None:
    """Test deletion of all sessions."""
    # Skip mock engines
    engine_instance = async_session_backend.alchemy.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    # Create multiple sessions
    session_ids = [str(uuid.uuid4()) for _ in range(5)]
    for sid in session_ids:
        await async_session_backend.set(sid, b"data", mock_store)

    # Delete all
    await async_session_backend.delete_all(mock_store)

    # Verify all deleted
    for sid in session_ids:
        assert await async_session_backend.get(sid, mock_store) is None


async def test_async_session_backend_delete_expired(
    async_session_backend: SQLAlchemyAsyncSessionBackend,
    async_session: AsyncSession,
    mock_store: Store,
    setup_async_database: None,
) -> None:
    """Test bulk deletion of expired sessions."""
    # Skip mock engines
    if getattr(async_session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    now = datetime.datetime.now(datetime.timezone.utc)
    test_session_model = async_session_backend.model

    # Create mix of expired and active sessions
    expired_ids = [str(uuid.uuid4()) for _ in range(3)]
    active_ids = [str(uuid.uuid4()) for _ in range(2)]

    # Insert expired sessions directly
    async with async_session_backend.alchemy.get_session() as db_session:
        for sid in expired_ids:
            session_obj = test_session_model(
                session_id=sid,
                data=b"expired",
                expires_at=now - datetime.timedelta(hours=1),
            )
            db_session.add(session_obj)
        await db_session.commit()

    # Create active sessions through backend
    for sid in active_ids:
        await async_session_backend.set(sid, b"active", mock_store)

    # Delete expired
    await async_session_backend.delete_expired()

    # Verify only active sessions remain
    async with async_session_backend.alchemy.get_session() as db_session:
        result = await db_session.execute(select(test_session_model.session_id))
        remaining_ids = {row[0] for row in result}
        assert remaining_ids == set(active_ids)


# Litestar Integration Tests
async def test_async_session_middleware_integration(
    async_engine: AsyncEngine,
    test_session_model: type[SessionModelMixin],
    setup_async_database: None,
) -> None:
    """Test async session backend with Litestar middleware."""
    # Skip mock engines
    if getattr(async_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    config = SQLAlchemyAsyncConfig(
        engine_instance=async_engine,
        session_dependency_key="db_session",
    )

    backend = SQLAlchemyAsyncSessionBackend(
        config=ServerSideSessionConfig(max_age=3600, key="test-session"),
        alchemy_config=config,
        model=test_session_model,
    )

    @get("/set")
    async def set_session(request: Request) -> "dict[str, str]":
        request.session["user_id"] = "123"
        request.session["username"] = "testuser"
        return {"status": "session set"}

    @get("/get")
    async def get_session(request: Request) -> "dict[str, Optional[str]]":
        return {
            "user_id": request.session.get("user_id"),
            "username": request.session.get("username"),
        }

    @post("/clear")
    async def clear_session(request: Request) -> "dict[str, str]":
        request.clear_session()
        return {"status": "session cleared"}

    app = Litestar(
        route_handlers=[set_session, get_session, clear_session],
        middleware=[partial(SessionMiddleware, backend=backend)],
    )

    async with AsyncTestClient(app=app) as client:
        # Set session data
        response = await client.get("/set")
        assert response.status_code == 200
        assert response.json() == {"status": "session set"}

        # Get session data
        response = await client.get("/get")
        assert response.status_code == 200
        assert response.json() == {"user_id": "123", "username": "testuser"}

        # Clear session
        response = await client.post("/clear")
        assert response.status_code == 201
        assert response.json() == {"status": "session cleared"}

        # Verify cleared
        response = await client.get("/get")
        assert response.status_code == 200
        assert response.json() == {"user_id": None, "username": None}


async def test_sync_session_middleware_integration(
    engine: Engine,
    test_session_model: type[SessionModelMixin],
    setup_sync_database: None,
) -> None:
    """Test sync session backend with Litestar middleware."""
    # Skip mock engines
    if getattr(engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    config = SQLAlchemySyncConfig(
        engine_instance=engine,
        session_dependency_key="db_session",
    )

    backend = SQLAlchemySyncSessionBackend(
        config=ServerSideSessionConfig(max_age=3600, key="test-session"),
        alchemy_config=config,
        model=test_session_model,
    )

    @get("/set", sync_to_thread=False)
    def set_session(request: Request) -> "dict[str, int]":
        counter = request.session.get("counter", 0) + 1
        request.session["counter"] = counter
        return {"counter": counter}

    @get("/get", sync_to_thread=False)
    def get_session(request: Request) -> "dict[str, Optional[int]]":
        return {"counter": request.session.get("counter")}

    app = Litestar(
        route_handlers=[set_session, get_session],
        middleware=[partial(SessionMiddleware, backend=backend)],
    )

    async with AsyncTestClient(app=app) as client:
        # Initial set
        response = await client.get("/set")
        assert response.status_code == 200
        assert response.json() == {"counter": 1}

        # Increment counter
        response = await client.get("/set")
        assert response.status_code == 200
        assert response.json() == {"counter": 2}

        # Get current value
        response = await client.get("/get")
        assert response.status_code == 200
        assert response.json() == {"counter": 2}

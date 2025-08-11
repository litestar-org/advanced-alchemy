"""Integration tests for Litestar session backend with real databases."""

import asyncio
import datetime
import uuid
from collections.abc import AsyncGenerator, Generator
from functools import partial
from typing import Optional, Union
from unittest.mock import Mock

import pytest
from litestar import Litestar, Request, get, post
from litestar.middleware.session import SessionMiddleware
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.stores.base import Store
from litestar.testing import AsyncTestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.base import UUIDv7Base
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.session import (
    SessionModelMixin,
    SQLAlchemyAsyncSessionBackend,
    SQLAlchemySyncSessionBackend,
)


class AsyncSessionModel(SessionModelMixin, UUIDv7Base):
    """Test session model for async tests."""

    __tablename__ = "async_test_sessions"


class SyncSessionModel(SessionModelMixin, UUIDv7Base):
    """Test session model for sync tests."""

    __tablename__ = "sync_test_sessions"


@pytest.fixture()
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an async SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(UUIDv7Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def sync_engine() -> Generator[Engine, None, None]:
    """Create a sync SQLite engine for testing."""
    import os
    import tempfile

    # Create a temporary file for the database
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        engine = create_engine(f"sqlite:///{db_path}")
        UUIDv7Base.metadata.create_all(engine)
        yield engine
        engine.dispose()
    finally:
        # Clean up the temporary file
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture()
async def async_session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory."""
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture()
def sync_session_factory(sync_engine: Engine) -> sessionmaker[Session]:
    """Create sync session factory."""
    return sessionmaker(sync_engine, expire_on_commit=False)


@pytest.fixture()
def mock_store() -> Store:
    """Create a mock store for testing."""
    return Mock(spec=Store)


@pytest.mark.xdist_group("litestar_session")
class TestAsyncSessionBackendIntegration:
    """Integration tests for async session backend."""

    @pytest.fixture()
    async def async_config(self, async_engine: AsyncEngine) -> SQLAlchemyAsyncConfig:
        """Create async config with test engine."""
        return SQLAlchemyAsyncConfig(
            engine_instance=async_engine,
            session_dependency_key="db_session",
        )

    @pytest.fixture()
    async def async_backend(self, async_config: SQLAlchemyAsyncConfig) -> SQLAlchemyAsyncSessionBackend:
        """Create async session backend."""
        return SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=async_config,
            model=AsyncSessionModel,
        )

    async def test_session_lifecycle(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_store: Store,
    ) -> None:
        """Test complete session lifecycle: create, retrieve, update, delete."""
        session_id = str(uuid.uuid4())
        original_data = b"test_data_123"
        updated_data = b"updated_data_456"

        # Create session
        await async_backend.set(session_id, original_data, mock_store)

        # Verify in database
        async with async_session_factory() as db_session:
            result = await db_session.execute(
                select(AsyncSessionModel).where(AsyncSessionModel.session_id == session_id)
            )
            session_obj = result.scalar_one()
            data_in_db = session_obj.data
            is_expired = session_obj.is_expired
            assert data_in_db == original_data
            assert not is_expired

        # Retrieve session
        retrieved_data = await async_backend.get(session_id, mock_store)
        assert retrieved_data == original_data

        # Update session
        await async_backend.set(session_id, updated_data, mock_store)

        # Verify update
        retrieved_data = await async_backend.get(session_id, mock_store)
        assert retrieved_data == updated_data

        # Delete session
        await async_backend.delete(session_id, mock_store)

        # Verify deletion
        retrieved_data = await async_backend.get(session_id, mock_store)
        assert retrieved_data is None

    async def test_session_expiration(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_store: Store,
    ) -> None:
        """Test session expiration handling."""
        # Create backend with very short expiration
        config = SQLAlchemyAsyncConfig(
            engine_instance=async_session_factory.kw["bind"],
            session_dependency_key="db_session",
        )

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=1),  # 1 second
            alchemy_config=config,
            model=AsyncSessionModel,
        )

        session_id = str(uuid.uuid4())
        data = b"expires_soon"

        # Create session
        await backend.set(session_id, data, mock_store)

        # Verify it exists
        assert await backend.get(session_id, mock_store) == data

        # Wait for expiration
        await asyncio.sleep(2)

        # Should return None and delete expired session
        assert await backend.get(session_id, mock_store) is None

        # Verify it's deleted from database
        async with async_session_factory() as db_session:
            result = await db_session.execute(
                select(AsyncSessionModel).where(AsyncSessionModel.session_id == session_id)
            )
            assert result.scalar_one_or_none() is None

    async def test_delete_expired_sessions(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_store: Store,
    ) -> None:
        """Test bulk deletion of expired sessions."""
        now = datetime.datetime.now(datetime.timezone.utc)

        # Create mix of expired and active sessions
        expired_ids = [str(uuid.uuid4()) for _ in range(3)]
        active_ids = [str(uuid.uuid4()) for _ in range(2)]

        # Insert expired sessions directly
        async with async_session_factory() as db_session:
            for sid in expired_ids:
                session = AsyncSessionModel(
                    session_id=sid,
                    data=b"expired",
                    expires_at=now - datetime.timedelta(hours=1),
                )
                db_session.add(session)
            await db_session.commit()

        # Create active sessions through backend
        for sid in active_ids:
            await async_backend.set(sid, b"active", mock_store)

        # Delete expired
        await async_backend.delete_expired()

        # Verify only active sessions remain
        async with async_session_factory() as db_session:
            result = await db_session.execute(select(AsyncSessionModel.session_id))
            remaining_ids = {row[0] for row in result}
            assert remaining_ids == set(active_ids)

    async def test_delete_all_sessions(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        async_session_factory: async_sessionmaker[AsyncSession],
        mock_store: Store,
    ) -> None:
        """Test deletion of all sessions."""
        # Create multiple sessions
        session_ids = [str(uuid.uuid4()) for _ in range(5)]
        for sid in session_ids:
            await async_backend.set(sid, b"data", mock_store)

        # Verify they exist
        async with async_session_factory() as db_session:
            from sqlalchemy import func

            count = await db_session.scalar(select(func.count()).select_from(AsyncSessionModel))
            assert count == 5

        # Delete all
        await async_backend.delete_all(mock_store)

        # Verify all deleted
        async with async_session_factory() as db_session:
            from sqlalchemy import func

            count = await db_session.scalar(select(func.count()).select_from(AsyncSessionModel))
            assert count == 0

    async def test_concurrent_session_access(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        mock_store: Store,
    ) -> None:
        """Test concurrent access to sessions."""
        session_id = str(uuid.uuid4())

        # Initial set
        await async_backend.set(session_id, b"initial", mock_store)

        # Concurrent reads and writes
        async def read_session(n: int) -> Optional[bytes]:
            return await async_backend.get(session_id, mock_store)

        async def write_session(n: int) -> None:
            await async_backend.set(session_id, f"data_{n}".encode(), mock_store)

        # Run concurrent operations
        tasks = []
        for i in range(10):
            tasks.append(read_session(i))
            tasks.append(write_session(i))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify no exceptions
        for result in results:
            if isinstance(result, Exception):
                raise result

        # Verify session still exists and has valid data
        final_data = await async_backend.get(session_id, mock_store)
        assert final_data is not None
        assert final_data.startswith(b"data_")


@pytest.mark.xdist_group("litestar_session")
class TestSyncSessionBackendIntegration:
    """Integration tests for sync session backend."""

    @pytest.fixture()
    def sync_config(self, sync_engine: Engine) -> SQLAlchemySyncConfig:
        """Create sync config with test engine."""
        return SQLAlchemySyncConfig(
            engine_instance=sync_engine,
            session_dependency_key="db_session",
        )

    @pytest.fixture()
    def sync_backend(self, sync_config: SQLAlchemySyncConfig) -> SQLAlchemySyncSessionBackend:
        """Create sync session backend."""
        return SQLAlchemySyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=sync_config,
            model=SyncSessionModel,
        )

    @pytest.mark.asyncio()
    async def test_session_lifecycle(
        self,
        sync_backend: SQLAlchemySyncSessionBackend,
        sync_session_factory: sessionmaker[Session],
        mock_store: Store,
    ) -> None:
        """Test complete session lifecycle with sync backend."""
        session_id = str(uuid.uuid4())
        original_data = b"sync_test_data"
        updated_data = b"sync_updated_data"

        # Create session
        await sync_backend.set(session_id, original_data, mock_store)

        # Verify in database
        with sync_session_factory() as db_session:
            result = db_session.execute(select(SyncSessionModel).where(SyncSessionModel.session_id == session_id))
            session_obj = result.scalar_one()
            data_in_db = session_obj.data
            is_expired = session_obj.is_expired
            assert data_in_db == original_data
            assert not is_expired

        # Retrieve session
        retrieved_data = await sync_backend.get(session_id, mock_store)
        assert retrieved_data == original_data

        # Update session
        await sync_backend.set(session_id, updated_data, mock_store)

        # Verify update
        retrieved_data = await sync_backend.get(session_id, mock_store)
        assert retrieved_data == updated_data

        # Delete session
        await sync_backend.delete(session_id, mock_store)

        # Verify deletion
        retrieved_data = await sync_backend.get(session_id, mock_store)
        assert retrieved_data is None

    @pytest.mark.asyncio()
    async def test_delete_expired_sessions(
        self,
        sync_backend: SQLAlchemySyncSessionBackend,
        sync_session_factory: sessionmaker[Session],
        mock_store: Store,
    ) -> None:
        """Test bulk deletion of expired sessions with sync backend."""
        now = datetime.datetime.now(datetime.timezone.utc)

        # Create mix of expired and active sessions
        expired_ids = [str(uuid.uuid4()) for _ in range(3)]
        active_ids = [str(uuid.uuid4()) for _ in range(2)]

        # Insert expired sessions directly
        with sync_session_factory() as db_session:
            for sid in expired_ids:
                session = SyncSessionModel(
                    session_id=sid,
                    data=b"expired",
                    expires_at=now - datetime.timedelta(hours=1),
                )
                db_session.add(session)
            db_session.commit()

        # Create active sessions through backend
        for sid in active_ids:
            await sync_backend.set(sid, b"active", mock_store)

        # Delete expired
        await sync_backend.delete_expired()

        # Verify only active sessions remain
        with sync_session_factory() as db_session:
            result = db_session.execute(select(SyncSessionModel.session_id))
            remaining_ids = {row[0] for row in result}
            assert remaining_ids == set(active_ids)


@pytest.mark.xdist_group("litestar_session")
class TestLitestarIntegration:
    """Test session backend integration with Litestar."""

    async def test_async_session_middleware(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test async session backend with Litestar middleware."""
        config = SQLAlchemyAsyncConfig(
            engine_instance=async_session_factory.kw["bind"],
            session_dependency_key="db_session",
        )

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600, key="test-session"),
            alchemy_config=config,
            model=AsyncSessionModel,
        )

        @get("/set")
        async def set_session(request: Request) -> dict[str, str]:
            request.session["user_id"] = "123"
            request.session["username"] = "testuser"
            return {"status": "session set"}

        @get("/get")
        async def get_session(request: Request) -> dict[str, Optional[str]]:
            return {
                "user_id": request.session.get("user_id"),
                "username": request.session.get("username"),
            }

        @post("/clear")
        async def clear_session(request: Request) -> dict[str, str]:
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

    async def test_sync_session_middleware(
        self,
        sync_session_factory: sessionmaker[Session],
    ) -> None:
        """Test sync session backend with Litestar middleware."""
        config = SQLAlchemySyncConfig(
            engine_instance=sync_session_factory.kw["bind"],
            session_dependency_key="db_session",
        )

        backend = SQLAlchemySyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600, key="test-session"),
            alchemy_config=config,
            model=SyncSessionModel,
        )

        @get("/set")
        def set_session(request: Request) -> dict[str, str]:
            request.session["counter"] = request.session.get("counter", 0) + 1
            return {"counter": request.session["counter"]}

        @get("/get")
        def get_session(request: Request) -> dict[str, Optional[int]]:
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

    async def test_session_persistence_across_requests(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that sessions persist across multiple requests."""
        config = SQLAlchemyAsyncConfig(
            engine_instance=async_session_factory.kw["bind"],
            session_dependency_key="db_session",
        )

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600, key="test-session"),
            alchemy_config=config,
            model=AsyncSessionModel,
        )

        @get("/login")
        async def login(request: Request) -> dict[str, str]:
            request.session["authenticated"] = True
            request.session["user_id"] = "user123"
            request.session["login_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            return {"status": "logged in"}

        @get("/profile")
        async def profile(request: Request) -> dict[str, Union[str, bool, None]]:
            if not request.session.get("authenticated"):
                return {"error": "not authenticated"}
            return {
                "user_id": request.session.get("user_id"),
                "login_time": request.session.get("login_time"),
            }

        @post("/logout")
        async def logout(request: Request) -> dict[str, str]:
            request.clear_session()
            return {"status": "logged out"}

        app = Litestar(
            route_handlers=[login, profile, logout],
            middleware=[partial(SessionMiddleware, backend=backend)],
        )

        async with AsyncTestClient(app=app) as client:
            # Access profile before login
            response = await client.get("/profile")
            assert response.json() == {"error": "not authenticated"}

            # Login
            response = await client.get("/login")
            assert response.json() == {"status": "logged in"}

            # Access profile after login
            response = await client.get("/profile")
            data = response.json()
            assert data["user_id"] == "user123"
            assert "login_time" in data

            # Logout
            response = await client.post("/logout")
            assert response.json() == {"status": "logged out"}

            # Access profile after logout
            response = await client.get("/profile")
            assert response.json() == {"error": "not authenticated"}

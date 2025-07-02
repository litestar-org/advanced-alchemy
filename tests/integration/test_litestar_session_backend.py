"""Integration tests for Litestar session backend with real databases."""

import asyncio
import datetime
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Dict, Optional, Union

import pytest
from litestar import Litestar, Request, get, post
from litestar.middleware.session import SessionMiddleware
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.testing import AsyncTestClient, create_test_client
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


class SessionModel(SessionModelMixin, UUIDv7Base):
    """Test session model."""

    __tablename__ = "test_sessions"


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
    engine = create_engine("sqlite:///:memory:")
    UUIDv7Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
async def async_session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory."""
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture()
def sync_session_factory(sync_engine: Engine) -> sessionmaker[Session]:
    """Create sync session factory."""
    return sessionmaker(sync_engine, expire_on_commit=False)


class TestAsyncSessionBackendIntegration:
    """Integration tests for async session backend."""

    @pytest.fixture()
    async def async_config(self, async_session_factory: async_sessionmaker[AsyncSession]) -> SQLAlchemyAsyncConfig:
        """Create async config with test session factory."""
        config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            session_dependency_key="db_session",
        )
        # Override the session factory
        config.get_session = async_session_factory
        return config

    @pytest.fixture()
    async def async_backend(self, async_config: SQLAlchemyAsyncConfig) -> SQLAlchemyAsyncSessionBackend:
        """Create async session backend."""
        return SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=async_config,
            model=SessionModel,
        )

    async def test_session_lifecycle(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test complete session lifecycle: create, retrieve, update, delete."""
        session_id = str(uuid.uuid4())
        original_data = b"test_data_123"
        updated_data = b"updated_data_456"
        store = None  # Mock store

        # Create session
        await async_backend.set(session_id, original_data, store)

        # Verify in database
        async with async_session_factory() as db_session:
            result = await db_session.execute(select(SessionModel).where(SessionModel.session_id == session_id))
            session_obj = result.scalar_one()
            assert session_obj.data == original_data
            assert not session_obj.is_expired

        # Retrieve session
        retrieved_data = await async_backend.get(session_id, store)
        assert retrieved_data == original_data

        # Update session
        await async_backend.set(session_id, updated_data, store)

        # Verify update
        retrieved_data = await async_backend.get(session_id, store)
        assert retrieved_data == updated_data

        # Delete session
        await async_backend.delete(session_id, store)

        # Verify deletion
        retrieved_data = await async_backend.get(session_id, store)
        assert retrieved_data is None

    async def test_session_expiration(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test session expiration handling."""
        # Create backend with very short expiration
        config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            session_dependency_key="db_session",
        )
        config.get_session = async_session_factory

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=1),  # 1 second
            alchemy_config=config,
            model=SessionModel,
        )

        session_id = str(uuid.uuid4())
        data = b"expires_soon"
        store = None

        # Create session
        await backend.set(session_id, data, store)

        # Verify it exists
        assert await backend.get(session_id, store) == data

        # Wait for expiration
        await asyncio.sleep(2)

        # Should return None and delete expired session
        assert await backend.get(session_id, store) is None

        # Verify it's deleted from database
        async with async_session_factory() as db_session:
            result = await db_session.execute(select(SessionModel).where(SessionModel.session_id == session_id))
            assert result.scalar_one_or_none() is None

    async def test_delete_expired_sessions(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test bulk deletion of expired sessions."""
        store = None
        now = datetime.datetime.now(datetime.timezone.utc)

        # Create mix of expired and active sessions
        expired_ids = [str(uuid.uuid4()) for _ in range(3)]
        active_ids = [str(uuid.uuid4()) for _ in range(2)]

        # Insert expired sessions directly
        async with async_session_factory() as db_session:
            for sid in expired_ids:
                session = SessionModel(
                    session_id=sid,
                    data=b"expired",
                    expires_at=now - datetime.timedelta(hours=1),
                )
                db_session.add(session)
            await db_session.commit()

        # Create active sessions through backend
        for sid in active_ids:
            await async_backend.set(sid, b"active", store)

        # Delete expired
        await async_backend.delete_expired()

        # Verify only active sessions remain
        async with async_session_factory() as db_session:
            result = await db_session.execute(select(SessionModel.session_id))
            remaining_ids = {row[0] for row in result}
            assert remaining_ids == set(active_ids)

    async def test_delete_all_sessions(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test deletion of all sessions."""
        store = None

        # Create multiple sessions
        session_ids = [str(uuid.uuid4()) for _ in range(5)]
        for sid in session_ids:
            await async_backend.set(sid, b"data", store)

        # Verify they exist
        async with async_session_factory() as db_session:
            from sqlalchemy import func

            count = await db_session.scalar(select(func.count()).select_from(SessionModel))
            assert count == 5

        # Delete all
        await async_backend.delete_all(store)

        # Verify all deleted
        async with async_session_factory() as db_session:
            from sqlalchemy import func

            count = await db_session.scalar(select(func.count()).select_from(SessionModel))
            assert count == 0

    async def test_concurrent_session_access(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
    ) -> None:
        """Test concurrent access to sessions."""
        store = None
        session_id = str(uuid.uuid4())

        # Initial set
        await async_backend.set(session_id, b"initial", store)

        # Concurrent reads and writes
        async def read_session(n: int) -> Optional[bytes]:
            return await async_backend.get(session_id, store)

        async def write_session(n: int) -> None:
            await async_backend.set(session_id, f"data_{n}".encode(), store)

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
        final_data = await async_backend.get(session_id, store)
        assert final_data is not None
        assert final_data.startswith(b"data_")


class TestSyncSessionBackendIntegration:
    """Integration tests for sync session backend."""

    @pytest.fixture()
    def sync_config(self, sync_session_factory: sessionmaker[Session]) -> SQLAlchemySyncConfig:
        """Create sync config with test session factory."""
        config = SQLAlchemySyncConfig(
            connection_string="sqlite:///:memory:",
            session_dependency_key="db_session",
        )
        # Override the session factory
        config.get_session = sync_session_factory
        return config

    @pytest.fixture()
    def sync_backend(self, sync_config: SQLAlchemySyncConfig) -> SQLAlchemySyncSessionBackend:
        """Create sync session backend."""
        return SQLAlchemySyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=sync_config,
            model=SessionModel,
        )

    @pytest.mark.asyncio()
    async def test_session_lifecycle(
        self,
        sync_backend: SQLAlchemySyncSessionBackend,
        sync_session_factory: sessionmaker[Session],
    ) -> None:
        """Test complete session lifecycle with sync backend."""
        session_id = str(uuid.uuid4())
        original_data = b"sync_test_data"
        updated_data = b"sync_updated_data"
        store = None

        # Create session
        await sync_backend.set(session_id, original_data, store)

        # Verify in database
        with sync_session_factory() as db_session:
            result = db_session.execute(select(SessionModel).where(SessionModel.session_id == session_id))
            session_obj = result.scalar_one()
            assert session_obj.data == original_data
            assert not session_obj.is_expired

        # Retrieve session
        retrieved_data = await sync_backend.get(session_id, store)
        assert retrieved_data == original_data

        # Update session
        await sync_backend.set(session_id, updated_data, store)

        # Verify update
        retrieved_data = await sync_backend.get(session_id, store)
        assert retrieved_data == updated_data

        # Delete session
        await sync_backend.delete(session_id, store)

        # Verify deletion
        retrieved_data = await sync_backend.get(session_id, store)
        assert retrieved_data is None

    @pytest.mark.asyncio()
    async def test_delete_expired_sessions(
        self,
        sync_backend: SQLAlchemySyncSessionBackend,
        sync_session_factory: sessionmaker[Session],
    ) -> None:
        """Test bulk deletion of expired sessions with sync backend."""
        store = None
        now = datetime.datetime.now(datetime.timezone.utc)

        # Create mix of expired and active sessions
        expired_ids = [str(uuid.uuid4()) for _ in range(3)]
        active_ids = [str(uuid.uuid4()) for _ in range(2)]

        # Insert expired sessions directly
        with sync_session_factory() as db_session:
            for sid in expired_ids:
                session = SessionModel(
                    session_id=sid,
                    data=b"expired",
                    expires_at=now - datetime.timedelta(hours=1),
                )
                db_session.add(session)
            db_session.commit()

        # Create active sessions through backend
        for sid in active_ids:
            await sync_backend.set(sid, b"active", store)

        # Delete expired
        await sync_backend.delete_expired()

        # Verify only active sessions remain
        with sync_session_factory() as db_session:
            result = db_session.execute(select(SessionModel.session_id))
            remaining_ids = {row[0] for row in result}
            assert remaining_ids == set(active_ids)


class TestLitestarIntegration:
    """Test session backend integration with Litestar."""

    async def test_async_session_middleware(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test async session backend with Litestar middleware."""
        config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            session_dependency_key="db_session",
        )
        config.get_session = async_session_factory

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600, key="test-session"),
            alchemy_config=config,
            model=SessionModel,
        )

        @get("/set")
        async def set_session(request: Request) -> Dict[str, str]:
            request.session["user_id"] = "123"
            request.session["username"] = "testuser"
            return {"status": "session set"}

        @get("/get")
        async def get_session(request: Request) -> Dict[str, Optional[str]]:
            return {
                "user_id": request.session.get("user_id"),
                "username": request.session.get("username"),
            }

        @post("/clear")
        async def clear_session(request: Request) -> Dict[str, str]:
            request.clear_session()
            return {"status": "session cleared"}

        app = Litestar(
            route_handlers=[set_session, get_session, clear_session],
            middleware=[SessionMiddleware(backend=backend, key="test-session")],
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
            assert response.status_code == 200
            assert response.json() == {"status": "session cleared"}

            # Verify cleared
            response = await client.get("/get")
            assert response.status_code == 200
            assert response.json() == {"user_id": None, "username": None}

    def test_sync_session_middleware(
        self,
        sync_session_factory: sessionmaker[Session],
    ) -> None:
        """Test sync session backend with Litestar middleware."""
        config = SQLAlchemySyncConfig(
            connection_string="sqlite:///:memory:",
            session_dependency_key="db_session",
        )
        config.get_session = sync_session_factory

        backend = SQLAlchemySyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600, key="test-session"),
            alchemy_config=config,
            model=SessionModel,
        )

        @get("/set")
        def set_session(request: Request) -> Dict[str, str]:
            request.session["counter"] = request.session.get("counter", 0) + 1
            return {"counter": request.session["counter"]}

        @get("/get")
        def get_session(request: Request) -> Dict[str, Optional[int]]:
            return {"counter": request.session.get("counter")}

        app = Litestar(
            route_handlers=[set_session, get_session],
            middleware=[SessionMiddleware(backend=backend, key="test-session")],
        )

        with create_test_client(app=app) as client:
            # Initial set
            response = client.get("/set")
            assert response.status_code == 200
            assert response.json() == {"counter": 1}

            # Increment counter
            response = client.get("/set")
            assert response.status_code == 200
            assert response.json() == {"counter": 2}

            # Get current value
            response = client.get("/get")
            assert response.status_code == 200
            assert response.json() == {"counter": 2}

    async def test_session_persistence_across_requests(
        self,
        async_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that sessions persist across multiple requests."""
        config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            session_dependency_key="db_session",
        )
        config.get_session = async_session_factory

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600, key="test-session"),
            alchemy_config=config,
            model=SessionModel,
        )

        @get("/login")
        async def login(request: Request) -> Dict[str, str]:
            request.session["authenticated"] = True
            request.session["user_id"] = "user123"
            request.session["login_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            return {"status": "logged in"}

        @get("/profile")
        async def profile(request: Request) -> Dict[str, Union[str, bool]]:
            if not request.session.get("authenticated"):
                return {"error": "not authenticated"}
            return {
                "user_id": request.session.get("user_id"),
                "login_time": request.session.get("login_time"),
            }

        @post("/logout")
        async def logout(request: Request) -> Dict[str, str]:
            request.clear_session()
            return {"status": "logged out"}

        app = Litestar(
            route_handlers=[login, profile, logout],
            middleware=[SessionMiddleware(backend=backend, key="test-session")],
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

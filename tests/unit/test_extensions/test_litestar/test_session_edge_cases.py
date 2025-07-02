"""Edge case and error scenario tests for session backend."""

import datetime
import sys
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from litestar.middleware.session.server_side import ServerSideSessionConfig
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.session import (
    SessionModelMixin,
    SQLAlchemyAsyncSessionBackend,
    SQLAlchemySyncSessionBackend,
)


class MockSessionModel(SessionModelMixin):
    """Mock session model for testing."""

    __tablename__ = "test_sessions"


class MockSessionModelEdgeCases:
    """Test edge cases for SessionModelMixin."""

    def test_table_args_with_spanner_dialect(self) -> None:
        """Test table args generation for Spanner dialect."""
        dialect_mock = Mock()
        dialect_mock.name = "spanner+spanner"

        # Test that unique constraint is not created for Spanner
        result = MockSessionModel._create_unique_session_id_constraint(dialect=dialect_mock)
        assert result is False

        # Test that unique index is created for Spanner
        result = MockSessionModel._create_unique_session_id_index(dialect=dialect_mock)
        assert result is True

    def test_table_args_with_postgresql_dialect(self) -> None:
        """Test table args generation for PostgreSQL dialect."""
        dialect_mock = Mock()
        dialect_mock.name = "postgresql"

        # Test that unique constraint is created for PostgreSQL
        result = MockSessionModel._create_unique_session_id_constraint(dialect=dialect_mock)
        assert result is True

        # Test that unique index is not created for PostgreSQL
        result = MockSessionModel._create_unique_session_id_index(dialect=dialect_mock)
        assert result is False

    def test_is_expired_expression(self) -> None:
        """Test the SQL expression for is_expired."""
        # Access the expression property
        expr = MockSessionModel.is_expired
        assert expr is not None
        # The expression should contain a comparison with func.now()
        assert hasattr(expr, "expression")

    def test_session_model_fields(self) -> None:
        """Test that all required fields are present."""
        # Create an instance to check fields
        now = datetime.datetime.now(datetime.timezone.utc)
        session = MockSessionModel(
            session_id="test_123",
            data=b"test_data",
            expires_at=now + datetime.timedelta(hours=1),
        )

        assert session.session_id == "test_123"
        assert session.data == b"test_data"
        assert session.expires_at > now
        assert hasattr(session, "id")  # From UUIDv7Base


class TestAsyncBackendErrors:
    """Test error scenarios for async backend."""

    @pytest.fixture()
    def mock_async_config(self) -> MagicMock:
        """Create mock async config."""
        config = MagicMock(spec=SQLAlchemyAsyncConfig)
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        config.get_session.return_value = session
        return config

    @pytest.fixture()
    def async_backend(self, mock_async_config: MagicMock) -> SQLAlchemyAsyncSessionBackend:
        """Create async backend with mock config."""
        return SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=mock_async_config,
            model=MockSessionModel,
        )

    async def test_get_database_error(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        mock_async_config: MagicMock,
    ) -> None:
        """Test handling of database errors during get operation."""
        session = mock_async_config.get_session.return_value

        # Simulate database error
        session.scalars.side_effect = Exception("Database connection lost")

        with pytest.raises(Exception, match="Database connection lost"):
            await async_backend.get("session_123", Mock())

    async def test_set_database_error_on_commit(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        mock_async_config: MagicMock,
    ) -> None:
        """Test handling of database errors during set operation commit."""
        session = mock_async_config.get_session.return_value

        # Mock successful query but failed commit
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        # Make scalars return an awaitable that returns mock_result
        async def mock_scalars(*args, **kwargs):
            return mock_result

        session.scalars = mock_scalars
        session.commit.side_effect = Exception("Commit failed")

        with pytest.raises(Exception, match="Commit failed"):
            await async_backend.set("session_123", b"data", Mock())

    async def test_delete_database_error(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        mock_async_config: MagicMock,
    ) -> None:
        """Test handling of database errors during delete operation."""
        session = mock_async_config.get_session.return_value

        # Simulate database error
        session.execute.side_effect = Exception("Delete operation failed")

        with pytest.raises(Exception, match="Delete operation failed"):
            await async_backend.delete("session_123", Mock())

    async def test_concurrent_session_modification(
        self,
        async_backend: SQLAlchemyAsyncSessionBackend,
        mock_async_config: MagicMock,
    ) -> None:
        """Test behavior with concurrent session modifications."""
        session = mock_async_config.get_session.return_value

        # First call returns session, second call returns None (simulating deletion)
        mock_result1 = MagicMock()
        mock_result1.one_or_none.return_value = MockSessionModel(
            session_id="test",
            data=b"data",
            expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
        )

        mock_result2 = MagicMock()
        mock_result2.one_or_none.return_value = None

        # Create async functions that return our mock results
        async def mock_scalars_1(*args, **kwargs):
            return mock_result1

        async def mock_scalars_2(*args, **kwargs):
            return mock_result2

        # Use a generator to return different functions on each call
        scalars_calls = iter([mock_scalars_1, mock_scalars_2])
        session.scalars = lambda *args, **kwargs: next(scalars_calls)(*args, **kwargs)

        # First get should succeed
        result1 = await async_backend.get("test", Mock())
        assert result1 == b"data"

        # Second get should return None
        result2 = await async_backend.get("test", Mock())
        assert result2 is None


class TestSyncBackendErrors:
    """Test error scenarios for sync backend."""

    @pytest.fixture()
    def mock_sync_config(self) -> MagicMock:
        """Create mock sync config."""
        config = MagicMock(spec=SQLAlchemySyncConfig)
        session = MagicMock(spec=SyncSession)
        session.__enter__.return_value = session
        session.__exit__.return_value = None
        config.get_session.return_value = session
        return config

    @pytest.fixture()
    def sync_backend(self, mock_sync_config: MagicMock) -> SQLAlchemySyncSessionBackend:
        """Create sync backend with mock config."""
        return SQLAlchemySyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=mock_sync_config,
            model=MockSessionModel,
        )

    def test_get_sync_database_error(
        self,
        sync_backend: SQLAlchemySyncSessionBackend,
        mock_sync_config: MagicMock,
    ) -> None:
        """Test handling of database errors during sync get operation."""
        session = mock_sync_config.get_session.return_value
        session.scalars.side_effect = Exception("Database error")

        # The internal _get_sync should raise
        with pytest.raises(Exception, match="Database error"):
            sync_backend._get_sync("session_123")

    def test_set_sync_database_error(
        self,
        sync_backend: SQLAlchemySyncSessionBackend,
        mock_sync_config: MagicMock,
    ) -> None:
        """Test handling of database errors during sync set operation."""
        session = mock_sync_config.get_session.return_value
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        session.scalars.return_value = mock_result
        session.commit.side_effect = Exception("Commit failed")

        with pytest.raises(Exception, match="Commit failed"):
            sync_backend._set_sync("session_123", b"data")

    def test_delete_sync_constraint_violation(
        self,
        sync_backend: SQLAlchemySyncSessionBackend,
        mock_sync_config: MagicMock,
    ) -> None:
        """Test handling of constraint violations during delete."""
        session = mock_sync_config.get_session.return_value
        session.execute.side_effect = Exception("Foreign key constraint violation")

        with pytest.raises(Exception, match="Foreign key constraint violation"):
            sync_backend._delete_sync("session_123")


class TestConfigurationEdgeCases:
    """Test configuration edge cases."""

    def test_backend_with_zero_max_age(self) -> None:
        """Test backend behavior with zero max_age."""
        config = MagicMock(spec=SQLAlchemyAsyncConfig)
        session = MagicMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        config.get_session.return_value = session

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=0),  # Sessions expire immediately
            alchemy_config=config,
            model=MockSessionModel,
        )

        assert backend.config.max_age == 0

    def test_backend_config_property_setter(self) -> None:
        """Test that config property can be updated."""
        config = MagicMock(spec=SQLAlchemyAsyncConfig)

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=config,
            model=MockSessionModel,
        )

        # Test setter
        new_config = ServerSideSessionConfig(max_age=7200)
        backend.config = new_config
        assert backend.config.max_age == 7200

    def test_select_session_obj_query_generation(self) -> None:
        """Test the SQL query generation for selecting session objects."""
        config = MagicMock(spec=SQLAlchemyAsyncConfig)

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=config,
            model=MockSessionModel,
        )

        # Test query generation
        query = backend._select_session_obj("test_session_id")
        query_str = str(query)

        assert "test_sessions" in query_str
        assert "session_id" in query_str
        assert "WHERE" in query_str


class TestTimezoneHandling:
    """Test timezone handling across Python versions."""

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="Testing Python 3.11+ behavior")
    def test_get_utc_now_python_311_plus(self) -> None:
        """Test get_utc_now for Python 3.11+."""
        from advanced_alchemy.utils.time import get_utc_now

        now = get_utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo.utcoffset(None) == datetime.timedelta(0)

    @pytest.mark.skipif(sys.version_info >= (3, 11), reason="Testing Python <3.11 behavior")
    def test_get_utc_now_python_pre_311(self) -> None:
        """Test get_utc_now for Python versions before 3.11."""
        from advanced_alchemy.utils.time import get_utc_now

        now = get_utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo.utcoffset(None) == datetime.timedelta(0)

    def test_session_expiry_timezone_aware(self) -> None:
        """Test that session expiry is always timezone-aware."""
        from advanced_alchemy.utils.time import get_utc_now

        now = get_utc_now()
        future = now + datetime.timedelta(hours=1)
        past = now - datetime.timedelta(hours=1)

        # Create sessions with different expiry times
        active_session = MockSessionModel(
            session_id="active",
            data=b"data",
            expires_at=future,
        )
        expired_session = MockSessionModel(
            session_id="expired",
            data=b"data",
            expires_at=past,
        )

        # Both should have timezone-aware expires_at
        assert active_session.expires_at.tzinfo is not None
        assert expired_session.expires_at.tzinfo is not None

        # Test is_expired property
        assert not active_session.is_expired
        assert expired_session.is_expired


class TestLargeDataHandling:
    """Test handling of large session data."""

    @pytest.fixture()
    def large_data(self) -> bytes:
        """Generate large data for testing."""
        # 1MB of data
        return b"x" * (1024 * 1024)

    async def test_async_backend_large_data(
        self,
        large_data: bytes,
    ) -> None:
        """Test async backend with large data."""
        config = MagicMock(spec=SQLAlchemyAsyncConfig)
        session = MagicMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        config.get_session.return_value = session

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=config,
            model=MockSessionModel,
        )

        # Mock successful operations
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        async def mock_scalars(*args, **kwargs):
            return mock_result

        session.scalars = mock_scalars
        session.commit = AsyncMock()

        # Should handle large data without issues
        await backend.set("large_session", large_data, Mock())

        # Verify the data was passed correctly
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert added_obj.data == large_data

    def test_sync_backend_large_data(
        self,
        large_data: bytes,
    ) -> None:
        """Test sync backend with large data."""
        config = MagicMock(spec=SQLAlchemySyncConfig)
        session = MagicMock(spec=SyncSession)
        session.__enter__.return_value = session
        session.__exit__.return_value = None
        config.get_session.return_value = session

        backend = SQLAlchemySyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=config,
            model=MockSessionModel,
        )

        # Mock successful operations
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        session.scalars.return_value = mock_result

        # Should handle large data without issues
        backend._set_sync("large_session", large_data)

        # Verify the data was passed correctly
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert added_obj.data == large_data


class TestSessionIDValidation:
    """Test session ID handling edge cases."""

    @pytest.mark.parametrize(
        "session_id",
        [
            "",  # Empty string
            "a" * 256,  # Longer than field limit
            "session with spaces",
            "session/with/slashes",
            "session?with=query",
            "session#with#hash",
            "😀emoji-session",
            "\nsession\nwith\nnewlines",
        ],
    )
    async def test_various_session_ids(
        self,
        session_id: str,
    ) -> None:
        """Test handling of various session ID formats."""
        config = MagicMock(spec=SQLAlchemyAsyncConfig)
        session = MagicMock(spec=AsyncSession)
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        config.get_session.return_value = session

        backend = SQLAlchemyAsyncSessionBackend(
            config=ServerSideSessionConfig(max_age=3600),
            alchemy_config=config,
            model=MockSessionModel,
        )

        # Mock successful operations
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None

        async def mock_scalars(*args, **kwargs):
            return mock_result

        session.scalars = mock_scalars
        session.commit = AsyncMock()

        # Should handle any session ID format
        await backend.set(session_id, b"data", Mock())

        # Verify session was created
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]

        # For long session IDs, they should be truncated or handled appropriately
        if len(session_id) > 255:
            # Implementation should handle this appropriately
            assert len(added_obj.session_id) <= 255
        else:
            assert added_obj.session_id == session_id

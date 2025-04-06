import datetime
from collections.abc import Awaitable, Generator
from typing import Any, Callable, TypeVar
from unittest.mock import MagicMock, Mock, patch

import pytest
from litestar.middleware.session.server_side import ServerSideSessionConfig
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.session import (
    SessionModelMixin,
    SQLAlchemyAsyncSessionBackend,
    SQLAlchemySyncSessionBackend,
)
from advanced_alchemy.utils.time import get_utc_now

# Type variable for the callable in the patch
F = TypeVar("F", bound=Callable[..., Any])


class MockSessionModel(SessionModelMixin):
    """Mock session model for testing."""

    __tablename__ = "mock_session"


@pytest.fixture()
def mock_session_model() -> type[SessionModelMixin]:
    return MockSessionModel


@pytest.fixture()
def mock_async_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.__aenter__.return_value = session  # Simulate async context manager
    session.__aexit__.return_value = None
    return session


@pytest.fixture()
def mock_async_config(mock_session_model: type[SessionModelMixin], mock_async_session: MagicMock) -> MagicMock:
    config = MagicMock(spec=SQLAlchemyAsyncConfig)
    config.get_session.return_value = mock_async_session  # Configure the mock method
    return config


@pytest.fixture()
def mock_sync_session() -> MagicMock:
    session = MagicMock(spec=SyncSession)
    session.__enter__.return_value = session  # Simulate sync context manager
    session.__exit__.return_value = None
    return session


@pytest.fixture()
def mock_sync_config(mock_session_model: type[SessionModelMixin], mock_sync_session: MagicMock) -> MagicMock:
    config = MagicMock(spec=SQLAlchemySyncConfig)
    config.get_session.return_value = mock_sync_session  # Configure the mock method
    return config


@pytest.fixture()
def async_backend_config(
    mock_session_model: type[SessionModelMixin],
    mock_async_config: MagicMock,  # Use MagicMock type hint
) -> SQLAlchemyAsyncSessionBackend:
    return SQLAlchemyAsyncSessionBackend(
        model=mock_session_model,
        alchemy_config=mock_async_config,
        config=ServerSideSessionConfig(max_age=1000),
    )


def test_backend_config_post_init_valid(
    mock_session_model: type[SessionModelMixin], mock_async_config: MagicMock
) -> None:
    """Test SQLAlchemyBackendConfig initialization with valid parameters."""
    config = SQLAlchemyAsyncSessionBackend(
        model=mock_session_model,
        alchemy_config=mock_async_config,
        config=ServerSideSessionConfig(max_age=1000),
    )
    assert config.model is mock_session_model
    assert config.alchemy is mock_async_config


def test_backend_config_backend_class_async(
    mock_session_model: type[SessionModelMixin], mock_async_config: MagicMock
) -> None:
    """Test _backend_class property returns async backend for async config."""
    config = SQLAlchemyAsyncSessionBackend(
        model=mock_session_model,
        alchemy_config=mock_async_config,
        config=ServerSideSessionConfig(max_age=1000),
    )
    assert config._backend_class is SQLAlchemyAsyncSessionBackend  # pyright: ignore [reportPrivateUsage]


def test_backend_config_backend_class_sync(
    mock_session_model: type[SessionModelMixin], mock_sync_config: MagicMock
) -> None:
    """Test _backend_class property returns sync backend for sync config."""
    config = SQLAlchemySyncSessionBackend(
        model=mock_session_model,
        alchemy_config=mock_sync_config,
        config=ServerSideSessionConfig(max_age=1000),
    )
    assert config._backend_class is SQLAlchemySyncSessionBackend  # pyright: ignore [reportPrivateUsage]


# --- SessionModelMixin Tests ---


def test_session_model_mixin_is_expired_property() -> None:
    """Test the is_expired hybrid property."""
    now = get_utc_now()
    expired_session = SessionModelMixin(expires_at=now - datetime.timedelta(seconds=1))
    active_session = SessionModelMixin(expires_at=now + datetime.timedelta(seconds=10))

    assert expired_session.is_expired is True
    assert active_session.is_expired is False


def test_create_session_model_default_table_name() -> None:
    """Test creating a session model with the default table name."""

    class DefaultSessionModel(SessionModelMixin):
        """Default session model for testing."""

        __tablename__ = "session"

    assert issubclass(DefaultSessionModel, SessionModelMixin)
    assert DefaultSessionModel.__tablename__ == "session"


def test_create_session_model_custom_table_name() -> None:
    """Test creating a session model with a custom table name."""
    custom_name = "custom_user_sessions"

    class CustomSessionModel(SessionModelMixin):
        """Custom session model for testing."""

        __tablename__ = custom_name

    assert issubclass(CustomSessionModel, SessionModelMixin)
    assert CustomSessionModel.__tablename__ == custom_name


# --- SQLAlchemyAsyncSessionBackend Tests ---


@pytest.fixture()
def async_backend(async_backend_config: SQLAlchemyAsyncSessionBackend) -> SQLAlchemyAsyncSessionBackend:
    return async_backend_config


async def test_async_backend_get_session_obj_found(
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_session_model: type[SessionModelMixin],
    mock_async_session: MagicMock,  # Inject mock session directly
) -> None:
    """Test _get_session_obj finds an existing session."""
    mock_scalar_result = MagicMock()
    expected_session = mock_session_model(session_id="test_id", data=b"data", expires_at=get_utc_now())
    mock_scalar_result.one_or_none.return_value = expected_session
    mock_async_session.scalars.return_value = mock_scalar_result

    session_obj = await async_backend._get_session_obj(db_session=mock_async_session, session_id="test_id")  # pyright: ignore [reportPrivateUsage]

    assert session_obj is expected_session
    mock_async_session.scalars.assert_called_once()
    # Check the select statement structure loosely
    call_args, _ = mock_async_session.scalars.call_args
    select_stmt = call_args[0]
    assert str(select_stmt).startswith(f"SELECT {mock_session_model.__tablename__}")
    assert "WHERE" in str(select_stmt) and "session_id = :session_id_1" in str(select_stmt)


async def test_async_backend_get_session_obj_not_found(
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test _get_session_obj returns None when session not found."""
    mock_scalar_result = MagicMock()
    mock_scalar_result.one_or_none.return_value = None
    mock_async_session.scalars.return_value = mock_scalar_result

    session_obj = await async_backend._get_session_obj(db_session=mock_async_session, session_id="test_id")  # pyright: ignore [reportPrivateUsage]

    assert session_obj is None
    mock_async_session.scalars.assert_called_once()


@pytest.mark.asyncio()
@patch("advanced_alchemy.extensions.litestar.session.get_utc_now")
async def test_async_backend_get_existing_not_expired(
    mock_get_utc_now: Mock,
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test getting an existing, non-expired session."""
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_get_utc_now.return_value = now
    expires_at = now + datetime.timedelta(seconds=async_backend.config.max_age)
    session_data = b"session_data"
    session_id = "existing_session"

    mock_session_obj = mock_session_model(session_id=session_id, data=session_data, expires_at=expires_at)

    with patch.object(async_backend, "_get_session_obj", return_value=mock_session_obj) as mock_get_obj:
        result = await async_backend.get(session_id, store=Mock())

        assert result == session_data
        mock_get_obj.assert_awaited_once_with(db_session=mock_async_session, session_id=session_id)
        # Check expiry was updated
        assert mock_session_obj.expires_at > now  # Compare with current time instead of old expiry
        mock_async_session.commit.assert_awaited_once()
        mock_async_session.delete.assert_not_called()


@pytest.mark.asyncio()
@patch("advanced_alchemy.extensions.litestar.session.get_utc_now")
async def test_async_backend_get_existing_expired(
    mock_get_utc_now: Mock,
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test getting an expired session returns None and deletes it."""
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_get_utc_now.return_value = now
    expires_at = now - datetime.timedelta(seconds=1)  # Expired
    session_data = b"expired_data"
    session_id = "expired_session"

    mock_session_obj = mock_session_model(session_id=session_id, data=session_data, expires_at=expires_at)

    with patch.object(async_backend, "_get_session_obj", return_value=mock_session_obj) as mock_get_obj:
        result = await async_backend.get(session_id, store=Mock())

        assert result is None
        mock_get_obj.assert_awaited_once_with(db_session=mock_async_session, session_id=session_id)
        mock_async_session.delete.assert_awaited_once_with(mock_session_obj)
        mock_async_session.commit.assert_awaited_once()


async def test_async_backend_get_non_existent(
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test getting a non-existent session returns None."""
    session_id = "non_existent_session"
    with patch.object(async_backend, "_get_session_obj", return_value=None) as mock_get_obj:
        result = await async_backend.get(session_id, store=Mock())

        assert result is None
        mock_get_obj.assert_awaited_once_with(db_session=mock_async_session, session_id=session_id)
        mock_async_session.delete.assert_not_called()
        mock_async_session.commit.assert_not_called()  # Nothing to commit


@pytest.mark.asyncio()
@patch("advanced_alchemy.extensions.litestar.session.get_utc_now")
async def test_async_backend_set_new_session(
    mock_get_utc_now: Mock,
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test setting a new session."""
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_get_utc_now.return_value = now
    session_id = "new_session"
    data = b"new_data"

    with patch.object(async_backend, "_get_session_obj", return_value=None) as mock_get_obj:
        await async_backend.set(session_id, data, store=Mock())

        mock_get_obj.assert_awaited_once_with(db_session=mock_async_session, session_id=session_id)
        # Check add was called with a new model instance
        mock_async_session.add.assert_called_once()
        added_obj = mock_async_session.add.call_args[0][0]
        assert isinstance(added_obj, mock_session_model)
        assert added_obj.session_id == session_id
        assert added_obj.data == data
        assert added_obj.expires_at == now + datetime.timedelta(seconds=async_backend.config.max_age)
        mock_async_session.commit.assert_awaited_once()


@patch("advanced_alchemy.extensions.litestar.session.get_utc_now")
async def test_async_backend_set_update_existing_session(
    mock_get_utc_now: Mock,
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test updating an existing session's data and expiry."""
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_get_utc_now.return_value = now
    session_id = "existing_session_update"
    old_data = b"old_data"
    new_data = b"new_data"
    old_expires_at = now - datetime.timedelta(seconds=10)  # Pretend it was older

    mock_existing_session = mock_session_model(session_id=session_id, data=old_data, expires_at=old_expires_at)

    with patch.object(async_backend, "_get_session_obj", return_value=mock_existing_session) as mock_get_obj:
        await async_backend.set(session_id, new_data, store=Mock())

        mock_get_obj.assert_awaited_once_with(db_session=mock_async_session, session_id=session_id)
        mock_async_session.add.assert_not_called()  # Should not add new
        # Check data and expiry were updated on the existing object
        assert mock_existing_session.data == new_data
        assert mock_existing_session.expires_at == now + datetime.timedelta(seconds=async_backend.config.max_age)
        mock_async_session.commit.assert_awaited_once()


async def test_async_backend_delete_existing(
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test deleting an existing session."""
    session_id = "delete_me"
    await async_backend.delete(session_id, store=Mock())

    mock_async_session.execute.assert_awaited_once()
    # Check the delete statement structure loosely
    call_args, _ = mock_async_session.execute.call_args
    delete_stmt = call_args[0]
    assert str(delete_stmt).startswith(f"DELETE FROM {mock_session_model.__tablename__}")
    assert "WHERE" in str(delete_stmt) and "session_id = :session_id_1" in str(delete_stmt)
    mock_async_session.commit.assert_awaited_once()


@pytest.mark.asyncio()
async def test_async_backend_delete_non_existent(
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test deleting a non-existent session (fails silently)."""
    session_id = "i_dont_exist"
    await async_backend.delete(session_id, store=Mock())

    mock_async_session.execute.assert_awaited_once()  # Execute is still called
    mock_async_session.commit.assert_awaited_once()  # Commit happens regardless


@pytest.mark.asyncio()
async def test_async_backend_delete_all(
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test deleting all sessions."""
    await async_backend.delete_all(store=Mock())

    mock_async_session.execute.assert_awaited_once()
    # Check the delete statement structure loosely
    call_args, _ = mock_async_session.execute.call_args
    delete_stmt = call_args[0]
    assert str(delete_stmt) == f"DELETE FROM {mock_session_model.__tablename__}"  # No WHERE clause
    mock_async_session.commit.assert_awaited_once()


@pytest.mark.asyncio()
async def test_async_backend_delete_expired(
    async_backend: SQLAlchemyAsyncSessionBackend,
    mock_async_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    monkeypatch: MonkeyPatch,
    mock_async_session: MagicMock,  # Inject mock session
) -> None:
    """Test deleting expired sessions."""
    mock_async_session = mock_async_config.get_session.return_value
    mock_async_session.__aenter__.return_value = mock_async_session
    mock_async_session.__aexit__.return_value = None

    # Mock get_utc_now used inside the is_expired expression
    fixed_time = datetime.datetime.now(datetime.timezone.utc)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.session.get_utc_now", lambda: fixed_time)

    await async_backend.delete_expired()

    mock_async_session.execute.assert_awaited_once()
    # Check the delete statement structure loosely
    call_args, _ = mock_async_session.execute.call_args
    delete_stmt = call_args[0]
    assert str(delete_stmt).startswith(f"DELETE FROM {mock_session_model.__tablename__}")
    # Check for the expiration condition in the WHERE clause
    assert "WHERE" in str(delete_stmt) and "now() >" in str(delete_stmt)  # Match actual SQL
    mock_async_session.commit.assert_awaited_once()


# --- SQLAlchemySyncSessionBackend Tests ---

# Use async fixtures and tests because the public methods are async,
# wrapping the internal sync calls.


@pytest.fixture()
def sync_backend(mock_sync_config: MagicMock) -> Generator[SQLAlchemySyncSessionBackend, None, None]:
    mock_sync_config.get_session.return_value = MagicMock()
    mock_sync_config.get_session.return_value.__enter__.return_value = MagicMock()
    mock_sync_config.get_session.return_value.__exit__.return_value = None

    # Create a proper async wrapper for sync functions
    def mock_async_(fn: Callable[..., Any], **_: Any) -> Callable[..., Awaitable[Any]]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return wrapper

    with patch("advanced_alchemy.extensions.litestar.session.async_", side_effect=mock_async_):
        yield SQLAlchemySyncSessionBackend(
            config=ServerSideSessionConfig(max_age=1000),
            alchemy_config=mock_sync_config,
            model=MockSessionModel,
        )


@pytest.mark.asyncio()
async def test_sync_backend_get_wraps_sync_call(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test that sync backend's async get() calls the internal _get_sync."""
    session_id = "sync_test_get"
    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    # Mock the internal sync method to check if it's called
    mock_get_sync = MagicMock(return_value=b"data")
    with patch.object(sync_backend, "_get_sync", mock_get_sync):
        result = await sync_backend.get(session_id, store=Mock())
        assert result == b"data"
        mock_get_sync.assert_called_once_with(session_id)


@pytest.mark.asyncio()
async def test_sync_backend_set_wraps_sync_call(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test that sync backend's async set() calls the internal _set_sync."""
    session_id = "sync_test_set"
    data = b"set_data"
    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    mock_set_sync = MagicMock()
    with patch.object(sync_backend, "_set_sync", mock_set_sync):
        await sync_backend.set(session_id, data, store=Mock())
        mock_set_sync.assert_called_once_with(session_id, data)


@pytest.mark.asyncio()
async def test_sync_backend_delete_wraps_sync_call(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test that sync backend's async delete() calls the internal _delete_sync."""
    session_id = "sync_test_delete"
    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    mock_delete_sync = MagicMock()
    with patch.object(sync_backend, "_delete_sync", mock_delete_sync):
        await sync_backend.delete(session_id, store=Mock())
        mock_delete_sync.assert_called_once_with(session_id)


@pytest.mark.asyncio()
async def test_sync_backend_delete_all_wraps_sync_call(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test that sync backend's async delete_all() calls the internal _delete_all_sync."""
    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    mock_delete_all_sync = MagicMock()
    with patch.object(sync_backend, "_delete_all_sync", mock_delete_all_sync):
        await sync_backend.delete_all()
        mock_delete_all_sync.assert_called_once()


@pytest.mark.asyncio()
async def test_sync_backend_delete_expired_wraps_sync_call(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test that sync backend's async delete_expired() calls the internal _delete_expired_sync."""
    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    mock_delete_expired_sync = MagicMock()
    with patch.object(sync_backend, "_delete_expired_sync", mock_delete_expired_sync):
        await sync_backend.delete_expired()
        mock_delete_expired_sync.assert_called_once()


# --- Internal Sync Method Tests (_get_sync, _set_sync etc.) ---
# These run within the sync backend's methods, so we test them directly (not async)


def test_sync_backend_internal_get_sync_existing_not_expired(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    monkeypatch: MonkeyPatch,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _get_sync method for existing, non-expired session."""
    now = datetime.datetime.now(datetime.timezone.utc)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.session.get_utc_now", lambda: now)

    expires_at = now + datetime.timedelta(seconds=sync_backend.config.max_age)
    session_data = b"sync_session_data"
    session_id = "sync_existing_session"

    mock_session_obj = mock_session_model(session_id=session_id, data=session_data, expires_at=expires_at)

    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    # Mock _get_session_obj called by _get_sync
    with patch.object(sync_backend, "_get_session_obj", return_value=mock_session_obj) as mock_get_obj:
        result = sync_backend._get_sync(session_id)  # pyright: ignore [reportPrivateUsage]

        assert result == session_data
        mock_get_obj.assert_called_once_with(db_session=mock_sync_session, session_id=session_id)
        assert mock_session_obj.expires_at > now  # Compare with current time instead of old expiry
        mock_sync_session.commit.assert_called_once()
        mock_sync_session.delete.assert_not_called()


def test_sync_backend_internal_get_sync_existing_expired(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    monkeypatch: MonkeyPatch,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _get_sync method for an expired session."""
    now = datetime.datetime.now(datetime.timezone.utc)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.session.get_utc_now", lambda: now)

    expires_at = now - datetime.timedelta(seconds=1)  # Expired
    session_data = b"sync_expired_data"
    session_id = "sync_expired_session"

    mock_session_obj = mock_session_model(session_id=session_id, data=session_data, expires_at=expires_at)

    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    with patch.object(sync_backend, "_get_session_obj", return_value=mock_session_obj) as mock_get_obj:
        result = sync_backend._get_sync(session_id)  # pyright: ignore [reportPrivateUsage]

        assert result is None
        mock_get_obj.assert_called_once_with(db_session=mock_sync_session, session_id=session_id)
        mock_sync_session.delete.assert_called_once_with(mock_session_obj)
        mock_sync_session.commit.assert_called_once()


def test_sync_backend_internal_get_sync_non_existent(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _get_sync method for a non-existent session."""
    session_id = "sync_non_existent"
    mock_sync_session = mock_sync_config.get_session.return_value
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None

    with patch.object(sync_backend, "_get_session_obj", return_value=None) as mock_get_obj:
        result = sync_backend._get_sync(session_id)  # pyright: ignore [reportPrivateUsage]

        assert result is None
        mock_get_obj.assert_called_once_with(db_session=mock_sync_session, session_id=session_id)
        mock_sync_session.delete.assert_not_called()
        mock_sync_session.commit.assert_not_called()


def test_sync_backend_internal_set_sync_new(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    monkeypatch: MonkeyPatch,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _set_sync method for a new session."""
    now = datetime.datetime.now(datetime.timezone.utc)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.session.get_utc_now", lambda: now)

    session_id = "sync_new_set"
    data = b"sync_new_data"

    mock_sync_session = MagicMock(spec=SyncSession)
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None
    mock_sync_config.get_session.return_value = mock_sync_session

    with patch.object(sync_backend, "_get_session_obj", return_value=None) as mock_get_obj:
        sync_backend._set_sync(session_id, data)  # pyright: ignore [reportPrivateUsage]

        mock_get_obj.assert_called_once_with(db_session=mock_sync_session, session_id=session_id)
        # Check add was called with a new model instance
        mock_sync_session.add.assert_called_once()
        added_obj = mock_sync_session.add.call_args[0][0]
        assert isinstance(added_obj, mock_session_model)
        assert added_obj.session_id == session_id
        assert added_obj.data == data
        assert added_obj.expires_at == now + datetime.timedelta(seconds=sync_backend.config.max_age)
        mock_sync_session.commit.assert_called_once()


def test_sync_backend_internal_set_sync_update(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    monkeypatch: MonkeyPatch,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _set_sync method updating an existing session."""
    now = datetime.datetime.now(datetime.timezone.utc)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.session.get_utc_now", lambda: now)

    session_id = "sync_update_set"
    old_data = b"sync_old_data"
    new_data = b"sync_new_data"
    old_expires_at = now - datetime.timedelta(seconds=20)

    mock_existing_session = mock_session_model(session_id=session_id, data=old_data, expires_at=old_expires_at)

    mock_sync_session = MagicMock(spec=SyncSession)
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None
    mock_sync_config.get_session.return_value = mock_sync_session

    with patch.object(sync_backend, "_get_session_obj", return_value=mock_existing_session) as mock_get_obj:
        sync_backend._set_sync(session_id, new_data)  # pyright: ignore [reportPrivateUsage]

        mock_get_obj.assert_called_once_with(db_session=mock_sync_session, session_id=session_id)
        mock_sync_session.add.assert_not_called()  # Should not add new
        assert mock_existing_session.data == new_data
        assert mock_existing_session.expires_at == now + datetime.timedelta(seconds=sync_backend.config.max_age)
        mock_sync_session.commit.assert_called_once()


def test_sync_backend_internal_delete_sync(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _delete_sync method."""
    session_id = "sync_delete_me"
    mock_sync_session = MagicMock(spec=SyncSession)
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None
    mock_sync_config.get_session.return_value = mock_sync_session

    sync_backend._delete_sync(session_id)  # pyright: ignore [reportPrivateUsage]

    mock_sync_session.execute.assert_called_once()
    # Check the delete statement structure loosely
    call_args, _ = mock_sync_session.execute.call_args
    delete_stmt = call_args[0]
    assert str(delete_stmt).startswith(f"DELETE FROM {mock_session_model.__tablename__}")
    assert "WHERE" in str(delete_stmt) and "session_id = :session_id_1" in str(delete_stmt)
    mock_sync_session.commit.assert_called_once()


def test_sync_backend_internal_delete_all_sync(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _delete_all_sync method."""
    mock_sync_session = MagicMock(spec=SyncSession)
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None
    mock_sync_config.get_session.return_value = mock_sync_session

    sync_backend._delete_all_sync()  # pyright: ignore [reportPrivateUsage]

    mock_sync_session.execute.assert_called_once()
    # Check the delete statement structure loosely
    call_args, _ = mock_sync_session.execute.call_args
    delete_stmt = call_args[0]
    assert str(delete_stmt) == f"DELETE FROM {mock_session_model.__tablename__}"  # No WHERE clause
    mock_sync_session.commit.assert_called_once()


def test_sync_backend_internal_delete_expired_sync(
    sync_backend: SQLAlchemySyncSessionBackend,
    mock_sync_config: MagicMock,
    mock_session_model: type[SessionModelMixin],
    monkeypatch: MonkeyPatch,
    mock_sync_session: MagicMock,  # Inject mock session
) -> None:
    """Test the internal _delete_expired_sync method."""
    mock_sync_session = MagicMock(spec=SyncSession)
    mock_sync_session.__enter__.return_value = mock_sync_session
    mock_sync_session.__exit__.return_value = None
    mock_sync_config.get_session.return_value = mock_sync_session

    fixed_time = datetime.datetime.now(datetime.timezone.utc)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.session.get_utc_now", lambda: fixed_time)

    sync_backend._delete_expired_sync()  # pyright: ignore [reportPrivateUsage]

    mock_sync_session.execute.assert_called_once()
    # Check the delete statement structure loosely
    call_args, _ = mock_sync_session.execute.call_args
    delete_stmt = call_args[0]
    assert str(delete_stmt).startswith(f"DELETE FROM {mock_session_model.__tablename__}")
    assert "WHERE" in str(delete_stmt) and "now() >" in str(delete_stmt)  # Match actual SQL
    mock_sync_session.commit.assert_called_once()

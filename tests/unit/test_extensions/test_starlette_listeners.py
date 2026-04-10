"""Unit tests for Starlette SQLAlchemy config listener registration.

Regression tests for https://github.com/litestar-org/advanced-alchemy/issues/709.
Both Starlette async and sync configs override create_session_maker without
delegating to super(), silently dropping the listener registration performed
by the base class. These tests lock the contract per subclass.
"""

from unittest.mock import MagicMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import sessionmaker

from advanced_alchemy.config.common import GenericSQLAlchemyConfig
from advanced_alchemy.extensions.starlette.config import (
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)


# --- Async ---


def test_async_create_session_maker_registers_all_listeners() -> None:
    mock_session_maker = MagicMock(spec=async_sessionmaker)
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
        patch("advanced_alchemy.config.asyncio.sync_sessionmaker") as mock_sync_factory,
    ):
        mock_sync_maker = MagicMock()
        mock_sync_factory.return_value = mock_sync_maker
        result = config.create_session_maker()

    assert result is mock_session_maker
    assert mock_listen.call_count == 6
    mock_session_maker.configure.assert_called_once_with(sync_session_class=mock_sync_maker)


def test_async_create_session_maker_file_object_listener_disabled() -> None:
    mock_session_maker = MagicMock(spec=async_sessionmaker)
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///",
        enable_file_object_listener=False,
    )

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
        patch("advanced_alchemy.config.asyncio.sync_sessionmaker"),
    ):
        config.create_session_maker()

    assert mock_listen.call_count == 3


def test_async_create_session_maker_timestamp_listener_disabled() -> None:
    mock_session_maker = MagicMock(spec=async_sessionmaker)
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///",
        enable_touch_updated_timestamp_listener=False,
    )

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
        patch("advanced_alchemy.config.asyncio.sync_sessionmaker"),
    ):
        config.create_session_maker()

    assert mock_listen.call_count == 5


# --- Sync ---


def test_sync_create_session_maker_registers_all_listeners() -> None:
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
    ):
        result = config.create_session_maker()

    assert result is mock_session_maker
    assert mock_listen.call_count == 6


def test_sync_create_session_maker_file_object_listener_disabled() -> None:
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///",
        enable_file_object_listener=False,
    )

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
    ):
        config.create_session_maker()

    assert mock_listen.call_count == 3


def test_sync_create_session_maker_timestamp_listener_disabled() -> None:
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///",
        enable_touch_updated_timestamp_listener=False,
    )

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
    ):
        config.create_session_maker()

    assert mock_listen.call_count == 5

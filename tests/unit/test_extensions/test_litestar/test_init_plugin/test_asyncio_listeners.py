"""Unit tests for Litestar SQLAlchemyAsyncConfig listener registration.

Regression tests for https://github.com/litestar-org/advanced-alchemy/issues/709.
The Litestar subclass of SQLAlchemyAsyncConfig must register the base-class
listener set (file-object, timestamp, cache) when create_session_maker() is
called. Previously the subclass overrode create_session_maker without
delegating to super() and silently dropped every listener.
"""

from unittest.mock import MagicMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker

from advanced_alchemy.config.common import GenericSQLAlchemyConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import (
    SQLAlchemyAsyncConfig,
)


def test_create_session_maker_registers_all_listeners() -> None:
    """Default config registers 6 listeners on the synthetic sync_maker."""
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
    for call in mock_listen.call_args_list:
        assert call.args[0] is mock_sync_maker
    listener_events = {c.args[1] for c in mock_listen.call_args_list}
    assert {"before_flush", "after_commit", "after_rollback"} <= listener_events


def test_create_session_maker_file_object_listener_disabled() -> None:
    """With file-object listener disabled, only timestamp + cache listeners register (3)."""
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


def test_create_session_maker_timestamp_listener_disabled() -> None:
    """With timestamp listener disabled, only file-object + cache listeners register (5)."""
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

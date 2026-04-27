"""Shared helpers for extension listener-registration contract tests.

Used by ``test_flask_listeners.py``, ``test_sanic_listeners.py``, and
``test_starlette_listeners.py`` to eliminate duplication. Each extension's
async/sync config overrides ``create_session_maker``; these helpers patch
the base class's ``create_session_maker`` and ``sqlalchemy.event.listen``,
then assert the middle-layer listener-registration contract per subclass.

Regression helpers for
https://github.com/litestar-org/advanced-alchemy/issues/709.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import sessionmaker

from advanced_alchemy.config.common import GenericSQLAlchemyConfig

__all__ = (
    "assert_async_file_object_listener_disabled",
    "assert_async_registers_all_listeners",
    "assert_async_timestamp_listener_disabled",
    "assert_sync_file_object_listener_disabled",
    "assert_sync_registers_all_listeners",
    "assert_sync_timestamp_listener_disabled",
)

_ASYNC_URL = "sqlite+aiosqlite:///"
_SYNC_URL = "sqlite:///"


def _make_async_config(config_cls: type, **kwargs: Any) -> Any:
    """Build an async config with ``engine_instance`` pre-populated.

    Pre-populating ``engine_instance`` isolates listener-count assertions
    from the aiosqlite dialect's internal ``event.listen`` calls that
    would otherwise fire during ``get_engine()``.
    """
    config = config_cls(connection_string=_ASYNC_URL, **kwargs)
    config.engine_instance = MagicMock()
    return config


def _make_sync_config(config_cls: type, **kwargs: Any) -> Any:
    """Build a sync config with ``engine_instance`` pre-populated."""
    config = config_cls(connection_string=_SYNC_URL, **kwargs)
    config.engine_instance = MagicMock()
    return config


def assert_async_registers_all_listeners(config_cls: type) -> None:
    """Default async config registers 6 listeners on the synthetic sync_maker."""
    mock_session_maker = MagicMock(spec=async_sessionmaker)
    config = _make_async_config(config_cls)

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


def assert_async_file_object_listener_disabled(config_cls: type) -> None:
    """With file-object listener disabled, only timestamp + cache listeners register (3)."""
    mock_session_maker = MagicMock(spec=async_sessionmaker)
    config = _make_async_config(config_cls, enable_file_object_listener=False)

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


def assert_async_timestamp_listener_disabled(config_cls: type) -> None:
    """With timestamp listener disabled, only file-object + cache listeners register (5)."""
    mock_session_maker = MagicMock(spec=async_sessionmaker)
    config = _make_async_config(config_cls, enable_touch_updated_timestamp_listener=False)

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


def assert_sync_registers_all_listeners(config_cls: type) -> None:
    """Default sync config registers 6 listeners directly on the session_maker."""
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = _make_sync_config(config_cls)

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


def assert_sync_file_object_listener_disabled(config_cls: type) -> None:
    """With file-object listener disabled, only timestamp + cache listeners register (3)."""
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = _make_sync_config(config_cls, enable_file_object_listener=False)

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


def assert_sync_timestamp_listener_disabled(config_cls: type) -> None:
    """With timestamp listener disabled, only file-object + cache listeners register (5)."""
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = _make_sync_config(config_cls, enable_touch_updated_timestamp_listener=False)

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

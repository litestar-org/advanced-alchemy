"""Unit tests for SQLAlchemyAsyncConfig.create_session_maker and __post_init__."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.common import GenericSQLAlchemyConfig
from advanced_alchemy.exceptions import ImproperConfigurationError


def test_create_session_maker_returns_existing() -> None:
    """When session_maker is already set, return it without creating a new one."""
    existing_maker = MagicMock()
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")
    config.session_maker = existing_maker

    result = config.create_session_maker()
    assert result is existing_maker


def test_create_session_maker_standard_path() -> None:
    """Standard path creates a sessionmaker and registers all listeners."""
    mock_session_maker = MagicMock(spec=async_sessionmaker)

    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")

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
    # Should register: before_flush, after_commit, after_rollback for file object
    #                  before_flush for timestamp
    #                  after_commit, after_rollback for cache
    assert mock_listen.call_count == 6

    # Verify file object listeners
    listener_events = [c.args[1] for c in mock_listen.call_args_list]
    assert "before_flush" in listener_events
    assert "after_commit" in listener_events
    assert "after_rollback" in listener_events


def test_create_session_maker_file_object_listener_disabled() -> None:
    """Skips file object listener registration when disabled."""
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
    ):
        config.create_session_maker()

    # Without file object listener: timestamp (1) + cache (2) = 3
    assert mock_listen.call_count == 3


def test_create_session_maker_timestamp_listener_disabled() -> None:
    """Skips timestamp listener when disabled."""
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
    ):
        config.create_session_maker()

    # Without timestamp: file object (3) + cache (2) = 5
    assert mock_listen.call_count == 5


def test_post_init_routing_and_connection_string_conflict() -> None:
    """Raises ImproperConfigurationError when both routing_config and connection_string are set."""
    mock_routing = MagicMock()
    mock_routing.primary_connection_string = "sqlite+aiosqlite:///"

    with pytest.raises(ImproperConfigurationError, match="Provide either"):
        SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///",
            routing_config=mock_routing,
        )


def test_post_init_routing_config_sets_connection_string() -> None:
    """Routing config populates connection_string from primary."""
    mock_routing = MagicMock()
    mock_routing.primary_connection_string = "sqlite+aiosqlite:///routed"
    mock_routing.get_engine_configs.return_value = []

    config = SQLAlchemyAsyncConfig(routing_config=mock_routing)
    assert config.connection_string == "sqlite+aiosqlite:///routed"


def test_post_init_routing_config_fallback_to_engine_configs() -> None:
    """Falls back to engine configs when primary_connection_string is None."""
    mock_engine_config = MagicMock()
    mock_engine_config.connection_string = "sqlite+aiosqlite:///fallback"

    mock_routing = MagicMock()
    mock_routing.primary_connection_string = None
    mock_routing.default_group = "default"
    mock_routing.get_engine_configs.return_value = [mock_engine_config]

    config = SQLAlchemyAsyncConfig(routing_config=mock_routing)
    assert config.connection_string == "sqlite+aiosqlite:///fallback"

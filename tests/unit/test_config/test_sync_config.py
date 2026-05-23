"""Unit tests for SQLAlchemySyncConfig.create_session_maker and __post_init__."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from advanced_alchemy.config.common import GenericSQLAlchemyConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig, SyncSessionConfig
from advanced_alchemy.exceptions import ImproperConfigurationError


def test_create_session_maker_returns_existing() -> None:
    """When session_maker is already set, return it without creating a new one."""
    existing_maker = MagicMock()
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")
    config.session_maker = existing_maker

    result = config.create_session_maker()
    assert result is existing_maker


def test_create_session_maker_standard_path() -> None:
    """Standard path creates a sessionmaker and registers all listeners."""
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
    # Should register: before_flush, after_commit, after_rollback for file object
    #                  before_flush for timestamp
    #                  after_commit, after_rollback for cache
    assert mock_listen.call_count == 6

    listener_events = [c.args[1] for c in mock_listen.call_args_list]
    assert "before_flush" in listener_events
    assert "after_commit" in listener_events
    assert "after_rollback" in listener_events


def test_create_session_maker_file_object_listener_disabled() -> None:
    """Skips file object listener registration when disabled."""
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

    # Without file object listener: timestamp (1) + cache (2) = 3
    assert mock_listen.call_count == 3


def test_create_session_maker_timestamp_listener_disabled() -> None:
    """Skips timestamp listener when disabled."""
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

    # Without timestamp: file object (3) + cache (2) = 5
    assert mock_listen.call_count == 5


def test_post_init_routing_and_connection_string_conflict() -> None:
    """Raises ImproperConfigurationError when both routing_config and connection_string are set."""
    mock_routing = MagicMock()
    mock_routing.primary_connection_string = "sqlite:///"

    with pytest.raises(ImproperConfigurationError, match="Provide either"):
        SQLAlchemySyncConfig(
            connection_string="sqlite:///",
            routing_config=mock_routing,
        )


def test_post_init_routing_config_sets_connection_string() -> None:
    """Routing config populates connection_string from primary."""
    mock_routing = MagicMock()
    mock_routing.primary_connection_string = "sqlite:///routed"
    mock_routing.get_engine_configs.return_value = []

    config = SQLAlchemySyncConfig(routing_config=mock_routing)
    assert config.connection_string == "sqlite:///routed"


def test_post_init_routing_config_fallback_to_engine_configs() -> None:
    """Falls back to engine configs when primary_connection_string is None."""
    mock_engine_config = MagicMock()
    mock_engine_config.connection_string = "sqlite:///fallback"

    mock_routing = MagicMock()
    mock_routing.primary_connection_string = None
    mock_routing.default_group = "default"
    mock_routing.get_engine_configs.return_value = [mock_engine_config]

    config = SQLAlchemySyncConfig(routing_config=mock_routing)
    assert config.connection_string == "sqlite:///fallback"


def test_post_init_cache_config_builds_manager() -> None:
    """cache_config triggers CacheManager creation and propagation to session.info."""
    from advanced_alchemy.cache import CacheConfig, CacheManager

    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        cache_config=CacheConfig(backend="dogpile.cache.memory", expiration_time=300),
    )
    assert isinstance(config.cache_manager, CacheManager)
    info = config.session_config.info
    assert isinstance(info, dict)
    assert info["cache_manager"] is config.cache_manager


def test_post_init_cache_config_with_session_info_none_builds_manager() -> None:
    """cache_config propagates cache_manager when session_config.info is None."""
    from advanced_alchemy.cache import CacheConfig, CacheManager

    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        session_config=SyncSessionConfig(info=None),
        cache_config=CacheConfig(backend="dogpile.cache.memory", expiration_time=300),
    )
    assert isinstance(config.cache_manager, CacheManager)
    info = config.session_config.info
    assert isinstance(info, dict)
    assert info["file_object_raise_on_error"] is True
    assert info["cache_manager"] is config.cache_manager


def test_post_init_explicit_cache_manager_overrides() -> None:
    """An explicit cache_manager is preserved and propagated; cache_config is not re-instantiated."""
    from advanced_alchemy.cache import CacheConfig, CacheManager

    manager = CacheManager(CacheConfig(backend="dogpile.cache.memory"))
    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        cache_manager=manager,
    )
    assert config.cache_manager is manager
    info = config.session_config.info
    assert isinstance(info, dict)
    assert info["cache_manager"] is manager


def test_post_init_without_cache_config_leaves_info_clean() -> None:
    """No cache_config means no cache_manager key on session.info."""
    config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
    assert config.cache_manager is None
    info = config.session_config.info
    assert isinstance(info, dict)
    assert "cache_manager" not in info


def test_post_init_does_not_alias_shared_session_config_info() -> None:
    """Two configs sharing a session_config must not clobber each other's cache_manager."""
    from advanced_alchemy.cache import CacheConfig, CacheManager
    from advanced_alchemy.config.sync import SyncSessionConfig

    shared = SyncSessionConfig(info={"user_key": "preserved"})
    mgr_a = CacheManager(CacheConfig(backend="dogpile.cache.memory", key_prefix="a:"))
    mgr_b = CacheManager(CacheConfig(backend="dogpile.cache.memory", key_prefix="b:"))

    cfg_a = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        session_config=shared,
        cache_manager=mgr_a,
    )
    cfg_b = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        session_config=shared,
        cache_manager=mgr_b,
    )

    info_a = cfg_a.session_config.info
    info_b = cfg_b.session_config.info
    assert isinstance(info_a, dict)
    assert isinstance(info_b, dict)
    assert info_a["cache_manager"] is mgr_a
    assert info_b["cache_manager"] is mgr_b
    assert info_a["user_key"] == "preserved"
    assert info_b["user_key"] == "preserved"


def test_hash_distinguishes_configs_by_cache_manager() -> None:
    """Configs identical except for cache_manager hash differently."""
    from advanced_alchemy.cache import CacheConfig, CacheManager

    mgr_a = CacheManager(CacheConfig(backend="dogpile.cache.memory", key_prefix="a:"))
    mgr_b = CacheManager(CacheConfig(backend="dogpile.cache.memory", key_prefix="b:"))

    cfg_a = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", cache_manager=mgr_a)
    cfg_b = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", cache_manager=mgr_b)
    cfg_none = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")

    assert hash(cfg_a) != hash(cfg_b)
    assert hash(cfg_a) != hash(cfg_none)

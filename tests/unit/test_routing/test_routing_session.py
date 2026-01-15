"""Unit tests for routing sessions.

Tests the session classes that implement read/write routing via get_bind().
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import Delete, Engine, Insert, Update, select

from advanced_alchemy.config.routing import RoutingConfig
from advanced_alchemy.routing.context import (
    force_primary_var,
    reset_routing_context,
    stick_to_primary_var,
)
from advanced_alchemy.routing.selectors import EngineSelector, RoundRobinSelector
from advanced_alchemy.routing.session import RoutingSyncSession


@pytest.fixture
def mock_primary_engine() -> Engine:
    """Create a mock primary engine."""
    engine = MagicMock(name="primary_engine")
    engine.url = "postgresql://primary:5432/db"
    return engine


@pytest.fixture
def mock_replica_engines() -> list[Engine]:
    """Create mock replica engines."""
    engines: list[Engine] = []
    for i in range(2):
        engine: Engine = MagicMock(name=f"replica_engine_{i}")
        setattr(engine, "url", f"postgresql://replica{i}:5432/db")
        engines.append(engine)
    return engines


@pytest.fixture
def mock_replica_selector(mock_replica_engines: list[Engine]) -> RoundRobinSelector[Engine]:
    """Create a mock replica selector."""
    return RoundRobinSelector(mock_replica_engines)


@pytest.fixture
def routing_config() -> RoutingConfig:
    """Create a default routing config."""
    return RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica:5432/db"],
    )


@pytest.fixture
def routing_session(
    mock_primary_engine: Engine,
    mock_replica_selector: RoundRobinSelector[Engine],
    routing_config: RoutingConfig,
) -> RoutingSyncSession:
    """Create a routing session for testing."""
    reset_routing_context()

    selectors: dict[str, EngineSelector[Engine]] = {routing_config.read_group: mock_replica_selector}
    return RoutingSyncSession(
        default_engine=mock_primary_engine,
        selectors=selectors,
        routing_config=routing_config,
    )


def test_routing_session_initialization(
    mock_primary_engine: Engine,
    mock_replica_selector: RoundRobinSelector[Engine],
    routing_config: RoutingConfig,
) -> None:
    """Test RoutingSyncSession initialization."""
    selectors: dict[str, EngineSelector[Engine]] = {routing_config.read_group: mock_replica_selector}
    session = RoutingSyncSession(
        default_engine=mock_primary_engine,
        selectors=selectors,
        routing_config=routing_config,
    )

    assert session._default_engine is mock_primary_engine
    assert session._selectors[routing_config.read_group] is mock_replica_selector
    assert session._routing_config is routing_config


def test_get_bind_routes_select_to_replica(
    routing_session: RoutingSyncSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that SELECT queries route to replica."""
    stmt = select(1)

    engine = routing_session.get_bind(clause=stmt)

    assert engine in mock_replica_engines


def test_get_bind_routes_insert_to_primary(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that INSERT queries route to primary."""
    stmt = MagicMock(spec=Insert)
    stmt._execution_options = {}

    engine = routing_session.get_bind(clause=stmt)

    assert engine is mock_primary_engine


def test_get_bind_routes_update_to_primary(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that UPDATE queries route to primary."""
    stmt = MagicMock(spec=Update)
    stmt._execution_options = {}

    engine = routing_session.get_bind(clause=stmt)

    assert engine is mock_primary_engine


def test_get_bind_routes_delete_to_primary(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that DELETE queries route to primary."""
    stmt = MagicMock(spec=Delete)
    stmt._execution_options = {}

    engine = routing_session.get_bind(clause=stmt)

    assert engine is mock_primary_engine


def test_get_bind_sticky_after_write(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that reads stick to primary after a write."""
    insert_stmt = MagicMock(spec=Insert)
    insert_stmt._execution_options = {}
    routing_session.get_bind(clause=insert_stmt)

    select_stmt = select(1)
    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_respects_force_primary_context(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that force_primary context variable forces primary for reads."""
    force_primary_var.set(True)

    select_stmt = select(1)
    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_with_routing_disabled(
    mock_primary_engine: Engine,
    mock_replica_selector: RoundRobinSelector[Engine],
) -> None:
    """Test that all queries use primary when routing is disabled."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica:5432/db"],
        enabled=False,
    )

    selectors: dict[str, EngineSelector[Engine]] = {config.read_group: mock_replica_selector}
    session = RoutingSyncSession(
        default_engine=mock_primary_engine,
        selectors=selectors,
        routing_config=config,
    )

    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_when_flushing_uses_primary(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that queries during flush use primary."""
    routing_session._flushing = True

    select_stmt = select(1)
    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_for_update_uses_primary(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that SELECT FOR UPDATE uses primary."""
    select_stmt = select(1).with_for_update()

    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_for_update_nowait_uses_primary(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that SELECT FOR UPDATE NOWAIT uses primary."""
    select_stmt = select(1).with_for_update(nowait=True)

    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_for_update_skip_locked_uses_primary(
    routing_session: RoutingSyncSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that SELECT FOR UPDATE SKIP LOCKED uses primary."""
    select_stmt = select(1).with_for_update(skip_locked=True)

    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_no_replicas_falls_back_to_primary(
    mock_primary_engine: Engine,
) -> None:
    """Test that reads fall back to primary when no replicas are configured."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[],
    )

    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    selectors: dict[str, EngineSelector[Engine]] = {config.read_group: selector}

    session = RoutingSyncSession(
        default_engine=mock_primary_engine,
        selectors=selectors,
        routing_config=config,
    )

    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_round_robin_through_replicas(
    routing_session: RoutingSyncSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that reads cycle through replicas in round-robin fashion."""
    select_stmt = select(1)

    engine1 = routing_session.get_bind(clause=select_stmt)
    assert engine1 is mock_replica_engines[0]

    engine2 = routing_session.get_bind(clause=select_stmt)
    assert engine2 is mock_replica_engines[1]

    engine3 = routing_session.get_bind(clause=select_stmt)
    assert engine3 is mock_replica_engines[0]


def test_commit_resets_stickiness(
    routing_session: RoutingSyncSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that commit resets sticky-to-primary state."""
    insert_stmt = MagicMock(spec=Insert)
    insert_stmt._execution_options = {}
    routing_session.get_bind(clause=insert_stmt)

    assert stick_to_primary_var.get() is True

    routing_session.commit()

    assert stick_to_primary_var.get() is False

    select_stmt = select(1)
    engine = routing_session.get_bind(clause=select_stmt)
    assert engine in mock_replica_engines


def test_commit_no_reset_when_disabled(
    mock_primary_engine: Engine,
    mock_replica_selector: RoundRobinSelector[Engine],
) -> None:
    """Test that commit doesn't reset stickiness when reset_stickiness_on_commit is False."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica:5432/db"],
        reset_stickiness_on_commit=False,
    )

    selectors: dict[str, EngineSelector[Engine]] = {config.read_group: mock_replica_selector}
    session = RoutingSyncSession(
        default_engine=mock_primary_engine,
        selectors=selectors,
        routing_config=config,
    )

    insert_stmt = MagicMock(spec=Insert)
    insert_stmt._execution_options = {}
    session.get_bind(clause=insert_stmt)

    session.commit()

    assert stick_to_primary_var.get() is True

    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)
    assert engine is mock_primary_engine


def test_rollback_resets_stickiness(
    routing_session: RoutingSyncSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that rollback resets sticky-to-primary state."""
    insert_stmt = MagicMock(spec=Insert)
    insert_stmt._execution_options = {}
    routing_session.get_bind(clause=insert_stmt)

    assert stick_to_primary_var.get() is True

    routing_session.rollback()

    assert stick_to_primary_var.get() is False

    select_stmt = select(1)
    engine = routing_session.get_bind(clause=select_stmt)
    assert engine in mock_replica_engines


def test_sticky_disabled_writes_dont_set_flag(
    mock_primary_engine: Engine,
    mock_replica_selector: RoundRobinSelector[Engine],
    mock_replica_engines: list[Engine],
) -> None:
    """Test that writes don't set stickiness when sticky_after_write is False."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica:5432/db"],
        sticky_after_write=False,
    )

    selectors: dict[str, EngineSelector[Engine]] = {config.read_group: mock_replica_selector}
    session = RoutingSyncSession(
        default_engine=mock_primary_engine,
        selectors=selectors,
        routing_config=config,
    )

    insert_stmt = MagicMock(spec=Insert)
    insert_stmt._execution_options = {}
    session.get_bind(clause=insert_stmt)

    assert stick_to_primary_var.get() is False

    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)
    assert engine in mock_replica_engines


def test_get_bind_with_none_clause_uses_replica(
    routing_session: RoutingSyncSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that get_bind with None clause uses replica."""
    engine = routing_session.get_bind(clause=None)

    assert engine in mock_replica_engines


def test_get_bind_with_none_clause_and_no_replicas(
    mock_primary_engine: Engine,
) -> None:
    """Test that get_bind with None clause falls back to primary when no replicas."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[],
    )

    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    selectors: dict[str, EngineSelector[Engine]] = {config.read_group: selector}

    session = RoutingSyncSession(
        default_engine=mock_primary_engine,
        selectors=selectors,
        routing_config=config,
    )

    engine = session.get_bind(clause=None)

    assert engine is mock_primary_engine


def test_has_for_update_detects_for_update_clause() -> None:
    """Test that _has_for_update correctly detects FOR UPDATE."""
    config = RoutingConfig(primary_connection_string="postgresql://primary:5432/db")
    primary_engine: Engine = MagicMock()
    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    selectors: dict[str, EngineSelector[Engine]] = {config.read_group: selector}
    session = RoutingSyncSession(
        default_engine=primary_engine,
        selectors=selectors,
        routing_config=config,
    )

    select_with_for_update = select(1).with_for_update()

    assert session._has_for_update(select_with_for_update) is True

    regular_select = select(1)
    assert session._has_for_update(regular_select) is False

    assert session._has_for_update(None) is False

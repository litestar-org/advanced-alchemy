"""Unit tests for routing sessions.

Tests the session classes that implement read/write routing via get_bind().
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Delete, Insert, Update, select

from advanced_alchemy.config.routing import RoutingConfig
from advanced_alchemy.routing.context import (
    force_primary_var,
    reset_routing_context,
    stick_to_primary_var,
)
from advanced_alchemy.routing.selectors import RoundRobinSelector
from advanced_alchemy.routing.session import RoutingSession

if TYPE_CHECKING:
    from sqlalchemy import Engine


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
        engine.url = f"postgresql://replica{i}:5432/db"  # type: ignore[assignment, attr-defined]
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
) -> RoutingSession:
    """Create a routing session for testing."""
    # Reset context before each test
    reset_routing_context()

    return RoutingSession(
        primary_engine=mock_primary_engine,
        replica_selector=mock_replica_selector,
        routing_config=routing_config,
    )


def test_routing_session_initialization(
    mock_primary_engine: Engine,
    mock_replica_selector: RoundRobinSelector[Engine],
    routing_config: RoutingConfig,
) -> None:
    """Test RoutingSession initialization."""
    session = RoutingSession(
        primary_engine=mock_primary_engine,
        replica_selector=mock_replica_selector,
        routing_config=routing_config,
    )

    assert session._primary_engine is mock_primary_engine
    assert session._replica_selector is mock_replica_selector
    assert session._routing_config is routing_config


def test_get_bind_routes_select_to_replica(
    routing_session: RoutingSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that SELECT queries route to replica."""
    # Create a Select clause
    stmt = select(1)

    engine = routing_session.get_bind(clause=stmt)

    # Should use a replica engine
    assert engine in mock_replica_engines


def test_get_bind_routes_insert_to_primary(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that INSERT queries route to primary."""
    # Create mock Insert clause
    stmt = MagicMock(spec=Insert)

    engine = routing_session.get_bind(clause=stmt)

    assert engine is mock_primary_engine


def test_get_bind_routes_update_to_primary(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that UPDATE queries route to primary."""
    # Create mock Update clause
    stmt = MagicMock(spec=Update)

    engine = routing_session.get_bind(clause=stmt)

    assert engine is mock_primary_engine


def test_get_bind_routes_delete_to_primary(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that DELETE queries route to primary."""
    # Create mock Delete clause
    stmt = MagicMock(spec=Delete)

    engine = routing_session.get_bind(clause=stmt)

    assert engine is mock_primary_engine


def test_get_bind_sticky_after_write(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that reads stick to primary after a write."""
    # Perform a write operation
    insert_stmt = MagicMock(spec=Insert)
    routing_session.get_bind(clause=insert_stmt)

    # Now a read operation should also use primary (sticky)
    select_stmt = select(1)
    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_respects_force_primary_context(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that force_primary context variable forces primary for reads."""
    force_primary_var.set(True)

    # Even a SELECT should use primary
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

    session = RoutingSession(
        primary_engine=mock_primary_engine,
        replica_selector=mock_replica_selector,
        routing_config=config,
    )

    # SELECT should use primary (routing disabled)
    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_when_flushing_uses_primary(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that queries during flush use primary."""
    # Set the _flushing flag
    routing_session._flushing = True

    # Even a SELECT should use primary during flush
    select_stmt = select(1)
    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_for_update_uses_primary(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that SELECT FOR UPDATE uses primary."""
    # Create a Select with FOR UPDATE
    select_stmt = select(1).with_for_update()

    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_for_update_nowait_uses_primary(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that SELECT FOR UPDATE NOWAIT uses primary."""
    # Create a Select with FOR UPDATE NOWAIT
    select_stmt = select(1).with_for_update(nowait=True)

    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_for_update_skip_locked_uses_primary(
    routing_session: RoutingSession,
    mock_primary_engine: Engine,
) -> None:
    """Test that SELECT FOR UPDATE SKIP LOCKED uses primary."""
    # Create a Select with FOR UPDATE SKIP LOCKED
    select_stmt = select(1).with_for_update(skip_locked=True)

    engine = routing_session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_no_replicas_falls_back_to_primary(
    mock_primary_engine: Engine,
) -> None:
    """Test that reads fall back to primary when no replicas are configured."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[],  # No replicas
    )

    # Empty selector
    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    session = RoutingSession(
        primary_engine=mock_primary_engine,
        replica_selector=selector,
        routing_config=config,
    )

    # SELECT should fall back to primary
    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)

    assert engine is mock_primary_engine


def test_get_bind_round_robin_through_replicas(
    routing_session: RoutingSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that reads cycle through replicas in round-robin fashion."""
    select_stmt = select(1)

    # First read -> replica 0
    engine1 = routing_session.get_bind(clause=select_stmt)
    assert engine1 is mock_replica_engines[0]

    # Second read -> replica 1
    engine2 = routing_session.get_bind(clause=select_stmt)
    assert engine2 is mock_replica_engines[1]

    # Third read -> back to replica 0
    engine3 = routing_session.get_bind(clause=select_stmt)
    assert engine3 is mock_replica_engines[0]


def test_commit_resets_stickiness(
    routing_session: RoutingSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that commit resets sticky-to-primary state."""
    # Perform a write to set stickiness
    insert_stmt = MagicMock(spec=Insert)
    routing_session.get_bind(clause=insert_stmt)

    # Verify stickiness is set
    assert stick_to_primary_var.get() is True

    # Commit should reset stickiness
    routing_session.commit()

    # Now reads should use replica again
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

    session = RoutingSession(
        primary_engine=mock_primary_engine,
        replica_selector=mock_replica_selector,
        routing_config=config,
    )

    # Perform a write to set stickiness
    insert_stmt = MagicMock(spec=Insert)
    session.get_bind(clause=insert_stmt)

    # Commit
    session.commit()

    # Stickiness should NOT be reset
    assert stick_to_primary_var.get() is True

    # Reads should still use primary
    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)
    assert engine is mock_primary_engine


def test_rollback_resets_stickiness(
    routing_session: RoutingSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that rollback resets sticky-to-primary state."""
    # Perform a write to set stickiness
    insert_stmt = MagicMock(spec=Insert)
    routing_session.get_bind(clause=insert_stmt)

    # Verify stickiness is set
    assert stick_to_primary_var.get() is True

    # Rollback should reset stickiness
    routing_session.rollback()

    # Now reads should use replica again
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

    session = RoutingSession(
        primary_engine=mock_primary_engine,
        replica_selector=mock_replica_selector,
        routing_config=config,
    )

    # Perform a write
    insert_stmt = MagicMock(spec=Insert)
    session.get_bind(clause=insert_stmt)

    # Stickiness should NOT be set
    assert stick_to_primary_var.get() is False

    # Reads should use replica
    select_stmt = select(1)
    engine = session.get_bind(clause=select_stmt)
    assert engine in mock_replica_engines


def test_get_bind_with_none_clause_uses_replica(
    routing_session: RoutingSession,
    mock_replica_engines: list[Engine],
) -> None:
    """Test that get_bind with None clause uses replica."""
    engine = routing_session.get_bind(clause=None)

    # Should use replica when no specific clause
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

    session = RoutingSession(
        primary_engine=mock_primary_engine,
        replica_selector=selector,
        routing_config=config,
    )

    engine = session.get_bind(clause=None)

    assert engine is mock_primary_engine


def test_has_for_update_detects_for_update_clause() -> None:
    """Test that _has_for_update correctly detects FOR UPDATE."""
    config = RoutingConfig(primary_connection_string="postgresql://primary:5432/db")
    primary_engine: Engine = MagicMock()
    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    session = RoutingSession(
        primary_engine=primary_engine,
        replica_selector=selector,
        routing_config=config,
    )

    # Create a Select with FOR UPDATE
    select_with_for_update = select(1).with_for_update()

    # Should detect FOR UPDATE
    assert session._has_for_update(select_with_for_update) is True

    # Regular SELECT should not have FOR UPDATE
    regular_select = select(1)
    assert session._has_for_update(regular_select) is False

    # None should return False
    assert session._has_for_update(None) is False

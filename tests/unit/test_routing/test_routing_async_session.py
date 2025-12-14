"""Unit tests for RoutingAsyncSession.

Tests the async session wrapper for routing.
Note: Some tests are limited because RoutingAsyncSession initialization
requires special handling that doesn't work well with simple mocks.
Full integration tests are in test_routing_maker.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from advanced_alchemy.routing.selectors import RoundRobinSelector
from advanced_alchemy.routing.session import RoutingAsyncSession, RoutingSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def test_routing_async_session_class_attribute_sync_session_class() -> None:
    """Test that sync_session_class is set to RoutingSession."""
    assert RoutingAsyncSession.sync_session_class == RoutingSession


def test_sync_replica_selector_wrapper_has_replicas() -> None:
    """Test _SyncReplicaSelectorWrapper.has_replicas()."""
    from advanced_alchemy.routing.session import _SyncReplicaSelectorWrapper

    # Create mock async engines with sync_engine attribute
    async_engines: list[AsyncEngine] = []
    for i in range(2):
        async_engine: AsyncEngine = MagicMock()
        async_engine.sync_engine = MagicMock(name=f"sync_engine_{i}")  # type: ignore[attr-defined]
        async_engines.append(async_engine)

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector(async_engines)
    wrapper = _SyncReplicaSelectorWrapper(async_selector)

    assert wrapper.has_replicas() is True


def test_sync_replica_selector_wrapper_has_no_replicas() -> None:
    """Test _SyncReplicaSelectorWrapper.has_replicas() with empty selector."""
    from advanced_alchemy.routing.session import _SyncReplicaSelectorWrapper

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector([])
    wrapper = _SyncReplicaSelectorWrapper(async_selector)

    assert wrapper.has_replicas() is False


def test_sync_replica_selector_wrapper_next() -> None:
    """Test _SyncReplicaSelectorWrapper.next() returns sync engine."""
    from advanced_alchemy.routing.session import _SyncReplicaSelectorWrapper

    # Create mock async engines with sync_engine attribute
    async_engines: list[AsyncEngine] = []
    for i in range(2):
        async_engine: AsyncEngine = MagicMock()
        async_engine.sync_engine = MagicMock(name=f"sync_engine_{i}")  # type: ignore[attr-defined]
        async_engines.append(async_engine)

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector(async_engines)
    wrapper = _SyncReplicaSelectorWrapper(async_selector)

    # Get next should return sync_engine, not async_engine
    sync_engine = wrapper.next()

    # Should be the sync_engine from first async engine
    assert sync_engine is async_engines[0].sync_engine


def test_sync_replica_selector_wrapper_cycles_through_sync_engines() -> None:
    """Test _SyncReplicaSelectorWrapper cycles through sync engines."""
    from advanced_alchemy.routing.session import _SyncReplicaSelectorWrapper

    # Create mock async engines with sync_engine attribute
    async_engines: list[AsyncEngine] = []
    for i in range(2):
        async_engine: AsyncEngine = MagicMock()
        async_engine.sync_engine = MagicMock(name=f"sync_engine_{i}")  # type: ignore[attr-defined]
        async_engines.append(async_engine)

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector(async_engines)
    wrapper = _SyncReplicaSelectorWrapper(async_selector)

    # First call
    sync_engine_0 = wrapper.next()
    assert sync_engine_0 is async_engines[0].sync_engine

    # Second call
    sync_engine_1 = wrapper.next()
    assert sync_engine_1 is async_engines[1].sync_engine

    # Third call - should cycle back
    sync_engine_2 = wrapper.next()
    assert sync_engine_2 is async_engines[0].sync_engine

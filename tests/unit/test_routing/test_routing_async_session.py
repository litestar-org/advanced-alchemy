"""Unit tests for RoutingAsyncSession.

Tests the async session wrapper for routing.
Note: Some tests are limited because RoutingAsyncSession initialization
requires special handling that doesn't work well with simple mocks.
Full integration tests are in test_routing_maker.py.
"""

from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncEngine

from advanced_alchemy.routing.selectors import RoundRobinSelector
from advanced_alchemy.routing.session import RoutingAsyncSession, RoutingSyncSession


def test_routing_async_session_class_attribute_sync_session_class() -> None:
    """Test that sync_session_class is set to RoutingSyncSession."""
    assert RoutingAsyncSession.sync_session_class == RoutingSyncSession


def test_sync_replica_selector_wrapper_has_replicas() -> None:
    """Test _SyncReplicaSelectorWrapper.has_replicas()."""
    from advanced_alchemy.routing.session import _SyncEngineSelectorWrapper

    async_engines: list[AsyncEngine] = []
    for i in range(2):
        async_engine: AsyncEngine = MagicMock()
        setattr(async_engine, "sync_engine", MagicMock(name=f"sync_engine_{i}"))
        async_engines.append(async_engine)

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector(async_engines)
    wrapper = _SyncEngineSelectorWrapper(async_selector)

    assert wrapper.has_replicas() is True


def test_sync_replica_selector_wrapper_has_no_replicas() -> None:
    """Test _SyncReplicaSelectorWrapper.has_replicas() with empty selector."""
    from advanced_alchemy.routing.session import _SyncEngineSelectorWrapper

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector([])
    wrapper = _SyncEngineSelectorWrapper(async_selector)

    assert wrapper.has_replicas() is False


def test_sync_replica_selector_wrapper_next() -> None:
    """Test _SyncReplicaSelectorWrapper.next() returns sync engine."""
    from advanced_alchemy.routing.session import _SyncEngineSelectorWrapper

    async_engines: list[AsyncEngine] = []
    for i in range(2):
        async_engine: AsyncEngine = MagicMock()
        setattr(async_engine, "sync_engine", MagicMock(name=f"sync_engine_{i}"))
        async_engines.append(async_engine)

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector(async_engines)
    wrapper = _SyncEngineSelectorWrapper(async_selector)

    sync_engine = wrapper.next()

    assert sync_engine is async_engines[0].sync_engine


def test_sync_replica_selector_wrapper_cycles_through_sync_engines() -> None:
    """Test _SyncReplicaSelectorWrapper cycles through sync engines."""
    from advanced_alchemy.routing.session import _SyncEngineSelectorWrapper

    async_engines: list[AsyncEngine] = []
    for i in range(2):
        async_engine: AsyncEngine = MagicMock()
        setattr(async_engine, "sync_engine", MagicMock(name=f"sync_engine_{i}"))
        async_engines.append(async_engine)

    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector(async_engines)
    wrapper = _SyncEngineSelectorWrapper(async_selector)

    sync_engine_0 = wrapper.next()
    assert sync_engine_0 is async_engines[0].sync_engine

    sync_engine_1 = wrapper.next()
    assert sync_engine_1 is async_engines[1].sync_engine

    sync_engine_2 = wrapper.next()
    assert sync_engine_2 is async_engines[0].sync_engine

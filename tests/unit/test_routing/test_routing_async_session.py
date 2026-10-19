"""Unit tests for RoutingAsyncSession.

Tests the async session wrapper for routing.
Note: Some tests are limited because RoutingAsyncSession initialization
requires special handling that doesn't work well with simple mocks.
Full integration tests are in test_routing_maker.py.
"""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.config.routing import RoutingConfig
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.routing import RoutingAsyncSessionMaker
from advanced_alchemy.routing.selectors import RoundRobinSelector
from advanced_alchemy.routing.session import (
    RoutingAsyncSession,
    RoutingSyncSession,
    _SyncEngineSelectorWrapper,
)


class RoutingBindAsyncUser(UUIDAuditBase):
    """Minimal model for async routing bind regression tests."""

    __tablename__ = "routing_bind_async_users"

    name: Mapped[str] = mapped_column(String(length=100))  # pyright: ignore[reportUninitializedInstanceVariable]


class RoutingBindUserAsyncRepository(SQLAlchemyAsyncRepository[RoutingBindAsyncUser]):
    """Async repository for ``RoutingBindAsyncUser``."""

    model_type = RoutingBindAsyncUser


@pytest.fixture()
async def async_routing_session() -> AsyncIterator[RoutingAsyncSession]:
    """Create an async routing session backed by in-memory SQLite engines."""
    pytest.importorskip("aiosqlite")
    maker = RoutingAsyncSessionMaker(
        RoutingConfig(
            primary_connection_string="sqlite+aiosqlite://",
            read_replicas=["sqlite+aiosqlite://"],
        )
    )
    session = maker()
    try:
        yield session
    finally:
        await session.close()
        await maker.close_all()


def test_routing_async_session_class_attribute_sync_session_class() -> None:
    """Test that sync_session_class is set to RoutingSyncSession."""
    assert RoutingAsyncSession.sync_session_class == RoutingSyncSession


def test_sync_replica_selector_wrapper_has_replicas() -> None:
    """Test _SyncReplicaSelectorWrapper.has_replicas()."""
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
    async_selector: RoundRobinSelector[AsyncEngine] = RoundRobinSelector([])
    wrapper = _SyncEngineSelectorWrapper(async_selector)

    assert wrapper.has_replicas() is False


def test_sync_replica_selector_wrapper_next() -> None:
    """Test _SyncReplicaSelectorWrapper.next() returns sync engine."""
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


async def test_async_routing_session_exposes_none_bind(async_routing_session: RoutingAsyncSession) -> None:
    """A routing async session must expose ``bind`` as ``None``."""
    assert async_routing_session.bind is None


async def test_async_repository_constructs_with_routing_session(async_routing_session: RoutingAsyncSession) -> None:
    """Constructing an async repository on a routing session must resolve dialect via ``get_bind()``."""
    repo = RoutingBindUserAsyncRepository(session=async_routing_session)

    assert repo.session is async_routing_session
    assert repo._dialect.name == "sqlite"
    assert repo._dialect is async_routing_session.get_bind().dialect

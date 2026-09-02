"""
Regression tests: repositories constructed on top of routing sessions.

Issue: https://github.com/litestar-org/advanced-alchemy/issues/793

Description:

``RoutingAsyncSession`` did not expose a ``bind`` attribute, so the repository ``__init__`` line::

    self._dialect = (
        self.session.bind.dialect
        if self.session.bind is not None
        else self.session.get_bind().dialect
    )

raised ``AttributeError: ...Session object has no attribute 'bind'`` as soon as a
repository was created around a routing session (e.g. inside a FastAPI/Starlette
dependency). These tests reproduce that scenario and verify the fix: routing
sessions must expose ``bind`` as ``None`` so the repository falls back to
``get_bind()`` and resolves the dialect correctly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.config.routing import RoutingConfig
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.routing import (
    RoutingAsyncSession,
    RoutingAsyncSessionMaker,
    RoutingSyncSession,
    RoutingSyncSessionMaker,
)


class User(UUIDAuditBase):
    """Minimal model for routing bind regression tests (mirrors issue #793)."""

    __tablename__ = "routing_bind_users"

    name: Mapped[str] = mapped_column(String(length=100))  # pyright: ignore[reportUninitializedInstanceVariable]


class UserSyncRepository(SQLAlchemySyncRepository[User]):
    """Sync repository for ``User``."""

    model_type = User


class UserAsyncRepository(SQLAlchemyAsyncRepository[User]):
    """Async repository for ``User``."""

    model_type = User


@pytest.fixture()
def sync_routing_session() -> Iterator[RoutingSyncSession]:
    """Create a sync routing session backed by real (in-memory) SQLite engines."""
    maker = RoutingSyncSessionMaker(
        RoutingConfig(
            primary_connection_string="sqlite://",
            read_replicas=["sqlite://"],
        )
    )
    session = maker()
    try:
        yield session
    finally:
        session.close()
        maker.close_all()


@pytest.fixture()
async def async_routing_session() -> AsyncIterator[RoutingAsyncSession]:
    """Create an async routing session backed by real (in-memory) SQLite engines."""
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


def test_sync_routing_session_exposes_none_bind(sync_routing_session: RoutingSyncSession) -> None:
    """A sync routing session must expose ``bind`` as ``None`` (not be missing)."""
    assert sync_routing_session.bind is None


async def test_async_routing_session_exposes_none_bind(async_routing_session: RoutingAsyncSession) -> None:
    """A routing async session must expose ``bind`` as ``None`` (issue #793)."""
    assert async_routing_session.bind is None


def test_sync_repository_constructs_with_routing_session(sync_routing_session: RoutingSyncSession) -> None:
    """Constructing a sync repository on a routing session must not raise (issue #793)."""
    repo = UserSyncRepository(session=sync_routing_session)

    assert repo.session is sync_routing_session
    assert repo._dialect.name == "sqlite"


async def test_async_repository_constructs_with_routing_session(async_routing_session: RoutingAsyncSession) -> None:
    """Constructing an async repository on a routing session must not raise (issue #793)."""
    repo = UserAsyncRepository(session=async_routing_session)

    assert repo.session is async_routing_session
    assert repo._dialect.name == "sqlite"


def test_sync_repository_resolves_replica_dialect(sync_routing_session: RoutingSyncSession) -> None:
    """The resolved dialect must come from the routed engine, not a bound engine."""
    repo = UserSyncRepository(session=sync_routing_session)

    assert repo._dialect is sync_routing_session.get_bind().dialect


async def test_async_repository_resolves_replica_dialect(async_routing_session: RoutingAsyncSession) -> None:
    """The resolved dialect must come from the routed engine, not a bound engine."""
    repo = UserAsyncRepository(session=async_routing_session)

    assert repo._dialect is async_routing_session.get_bind().dialect

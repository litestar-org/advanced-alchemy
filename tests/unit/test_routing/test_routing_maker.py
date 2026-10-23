"""Unit tests for routing session makers.

Tests the factory classes that create routing sessions.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy._listeners import touch_updated_timestamp
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.routing import RoutingConfig, RoutingStrategy
from advanced_alchemy.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.routing.maker import (
    RoutingAsyncSessionMaker,
    RoutingSyncSessionMaker,
    dispose_session_maker_async,
    dispose_session_maker_sync,
)
from advanced_alchemy.routing.selectors import RandomSelector, RoundRobinSelector
from advanced_alchemy.routing.session import RoutingSyncSession
from advanced_alchemy.types import DateTimeUTC


@pytest.fixture
def routing_config() -> RoutingConfig:
    """Create a routing config with two replicas."""
    return RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[
            "postgresql://replica1:5432/db",
            "postgresql://replica2:5432/db",
        ],
    )


def test_sync_session_maker_initialization(routing_config: RoutingConfig) -> None:
    """Test RoutingSyncSessionMaker initialization."""

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        engine = MagicMock(spec=["dispose"])
        engine.url = url
        return engine

    maker = RoutingSyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_engine,
    )

    assert maker.primary_engine is not None
    assert len(maker.replica_engines) == 2
    assert maker.primary_engine.url == "postgresql://primary:5432/db"
    assert maker.replica_engines[0].url == "postgresql://replica1:5432/db"
    assert maker.replica_engines[1].url == "postgresql://replica2:5432/db"


def test_sync_session_maker_creates_round_robin_selector_by_default(
    routing_config: RoutingConfig,
) -> None:
    """Test that RoutingSyncSessionMaker creates RoundRobinSelector by default."""

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        engine = MagicMock(spec=["dispose"])
        engine.url = url
        return engine

    maker = RoutingSyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_engine,
    )

    session = maker()
    assert isinstance(session._selectors[routing_config.read_group], RoundRobinSelector)


def test_sync_session_maker_creates_random_selector(routing_config: RoutingConfig) -> None:
    """Test that RoutingSyncSessionMaker creates RandomSelector when configured."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
        routing_strategy=RoutingStrategy.RANDOM,
    )

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        engine = MagicMock(spec=["dispose"])
        engine.url = url
        return engine

    maker = RoutingSyncSessionMaker(
        routing_config=config,
        create_engine_callable=create_mock_engine,
    )

    session = maker()
    assert isinstance(session._selectors[config.read_group], RandomSelector)


def test_sync_session_maker_call_creates_session(routing_config: RoutingConfig) -> None:
    """Test that calling the maker creates a RoutingSyncSession."""

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        return MagicMock(spec=["dispose"])

    maker = RoutingSyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_engine,
    )

    session = maker()

    assert isinstance(session, RoutingSyncSession)
    assert session._routing_config is routing_config


def test_sync_session_maker_passes_engine_config() -> None:
    """Test that RoutingSyncSessionMaker passes engine config to create_engine."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
    )

    engine_config = {"pool_size": 10, "max_overflow": 20}

    mock_create_engine = MagicMock(return_value=MagicMock(spec=["dispose"]))

    RoutingSyncSessionMaker(
        routing_config=config,
        engine_config=engine_config,
        create_engine_callable=mock_create_engine,
    )

    assert mock_create_engine.call_count == 2
    for call in mock_create_engine.call_args_list:
        _, kwargs = call
        assert kwargs.get("pool_size") == 10
        assert kwargs.get("max_overflow") == 20


def test_sync_session_maker_passes_session_config(routing_config: RoutingConfig) -> None:
    """Test that RoutingSyncSessionMaker passes session config to session."""

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        return MagicMock(spec=["dispose"])

    session_config = {"expire_on_commit": False, "autoflush": False}

    maker = RoutingSyncSessionMaker(
        routing_config=routing_config,
        engine_config={},
        session_config=session_config,
        create_engine_callable=create_mock_engine,
    )

    session = maker()

    assert session.expire_on_commit is False
    assert session.autoflush is False


def test_sync_session_maker_close_all_disposes_engines(routing_config: RoutingConfig) -> None:
    """Test that close_all disposes all engines."""
    mock_engines = []

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        engine = MagicMock(spec=["dispose"])
        mock_engines.append(engine)
        return engine

    maker = RoutingSyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_engine,
    )

    maker.close_all()

    assert len(mock_engines) == 3
    for engine in mock_engines:
        engine.dispose.assert_called_once()


def test_sync_session_maker_handles_engine_creation_errors() -> None:
    """Test that RoutingSyncSessionMaker handles TypeError from unsupported engine options."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
    )

    call_count = 0

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        nonlocal call_count
        call_count += 1

        if "json_serializer" in kwargs:
            raise TypeError("json_serializer not supported")

        engine = MagicMock(spec=["dispose"])
        engine.url = url
        return engine

    engine_config = {"pool_size": 10, "json_serializer": lambda x: x}

    maker = RoutingSyncSessionMaker(
        routing_config=config,
        engine_config=engine_config,
        create_engine_callable=create_mock_engine,
    )

    assert maker.primary_engine is not None
    assert len(maker.replica_engines) == 1


def test_async_session_maker_initialization(routing_config: RoutingConfig) -> None:
    """Test RoutingAsyncSessionMaker initialization."""

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.url = url
        engine.sync_engine = MagicMock()
        return engine

    maker = RoutingAsyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_async_engine,
    )

    assert maker.primary_engine is not None
    assert len(maker.replica_engines) == 2
    assert maker.primary_engine.url == "postgresql://primary:5432/db"


def test_async_session_maker_creates_round_robin_selector_by_default(
    routing_config: RoutingConfig,
) -> None:
    """Test that RoutingAsyncSessionMaker creates RoundRobinSelector by default."""

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()
        return engine

    maker = RoutingAsyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_async_engine,
    )

    assert isinstance(maker._selectors[routing_config.read_group], RoundRobinSelector)


def test_async_session_maker_creates_random_selector(routing_config: RoutingConfig) -> None:
    """Test that RoutingAsyncSessionMaker creates RandomSelector when configured."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
        routing_strategy=RoutingStrategy.RANDOM,
    )

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()
        return engine

    maker = RoutingAsyncSessionMaker(
        routing_config=config,
        create_engine_callable=create_mock_async_engine,
    )

    assert isinstance(maker._selectors[config.read_group], RandomSelector)


def test_async_session_maker_call_creates_session(routing_config: RoutingConfig) -> None:
    """Test that calling the async maker would create a RoutingAsyncSession.

    Note: We can't fully test this with mocks because RoutingAsyncSession
    initialization requires special engine handling. This test is covered
    in integration tests instead.
    """

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()
        return engine

    maker = RoutingAsyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_async_engine,
    )

    assert maker.primary_engine is not None
    assert len(maker.replica_engines) == 2


def test_async_session_maker_passes_engine_config() -> None:
    """Test that RoutingAsyncSessionMaker passes engine config to create_async_engine."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
    )

    engine_config = {"pool_size": 10, "max_overflow": 20}

    mock_create_engine = MagicMock()
    mock_create_engine.return_value = MagicMock(spec=["dispose", "sync_engine"])
    mock_create_engine.return_value.sync_engine = MagicMock()

    RoutingAsyncSessionMaker(
        routing_config=config,
        engine_config=engine_config,
        create_engine_callable=mock_create_engine,
    )

    assert mock_create_engine.call_count == 2
    for call in mock_create_engine.call_args_list:
        _, kwargs = call
        assert kwargs.get("pool_size") == 10
        assert kwargs.get("max_overflow") == 20


@pytest.mark.asyncio
async def test_async_session_maker_close_all_disposes_engines(
    routing_config: RoutingConfig,
) -> None:
    """Test that close_all disposes all async engines."""
    import asyncio

    mock_engines = []

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()

        async def mock_dispose() -> None:
            pass

        engine.dispose = MagicMock(side_effect=lambda: asyncio.create_task(mock_dispose()))
        mock_engines.append(engine)
        return engine

    maker = RoutingAsyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_async_engine,
    )

    await maker.close_all()

    assert len(mock_engines) == 3
    for engine in mock_engines:
        engine.dispose.assert_called_once()


def test_async_session_maker_handles_engine_creation_errors() -> None:
    """Test that RoutingAsyncSessionMaker handles TypeError from unsupported options."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
    )

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        if "json_serializer" in kwargs:
            raise TypeError("json_serializer not supported")

        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()
        engine.url = url
        return engine

    engine_config = {"pool_size": 10, "json_serializer": lambda x: x}

    maker = RoutingAsyncSessionMaker(
        routing_config=config,
        engine_config=engine_config,
        create_engine_callable=create_mock_async_engine,
    )

    assert maker.primary_engine is not None
    assert len(maker.replica_engines) == 1


def test_sync_session_maker_no_replicas(routing_config: RoutingConfig) -> None:
    """Test RoutingSyncSessionMaker with no replicas."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[],
    )

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        return MagicMock(spec=["dispose"])

    maker = RoutingSyncSessionMaker(
        routing_config=config,
        create_engine_callable=create_mock_engine,
    )

    assert maker.primary_engine is not None
    assert len(maker.replica_engines) == 0


def test_async_session_maker_no_replicas(routing_config: RoutingConfig) -> None:
    """Test RoutingAsyncSessionMaker with no replicas."""
    config = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=[],
    )

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()
        return engine

    maker = RoutingAsyncSessionMaker(
        routing_config=config,
        create_engine_callable=create_mock_async_engine,
    )

    assert maker.primary_engine is not None
    assert len(maker.replica_engines) == 0


def test_sync_session_maker_removes_bind_from_session_config(
    routing_config: RoutingConfig,
) -> None:
    """Test that session maker removes 'bind' from session config."""

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        return MagicMock(spec=["dispose"])

    session_config = {"bind": MagicMock(), "expire_on_commit": False}

    maker = RoutingSyncSessionMaker(
        routing_config=routing_config,
        session_config=session_config,
        create_engine_callable=create_mock_engine,
    )

    session = maker()
    assert isinstance(session, RoutingSyncSession)


def test_async_session_maker_stores_session_config(
    routing_config: RoutingConfig,
) -> None:
    """Test that async session maker stores session config correctly."""

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()
        return engine

    session_config = {"expire_on_commit": False}

    maker = RoutingAsyncSessionMaker(
        routing_config=routing_config,
        session_config=session_config,
        create_engine_callable=create_mock_async_engine,
    )

    assert maker._session_config == session_config


def test_dispose_session_maker_sync_disposes_routing_sync_maker(
    routing_config: RoutingConfig,
) -> None:
    """dispose_session_maker_sync calls close_all on a sync routing maker."""
    mock_engines: list[Any] = []

    def create_mock_engine(url: str, **kwargs: Any) -> Engine:
        engine = MagicMock(spec=["dispose"])
        mock_engines.append(engine)
        return engine

    maker = RoutingSyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_engine,
    )

    dispose_session_maker_sync(maker)

    assert len(mock_engines) == 3
    for engine in mock_engines:
        engine.dispose.assert_called_once()


def test_dispose_session_maker_sync_noop_for_non_routing_maker() -> None:
    """dispose_session_maker_sync is a no-op for non-routing makers."""
    plain = MagicMock()
    dispose_session_maker_sync(plain)
    plain.close_all.assert_not_called()


def test_dispose_session_maker_sync_noop_for_none() -> None:
    """dispose_session_maker_sync handles a None session maker without raising."""
    dispose_session_maker_sync(None)


@pytest.mark.asyncio
async def test_dispose_session_maker_async_disposes_routing_async_maker(
    routing_config: RoutingConfig,
) -> None:
    """dispose_session_maker_async calls close_all on an async routing maker."""
    mock_engines: list[Any] = []

    def create_mock_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
        engine = MagicMock(spec=["dispose", "sync_engine"])
        engine.sync_engine = MagicMock()

        async def _dispose() -> None:
            return None

        engine.dispose.side_effect = _dispose
        mock_engines.append(engine)
        return engine

    maker = RoutingAsyncSessionMaker(
        routing_config=routing_config,
        create_engine_callable=create_mock_async_engine,
    )

    await dispose_session_maker_async(maker)

    assert len(mock_engines) == 3
    for engine in mock_engines:
        engine.dispose.assert_called_once()


@pytest.mark.asyncio
async def test_dispose_session_maker_async_noop_for_non_routing_maker() -> None:
    """dispose_session_maker_async is a no-op for non-routing makers."""
    plain = MagicMock()
    await dispose_session_maker_async(plain)
    plain.close_all.assert_not_called()


@pytest.mark.asyncio
async def test_dispose_session_maker_async_noop_for_none() -> None:
    """dispose_session_maker_async handles a None session maker without raising."""
    await dispose_session_maker_async(None)


def test_sync_config_with_routing_attaches_and_removes_listeners() -> None:
    """Verify SQLAlchemySyncConfig attaches before_flush listeners to RoutingSyncSessionMaker."""
    routing = RoutingConfig(
        primary_connection_string="sqlite:///:memory:",
        read_replicas=["sqlite:///:memory:"],
    )
    config = SQLAlchemySyncConfig(routing_config=routing)
    maker = config.create_session_maker()
    assert isinstance(maker, RoutingSyncSessionMaker)
    assert event.contains(maker.session_maker, "before_flush", touch_updated_timestamp)
    with pytest.deprecated_call():
        assert maker.sync_session_maker is maker.session_maker
    maker.close_all()


@pytest.mark.asyncio
async def test_async_config_with_routing_attaches_and_removes_listeners() -> None:
    """Verify SQLAlchemyAsyncConfig attaches before_flush listeners to RoutingAsyncSessionMaker."""
    routing = RoutingConfig(
        primary_connection_string="sqlite+aiosqlite:///:memory:",
        read_replicas=["sqlite+aiosqlite:///:memory:"],
    )
    config = SQLAlchemyAsyncConfig(routing_config=routing)
    maker = config.create_session_maker()
    assert isinstance(maker, RoutingAsyncSessionMaker)
    sync_maker = maker._session_config["sync_session_class"]
    assert event.contains(sync_maker, "before_flush", touch_updated_timestamp)
    await maker.close_all()


def test_routing_sync_session_maker_configure(routing_config: RoutingConfig) -> None:
    """Verify configure() updates session config and underlying sessionmaker."""
    maker = RoutingSyncSessionMaker(routing_config=routing_config)
    maker.configure(autoflush=False, expire_on_commit=False)
    assert maker._session_config["autoflush"] is False
    assert maker._session_config["expire_on_commit"] is False
    assert maker.session_maker.kw["autoflush"] is False
    assert maker.session_maker.kw["expire_on_commit"] is False
    maker.close_all()


def test_routing_async_session_maker_configure() -> None:
    """Verify configure() updates session config on RoutingAsyncSessionMaker."""
    routing = RoutingConfig(
        primary_connection_string="sqlite+aiosqlite:///:memory:",
        read_replicas=["sqlite+aiosqlite:///:memory:"],
    )
    maker = RoutingAsyncSessionMaker(routing_config=routing)
    maker.configure(expire_on_commit=False)
    assert maker._session_config["expire_on_commit"] is False


def test_sync_routing_session_executes_listeners(tmp_path: Path) -> None:
    """Verify touch_updated_timestamp executes during flush on routing sessions."""

    class Base(DeclarativeBase):
        pass

    class AuditModel(Base):
        __tablename__ = "audit_items_sync"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column()
        updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)

    db_file = tmp_path / "routing_sync_test.db"
    routing = RoutingConfig(
        primary_connection_string=f"sqlite:///{db_file}",
        read_replicas=[f"sqlite:///{db_file}"],
    )
    config = SQLAlchemySyncConfig(routing_config=routing)
    maker = config.create_session_maker()
    assert isinstance(maker, RoutingSyncSessionMaker)
    Base.metadata.create_all(maker.primary_engine)

    initial_time = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    with maker() as session:
        item = AuditModel(id=1, name="initial", updated_at=initial_time)
        session.add(item)
        session.commit()

    with maker() as session:
        item = session.get(AuditModel, 1)
        assert item is not None
        item.name = "updated"
        session.commit()
        assert item.updated_at is not None
        assert item.updated_at > initial_time

    maker.close_all()


@pytest.mark.asyncio
async def test_async_routing_session_executes_listeners(tmp_path: Path) -> None:
    """Verify touch_updated_timestamp executes during async flush on routing sessions."""

    class Base(DeclarativeBase):
        pass

    class AuditModel(Base):
        __tablename__ = "audit_items_async"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column()
        updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)

    db_file = tmp_path / "routing_async_test.db"
    routing = RoutingConfig(
        primary_connection_string=f"sqlite+aiosqlite:///{db_file}",
        read_replicas=[f"sqlite+aiosqlite:///{db_file}"],
    )
    config = SQLAlchemyAsyncConfig(routing_config=routing)
    maker = config.create_session_maker()
    assert isinstance(maker, RoutingAsyncSessionMaker)

    async with maker.primary_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    initial_time = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    async with maker() as session:
        item = AuditModel(id=1, name="initial", updated_at=initial_time)
        session.add(item)
        await session.commit()

    async with maker() as session:
        item = await session.get(AuditModel, 1)
        assert item is not None
        item.name = "updated"
        await session.commit()
        await session.refresh(item)
        assert item.updated_at is not None
        assert item.updated_at > initial_time

    await maker.close_all()

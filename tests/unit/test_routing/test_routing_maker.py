"""Unit tests for routing session makers.

Tests the factory classes that create routing sessions.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from advanced_alchemy.config.routing import RoutingConfig, RoutingStrategy
from advanced_alchemy.routing.maker import RoutingAsyncSessionMaker, RoutingSyncSessionMaker
from advanced_alchemy.routing.selectors import RandomSelector, RoundRobinSelector
from advanced_alchemy.routing.session import RoutingSyncSession


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

    assert isinstance(maker._replica_selector, RoundRobinSelector)


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

    assert isinstance(maker._replica_selector, RandomSelector)


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

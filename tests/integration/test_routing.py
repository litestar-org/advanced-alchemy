"""Integration tests for read/write routing functionality.

These tests verify that the routing module correctly routes read operations to
replicas and write operations to the primary database with real sessions.
"""

import asyncio
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, String, create_engine, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.config.routing import RoutingConfig, RoutingStrategy
from advanced_alchemy.routing import (
    RandomSelector,
    RoundRobinSelector,
    RoutingAsyncSession,
    RoutingAsyncSessionMaker,
    RoutingSyncSession,
    RoutingSyncSessionMaker,
    primary_context,
    replica_context,
    reset_routing_context,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("routing"),
]


class RoutingTestBase(DeclarativeBase):
    """Base class for routing test models."""

    pass


class User(RoutingTestBase):
    """Simple user model for routing tests."""

    __tablename__ = "routing_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100))


@pytest.fixture()
def routing_test_db_paths(tmp_path: Path) -> dict[str, Path]:
    """Create temporary database file paths for primary and replicas."""
    return {
        "primary": tmp_path / "primary.db",
        "replica1": tmp_path / "replica1.db",
        "replica2": tmp_path / "replica2.db",
    }


@pytest.fixture()
def sync_routing_engines(routing_test_db_paths: dict[str, Path]) -> Generator[dict[str, Engine], None, None]:
    """Create sync engines for primary and replicas."""
    engines = {
        "primary": create_engine(f"sqlite:///{routing_test_db_paths['primary']}"),
        "replica1": create_engine(f"sqlite:///{routing_test_db_paths['replica1']}"),
        "replica2": create_engine(f"sqlite:///{routing_test_db_paths['replica2']}"),
    }

    for engine in engines.values():
        RoutingTestBase.metadata.create_all(engine)

    yield engines

    for engine in engines.values():
        engine.dispose()


@pytest.fixture()
def async_routing_engines(
    routing_test_db_paths: dict[str, Path],
) -> Generator[dict[str, AsyncEngine], None, None]:
    """Create async engines for primary and replicas."""
    engines = {
        "primary": create_async_engine(f"sqlite+aiosqlite:///{routing_test_db_paths['primary']}"),
        "replica1": create_async_engine(f"sqlite+aiosqlite:///{routing_test_db_paths['replica1']}"),
        "replica2": create_async_engine(f"sqlite+aiosqlite:///{routing_test_db_paths['replica2']}"),
    }

    yield engines


@pytest.fixture()
def routing_config() -> RoutingConfig:
    """Create a basic routing configuration."""
    return RoutingConfig(
        primary_connection_string="sqlite:///primary.db",
        read_replicas=["sqlite:///replica1.db", "sqlite:///replica2.db"],
        routing_strategy=RoutingStrategy.ROUND_ROBIN,
        sticky_after_write=True,
        reset_stickiness_on_commit=True,
    )


@pytest.fixture()
def sync_session_maker(
    routing_test_db_paths: dict[str, Path],
) -> Generator[RoutingSyncSessionMaker, None, None]:
    """Create a sync routing session maker with real databases."""
    config = RoutingConfig(
        primary_connection_string=f"sqlite:///{routing_test_db_paths['primary']}",
        read_replicas=[
            f"sqlite:///{routing_test_db_paths['replica1']}",
            f"sqlite:///{routing_test_db_paths['replica2']}",
        ],
        routing_strategy=RoutingStrategy.ROUND_ROBIN,
        sticky_after_write=True,
    )

    maker = RoutingSyncSessionMaker(routing_config=config)

    RoutingTestBase.metadata.create_all(maker.primary_engine)
    for engine in maker.replica_engines:
        RoutingTestBase.metadata.create_all(engine)

    yield maker

    maker.close_all()


@pytest.fixture()
def async_session_maker(
    routing_test_db_paths: dict[str, Path],
) -> Generator[RoutingAsyncSessionMaker, None, None]:
    """Create an async routing session maker with real databases."""
    config = RoutingConfig(
        primary_connection_string=f"sqlite+aiosqlite:///{routing_test_db_paths['primary']}",
        read_replicas=[
            f"sqlite+aiosqlite:///{routing_test_db_paths['replica1']}",
            f"sqlite+aiosqlite:///{routing_test_db_paths['replica2']}",
        ],
        routing_strategy=RoutingStrategy.ROUND_ROBIN,
        sticky_after_write=True,
    )

    maker = RoutingAsyncSessionMaker(routing_config=config)

    yield maker


class TestRoutingSyncSession:
    """Integration tests for sync routing sessions."""

    def test_write_goes_to_primary(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that INSERT statements are routed to primary."""
        reset_routing_context()
        session = sync_session_maker()

        try:
            user = User(name="Test User")
            session.add(user)
            session.commit()

            with Session(sync_session_maker.primary_engine) as primary_session:
                result = primary_session.execute(select(User).where(User.name == "Test User")).scalar_one_or_none()
                assert result is not None
                assert result.name == "Test User"

        finally:
            session.close()
            reset_routing_context()

    def test_read_after_write_stickiness(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that reads stick to primary after a write."""
        reset_routing_context()
        session = sync_session_maker()

        try:
            with Session(sync_session_maker.primary_engine) as primary_session:
                primary_session.add(User(id="primary-user", name="Primary User"))
                primary_session.commit()

            session.add(User(name="Trigger Write"))
            session.flush()

            stmt = select(User).where(User.id == "primary-user")
            result = session.execute(stmt).scalar_one_or_none()
            assert result is not None
            assert result.name == "Primary User"

        finally:
            session.rollback()
            session.close()
            reset_routing_context()

    def test_commit_resets_stickiness(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that commit resets stickiness when configured."""
        reset_routing_context()
        session = sync_session_maker()

        try:
            user = User(name="Test User")
            session.add(user)
            session.commit()

            from advanced_alchemy.routing.context import stick_to_primary_var

            assert not stick_to_primary_var.get()

        finally:
            session.close()
            reset_routing_context()

    def test_rollback_resets_stickiness(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that rollback always resets stickiness."""
        reset_routing_context()
        session = sync_session_maker()

        try:
            session.add(User(name="Test User"))
            session.flush()

            from advanced_alchemy.routing.context import stick_to_primary_var

            assert stick_to_primary_var.get()

            session.rollback()

            assert not stick_to_primary_var.get()

        finally:
            session.close()
            reset_routing_context()

    def test_primary_context_forces_primary(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that primary_context() forces operations to primary."""
        reset_routing_context()
        session = sync_session_maker()

        try:
            with Session(sync_session_maker.primary_engine) as primary_session:
                primary_session.add(User(id="primary-only", name="Primary Only"))
                primary_session.commit()

            with primary_context():
                result = session.execute(select(User).where(User.id == "primary-only")).scalar_one_or_none()
                assert result is not None
                assert result.name == "Primary Only"

        finally:
            session.close()
            reset_routing_context()

    def test_replica_context_allows_replicas_after_write(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that replica_context() allows replicas even after writes."""
        reset_routing_context()
        session = sync_session_maker()

        try:
            session.add(User(name="Trigger Write"))
            session.flush()

            from advanced_alchemy.routing.context import stick_to_primary_var

            assert stick_to_primary_var.get()

            with replica_context():
                from advanced_alchemy.routing.context import force_primary_var

                assert not force_primary_var.get()

        finally:
            session.rollback()
            session.close()
            reset_routing_context()


class TestRoutingAsyncSession:
    """Integration tests for async routing sessions."""

    @pytest.mark.asyncio
    async def test_async_write_goes_to_primary(self, async_session_maker: RoutingAsyncSessionMaker) -> None:
        """Test that async INSERT statements are routed to primary."""
        reset_routing_context()

        async with async_session_maker.primary_engine.begin() as conn:
            await conn.run_sync(RoutingTestBase.metadata.create_all)
        for replica_engine in async_session_maker.replica_engines:
            async with replica_engine.begin() as conn:
                await conn.run_sync(RoutingTestBase.metadata.create_all)

        session = async_session_maker()

        try:
            user = User(name="Async Test User")
            session.add(user)
            await session.commit()

            async with AsyncSession(async_session_maker.primary_engine) as primary_session:
                result = await primary_session.execute(select(User).where(User.name == "Async Test User"))
                user_result = result.scalar_one_or_none()
                assert user_result is not None
                assert user_result.name == "Async Test User"

        finally:
            await session.close()
            reset_routing_context()

        await async_session_maker.close_all()

    @pytest.mark.asyncio
    async def test_async_primary_context(self, async_session_maker: RoutingAsyncSessionMaker) -> None:
        """Test that primary_context() works with async sessions."""
        reset_routing_context()

        async with async_session_maker.primary_engine.begin() as conn:
            await conn.run_sync(RoutingTestBase.metadata.create_all)

        async with AsyncSession(async_session_maker.primary_engine) as primary_session:
            primary_session.add(User(id="async-primary", name="Async Primary"))
            await primary_session.commit()

        session = async_session_maker()

        try:
            with primary_context():
                result = await session.execute(select(User).where(User.id == "async-primary"))
                user = result.scalar_one_or_none()
                assert user is not None
                assert user.name == "Async Primary"

        finally:
            await session.close()
            reset_routing_context()

        await async_session_maker.close_all()

    @pytest.mark.asyncio
    async def test_async_commit_resets_stickiness(self, async_session_maker: RoutingAsyncSessionMaker) -> None:
        """Test that async commit resets stickiness."""
        reset_routing_context()

        async with async_session_maker.primary_engine.begin() as conn:
            await conn.run_sync(RoutingTestBase.metadata.create_all)

        session = async_session_maker()

        try:
            from advanced_alchemy.routing.context import stick_to_primary_var

            session.add(User(name="Commit Test User"))
            await session.flush()

            assert stick_to_primary_var.get()

            await session.commit()

            assert not stick_to_primary_var.get()

        finally:
            await session.close()
            reset_routing_context()

        await async_session_maker.close_all()


class TestRoutingSyncSessionMaker:
    """Integration tests for sync session maker."""

    def test_creates_sessions_with_routing(self, routing_test_db_paths: dict[str, Path]) -> None:
        """Test that session maker creates properly configured routing sessions."""
        config = RoutingConfig(
            primary_connection_string=f"sqlite:///{routing_test_db_paths['primary']}",
            read_replicas=[f"sqlite:///{routing_test_db_paths['replica1']}"],
        )

        maker = RoutingSyncSessionMaker(routing_config=config)

        try:
            session = maker()
            assert isinstance(session, RoutingSyncSession)
            assert session._primary_engine is maker.primary_engine
        finally:
            maker.close_all()

    def test_round_robin_selector(self, routing_test_db_paths: dict[str, Path]) -> None:
        """Test that round-robin strategy is applied."""
        config = RoutingConfig(
            primary_connection_string=f"sqlite:///{routing_test_db_paths['primary']}",
            read_replicas=[
                f"sqlite:///{routing_test_db_paths['replica1']}",
                f"sqlite:///{routing_test_db_paths['replica2']}",
            ],
            routing_strategy=RoutingStrategy.ROUND_ROBIN,
        )

        maker = RoutingSyncSessionMaker(routing_config=config)

        try:
            assert maker._replica_selector is not None
            selector = maker._replica_selector
            assert isinstance(selector, RoundRobinSelector)

            first = selector.next()
            second = selector.next()
            third = selector.next()

            assert first == third
            assert first != second

        finally:
            maker.close_all()

    def test_random_selector(self, routing_test_db_paths: dict[str, Path]) -> None:
        """Test that random strategy is applied."""
        config = RoutingConfig(
            primary_connection_string=f"sqlite:///{routing_test_db_paths['primary']}",
            read_replicas=[
                f"sqlite:///{routing_test_db_paths['replica1']}",
                f"sqlite:///{routing_test_db_paths['replica2']}",
            ],
            routing_strategy=RoutingStrategy.RANDOM,
        )

        maker = RoutingSyncSessionMaker(routing_config=config)

        try:
            assert isinstance(maker._replica_selector, RandomSelector)
        finally:
            maker.close_all()


class TestRoutingAsyncSessionMaker:
    """Integration tests for async session maker."""

    @pytest.mark.asyncio
    async def test_creates_async_sessions_with_routing(self, routing_test_db_paths: dict[str, Path]) -> None:
        """Test that async session maker creates properly configured sessions."""
        config = RoutingConfig(
            primary_connection_string=f"sqlite+aiosqlite:///{routing_test_db_paths['primary']}",
            read_replicas=[f"sqlite+aiosqlite:///{routing_test_db_paths['replica1']}"],
        )

        maker = RoutingAsyncSessionMaker(routing_config=config)

        try:
            session = maker()
            assert isinstance(session, RoutingAsyncSession)
            assert session.primary_engine is maker.primary_engine
        finally:
            await maker.close_all()


class TestContextIsolation:
    """Tests for context variable isolation between concurrent requests."""

    def test_sync_context_isolation(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that context variables are isolated per execution context."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        results: dict[str, bool] = {}
        barrier = Barrier(2)

        def task1() -> None:
            reset_routing_context()
            session = sync_session_maker()
            try:
                session.add(User(name="Task 1"))
                session.flush()

                from advanced_alchemy.routing.context import stick_to_primary_var

                barrier.wait()
                results["task1_sticky"] = stick_to_primary_var.get()
            finally:
                session.rollback()
                session.close()
                reset_routing_context()

        def task2() -> None:
            reset_routing_context()
            session = sync_session_maker()
            try:
                barrier.wait()
                from advanced_alchemy.routing.context import stick_to_primary_var

                results["task2_sticky"] = stick_to_primary_var.get()
            finally:
                session.close()
                reset_routing_context()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(task1)
            f2 = executor.submit(task2)
            f1.result()
            f2.result()

        assert results["task1_sticky"] is True
        assert results["task2_sticky"] is False

    @pytest.mark.asyncio
    async def test_async_context_isolation(self, async_session_maker: RoutingAsyncSessionMaker) -> None:
        """Test that async context variables are isolated per task."""
        async with async_session_maker.primary_engine.begin() as conn:
            await conn.run_sync(RoutingTestBase.metadata.create_all)

        results: dict[str, bool] = {}
        event = asyncio.Event()

        async def task1() -> None:
            reset_routing_context()
            session = async_session_maker()
            try:
                session.add(User(name="Async Task 1"))
                await session.flush()

                from advanced_alchemy.routing.context import stick_to_primary_var

                event.set()
                await asyncio.sleep(0.1)
                results["task1_sticky"] = stick_to_primary_var.get()
            finally:
                await session.rollback()
                await session.close()
                reset_routing_context()

        async def task2() -> None:
            reset_routing_context()
            session = async_session_maker()
            try:
                await event.wait()

                from advanced_alchemy.routing.context import stick_to_primary_var

                results["task2_sticky"] = stick_to_primary_var.get()
            finally:
                await session.close()
                reset_routing_context()

        await asyncio.gather(task1(), task2())

        assert results["task1_sticky"] is True
        assert results["task2_sticky"] is False

        await async_session_maker.close_all()


class TestEdgeCases:
    """Edge case tests for routing functionality."""

    def test_no_replicas_routes_to_primary(self, routing_test_db_paths: dict[str, Path]) -> None:
        """Test that without replicas, all operations go to primary."""
        config = RoutingConfig(
            primary_connection_string=f"sqlite:///{routing_test_db_paths['primary']}",
            read_replicas=[],
        )

        maker = RoutingSyncSessionMaker(routing_config=config)
        RoutingTestBase.metadata.create_all(maker.primary_engine)

        try:
            reset_routing_context()
            session = maker()

            with Session(maker.primary_engine) as direct_session:
                direct_session.add(User(id="no-replica-test", name="No Replica User"))
                direct_session.commit()

            result = session.execute(select(User).where(User.id == "no-replica-test")).scalar_one_or_none()
            assert result is not None
            assert result.name == "No Replica User"

        finally:
            session.close()
            maker.close_all()
            reset_routing_context()

    def test_routing_disabled(self, routing_test_db_paths: dict[str, Path]) -> None:
        """Test that disabled routing sends all operations to primary."""
        config = RoutingConfig(
            primary_connection_string=f"sqlite:///{routing_test_db_paths['primary']}",
            read_replicas=[f"sqlite:///{routing_test_db_paths['replica1']}"],
            enabled=False,
        )

        maker = RoutingSyncSessionMaker(routing_config=config)
        RoutingTestBase.metadata.create_all(maker.primary_engine)

        try:
            reset_routing_context()
            session = maker()

            with Session(maker.primary_engine) as direct_session:
                direct_session.add(User(id="disabled-test", name="Disabled Routing User"))
                direct_session.commit()

            result = session.execute(select(User).where(User.id == "disabled-test")).scalar_one_or_none()
            assert result is not None

        finally:
            session.close()
            maker.close_all()
            reset_routing_context()

    def test_for_update_routes_to_primary(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that FOR UPDATE queries route to primary."""
        reset_routing_context()

        with Session(sync_session_maker.primary_engine) as direct_session:
            direct_session.add(User(id="for-update-test", name="For Update User"))
            direct_session.commit()

        session = sync_session_maker()

        try:
            stmt = select(User).where(User.id == "for-update-test").with_for_update()
            result = session.execute(stmt).scalar_one_or_none()
            assert result is not None
            assert result.name == "For Update User"

        finally:
            session.close()
            reset_routing_context()


class TestNestedContexts:
    """Tests for nested context manager behavior."""

    def test_nested_primary_contexts(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that nested primary_context managers work correctly."""
        reset_routing_context()

        with primary_context():
            from advanced_alchemy.routing.context import force_primary_var

            assert force_primary_var.get()

            with primary_context():
                assert force_primary_var.get()

            assert force_primary_var.get()

        assert not force_primary_var.get()
        reset_routing_context()

    def test_nested_replica_contexts(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test that nested replica_context managers work correctly."""
        reset_routing_context()
        session = sync_session_maker()

        try:
            session.add(User(name="Sticky User"))
            session.flush()

            from advanced_alchemy.routing.context import (
                force_primary_var,
                stick_to_primary_var,
            )

            assert stick_to_primary_var.get()

            with replica_context():
                assert not force_primary_var.get()

                with replica_context():
                    assert not force_primary_var.get()

                assert not force_primary_var.get()

        finally:
            session.rollback()
            session.close()
            reset_routing_context()

    def test_mixed_contexts(self, sync_session_maker: RoutingSyncSessionMaker) -> None:
        """Test mixing primary_context and replica_context."""
        reset_routing_context()

        from advanced_alchemy.routing.context import force_primary_var

        with primary_context():
            assert force_primary_var.get()

            with replica_context():
                assert not force_primary_var.get()

            assert force_primary_var.get()

        assert not force_primary_var.get()
        reset_routing_context()

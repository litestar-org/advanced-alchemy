"""Session maker factories for read/write routing.

This module provides session maker classes that create routing-aware sessions
with properly configured primary and replica engines.
"""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from advanced_alchemy.config.routing import RoutingConfig, RoutingStrategy
from advanced_alchemy.routing.selectors import RandomSelector, ReplicaSelector, RoundRobinSelector
from advanced_alchemy.routing.session import RoutingAsyncSession, RoutingSession

__all__ = (
    "RoutingAsyncSessionMaker",
    "RoutingSyncSessionMaker",
)


class RoutingSyncSessionMaker:
    """Factory for creating sync routing sessions.

    This class creates :class:`RoutingSession` instances with properly
    configured primary and replica engines.

    Example:
        Creating a routing session maker::

            maker = RoutingSyncSessionMaker(
                routing_config=RoutingConfig(
                    primary_connection_string="postgresql://...",
                    read_replicas=[
                        "postgresql://replica1/...",
                        "postgresql://replica2/...",
                    ],
                ),
                engine_config={"pool_size": 10},
            )

            # Create a session
            session = maker()
    """

    __slots__ = (
        "_engine_config",
        "_primary_engine",
        "_replica_engines",
        "_replica_selector",
        "_routing_config",
        "_session_config",
    )

    def __init__(
        self,
        routing_config: RoutingConfig,
        engine_config: dict[str, Any] | None = None,
        session_config: dict[str, Any] | None = None,
        create_engine_callable: Callable[[str], Engine] = create_engine,
    ) -> None:
        """Initialize the session maker.

        Args:
            routing_config: Configuration for read/write routing.
            engine_config: Configuration options for engine creation.
            session_config: Configuration options for session creation.
            create_engine_callable: Callable to create engines (for testing).
        """
        self._routing_config = routing_config
        self._engine_config = engine_config or {}
        self._session_config = session_config or {}

        # Create primary engine
        self._primary_engine = self._create_engine(
            routing_config.primary_connection_string,
            create_engine_callable,
        )

        # Create replica engines
        self._replica_engines: list[Engine] = []
        for connection_string in routing_config.get_replica_connection_strings():
            engine = self._create_engine(connection_string, create_engine_callable)
            self._replica_engines.append(engine)

        # Create replica selector
        self._replica_selector = self._create_selector(
            self._replica_engines,
            routing_config.routing_strategy,
        )

    def _create_engine(
        self,
        connection_string: str,
        create_engine_callable: Callable[[str], Engine],
    ) -> Engine:
        """Create an engine with the configured options.

        Args:
            connection_string: Database connection string.
            create_engine_callable: Callable to create the engine.

        Returns:
            The created engine.
        """
        try:
            return create_engine_callable(connection_string, **self._engine_config)
        except TypeError:
            # Some dialects don't support all engine options
            config = self._engine_config.copy()
            config.pop("json_deserializer", None)
            config.pop("json_serializer", None)
            return create_engine_callable(connection_string, **config)

    def _create_selector(
        self,
        engines: list[Engine],
        strategy: RoutingStrategy,
    ) -> ReplicaSelector[Engine]:
        """Create a replica selector for the given strategy.

        Args:
            engines: List of replica engines.
            strategy: The routing strategy to use.

        Returns:
            The appropriate selector instance.
        """
        if strategy == RoutingStrategy.RANDOM:
            return RandomSelector(engines)
        return RoundRobinSelector(engines)

    def __call__(self) -> RoutingSession:
        """Create a new routing session.

        Returns:
            A new :class:`RoutingSession` instance.
        """
        session_config = self._session_config.copy()
        # Remove bind from session config - routing handles this
        session_config.pop("bind", None)
        return RoutingSession(
            primary_engine=self._primary_engine,
            replica_selector=self._replica_selector,
            routing_config=self._routing_config,
            **session_config,
        )

    @property
    def primary_engine(self) -> Engine:
        """Get the primary engine.

        Returns:
            The primary database engine.
        """
        return self._primary_engine

    @property
    def replica_engines(self) -> list[Engine]:
        """Get the replica engines.

        Returns:
            List of replica database engines.
        """
        return self._replica_engines

    def close_all(self) -> None:
        """Close all engines and release connections.

        Call this when shutting down to properly release database connections.
        """
        self._primary_engine.dispose()
        for engine in self._replica_engines:
            engine.dispose()


class RoutingAsyncSessionMaker:
    """Factory for creating async routing sessions.

    This class creates :class:`RoutingAsyncSession` instances with properly
    configured primary and replica async engines.

    Example:
        Creating an async routing session maker::

            maker = RoutingAsyncSessionMaker(
                routing_config=RoutingConfig(
                    primary_connection_string="postgresql+asyncpg://...",
                    read_replicas=["postgresql+asyncpg://replica1/..."],
                ),
                engine_config={"pool_size": 10},
            )

            # Create a session
            async with maker() as session:
                result = await session.execute(select(User))
    """

    __slots__ = (
        "_engine_config",
        "_primary_engine",
        "_replica_engines",
        "_replica_selector",
        "_routing_config",
        "_session_config",
    )

    def __init__(
        self,
        routing_config: RoutingConfig,
        engine_config: dict[str, Any] | None = None,
        session_config: dict[str, Any] | None = None,
        create_engine_callable: Callable[[str], AsyncEngine] = create_async_engine,
    ) -> None:
        """Initialize the async session maker.

        Args:
            routing_config: Configuration for read/write routing.
            engine_config: Configuration options for engine creation.
            session_config: Configuration options for session creation.
            create_engine_callable: Callable to create async engines (for testing).
        """
        self._routing_config = routing_config
        self._engine_config = engine_config or {}
        self._session_config = session_config or {}

        # Create primary async engine
        self._primary_engine = self._create_engine(
            routing_config.primary_connection_string,
            create_engine_callable,
        )

        # Create replica async engines
        self._replica_engines: list[AsyncEngine] = []
        for connection_string in routing_config.get_replica_connection_strings():
            engine = self._create_engine(connection_string, create_engine_callable)
            self._replica_engines.append(engine)

        # Create replica selector
        self._replica_selector = self._create_selector(
            self._replica_engines,
            routing_config.routing_strategy,
        )

    def _create_engine(
        self,
        connection_string: str,
        create_engine_callable: Callable[[str], AsyncEngine],
    ) -> AsyncEngine:
        """Create an async engine with the configured options.

        Args:
            connection_string: Database connection string.
            create_engine_callable: Callable to create the engine.

        Returns:
            The created async engine.
        """
        try:
            return create_engine_callable(connection_string, **self._engine_config)
        except TypeError:
            # Some dialects don't support all engine options
            config = self._engine_config.copy()
            config.pop("json_deserializer", None)
            config.pop("json_serializer", None)
            return create_engine_callable(connection_string, **config)

    def _create_selector(
        self,
        engines: list[AsyncEngine],
        strategy: RoutingStrategy,
    ) -> ReplicaSelector[AsyncEngine]:
        """Create a replica selector for the given strategy.

        Args:
            engines: List of replica async engines.
            strategy: The routing strategy to use.

        Returns:
            The appropriate selector instance.
        """
        if strategy == RoutingStrategy.RANDOM:
            return RandomSelector(engines)
        return RoundRobinSelector(engines)

    def __call__(self) -> RoutingAsyncSession:
        """Create a new async routing session.

        Returns:
            A new :class:`RoutingAsyncSession` instance.
        """
        session_config = self._session_config.copy()
        # Remove bind from session config - routing handles this
        session_config.pop("bind", None)
        return RoutingAsyncSession(
            primary_engine=self._primary_engine,
            replica_selector=self._replica_selector,
            routing_config=self._routing_config,
            **session_config,
        )

    @property
    def primary_engine(self) -> AsyncEngine:
        """Get the primary async engine.

        Returns:
            The primary database async engine.
        """
        return self._primary_engine

    @property
    def replica_engines(self) -> list[AsyncEngine]:
        """Get the replica async engines.

        Returns:
            List of replica database async engines.
        """
        return self._replica_engines

    async def close_all(self) -> None:
        """Close all engines and release connections.

        Call this when shutting down to properly release database connections.
        """
        await self._primary_engine.dispose()
        for engine in self._replica_engines:
            await engine.dispose()

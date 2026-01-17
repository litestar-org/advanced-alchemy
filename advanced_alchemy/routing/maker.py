"""Session maker factories for read/write routing.

This module provides session maker classes that create routing-aware sessions
with properly configured primary and replica engines.
"""

from typing import Any, Callable, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from advanced_alchemy.config.routing import RoutingConfig, RoutingStrategy
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.routing.selectors import EngineSelector, RandomSelector, RoundRobinSelector
from advanced_alchemy.routing.session import RoutingAsyncSession, RoutingSyncSession

__all__ = (
    "RoutingAsyncSessionMaker",
    "RoutingSyncSessionMaker",
)


class RoutingSyncSessionMaker:
    """Factory for creating sync routing sessions.

    This class creates :class:`RoutingSyncSession` instances with properly
    configured engines and routing selectors.

    Example:
        Creating a routing session maker::

            maker = RoutingSyncSessionMaker(
                routing_config=RoutingConfig(
                    engines={
                        "writer": ["postgresql://primary"],
                        "reader": ["postgresql://replica1"],
                    }
                ),
                engine_config={"pool_size": 10},
            )

            session = maker()
    """

    __slots__ = (
        "_default_engine",
        "_engine_config",
        "_engines",
        "_routing_config",
        "_selectors",
        "_session_config",
    )

    def __init__(
        self,
        routing_config: RoutingConfig,
        engine_config: Optional[dict[str, Any]] = None,
        session_config: Optional[dict[str, Any]] = None,
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

        self._engines: dict[str, list[Engine]] = {}
        self._selectors: dict[str, EngineSelector[Engine]] = {}

        # Initialize engines and selectors for all groups
        for group in routing_config.engines:
            engines_for_group: list[Engine] = []
            for config in routing_config.get_engine_configs(group):
                engine = self._create_engine(config.connection_string, create_engine_callable)
                engines_for_group.append(engine)

            if engines_for_group:
                self._engines[group] = engines_for_group
                self._selectors[group] = self._create_selector(
                    engines_for_group,
                    routing_config.routing_strategy,
                )

        # Set default engine (required)
        default_group = routing_config.default_group
        if (
            default_group not in self._engines or not self._engines[default_group]
        ) and not routing_config.primary_connection_string:
            # Only raise if strict legacy check fails too?
            # Actually, post_init maps primary_connection_string to engines, so we just check engines.
            msg = (
                f"Default group '{default_group}' has no engines configured. "
                "Ensure 'engines' contains this group or 'primary_connection_string' is set."
            )
            raise ImproperConfigurationError(msg)

        self._default_engine = self._engines[default_group][0]

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
            config = self._engine_config.copy()
            config.pop("json_deserializer", None)
            config.pop("json_serializer", None)
            return create_engine_callable(connection_string, **config)

    def _create_selector(
        self,
        engines: list[Engine],
        strategy: RoutingStrategy,
    ) -> EngineSelector[Engine]:
        """Create an engine selector for the given strategy.

        Args:
            engines: List of engines.
            strategy: The routing strategy to use.

        Returns:
            The appropriate selector instance.
        """
        if strategy == RoutingStrategy.RANDOM:
            return RandomSelector(engines)
        return RoundRobinSelector(engines)

    def __call__(self) -> RoutingSyncSession:
        """Create a new routing session.

        Any ``bind`` passed in the session config is ignored because
        routing controls bind selection.

        Returns:
            A new :class:`RoutingSyncSession` instance.
        """
        session_config = self._session_config.copy()
        session_config.pop("bind", None)
        return RoutingSyncSession(
            routing_config=self._routing_config,
            selectors=self._selectors,
            default_engine=self._default_engine,
            **session_config,
        )

    @property
    def primary_engine(self) -> Engine:
        """Get the primary (default) engine.

        Returns:
            The primary database engine.
        """
        return self._default_engine

    @property
    def replica_engines(self) -> list[Engine]:
        """Get the replica engines (from read_group).

        Returns:
            List of replica database engines.
        """
        return self._engines.get(self._routing_config.read_group, [])

    def close_all(self) -> None:
        """Close all engines and release connections.

        Call this when shutting down to properly release database connections.
        """
        for engine_list in self._engines.values():
            for engine in engine_list:
                engine.dispose()


class RoutingAsyncSessionMaker:
    """Factory for creating async routing sessions.

    This class creates :class:`RoutingAsyncSession` instances with properly
    configured async engines and routing selectors.

    Example:
        Creating an async routing session maker::

            maker = RoutingAsyncSessionMaker(
                routing_config=RoutingConfig(
                    engines={
                        "writer": ["postgresql+asyncpg://primary"],
                        "reader": ["postgresql+asyncpg://replica1"],
                    }
                ),
                engine_config={"pool_size": 10},
            )

            async with maker() as session:
                result = await session.execute(select(User))
    """

    __slots__ = (
        "_default_engine",
        "_engine_config",
        "_engines",
        "_routing_config",
        "_selectors",
        "_session_config",
    )

    def __init__(
        self,
        routing_config: RoutingConfig,
        engine_config: Optional[dict[str, Any]] = None,
        session_config: Optional[dict[str, Any]] = None,
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

        self._engines: dict[str, list[AsyncEngine]] = {}
        self._selectors: dict[str, EngineSelector[AsyncEngine]] = {}

        # Initialize engines and selectors for all groups
        for group in routing_config.engines:
            engines_for_group: list[AsyncEngine] = []
            for config in routing_config.get_engine_configs(group):
                engine = self._create_engine(config.connection_string, create_engine_callable)
                engines_for_group.append(engine)

            if engines_for_group:
                self._engines[group] = engines_for_group
                self._selectors[group] = self._create_selector(
                    engines_for_group,
                    routing_config.routing_strategy,
                )

        # Set default engine (required)
        default_group = routing_config.default_group
        if default_group not in self._engines or not self._engines[default_group]:
            msg = (
                f"Default group '{default_group}' has no engines configured. "
                "Ensure 'engines' contains this group or 'primary_connection_string' is set."
            )
            raise ImproperConfigurationError(msg)

        self._default_engine = self._engines[default_group][0]

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
            config = self._engine_config.copy()
            config.pop("json_deserializer", None)
            config.pop("json_serializer", None)
            return create_engine_callable(connection_string, **config)

    def _create_selector(
        self,
        engines: list[AsyncEngine],
        strategy: RoutingStrategy,
    ) -> EngineSelector[AsyncEngine]:
        """Create an engine selector for the given strategy.

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

        Any ``bind`` passed in the session config is ignored because
        routing controls bind selection.

        Returns:
            A new :class:`RoutingAsyncSession` instance.
        """
        session_config = self._session_config.copy()
        session_config.pop("bind", None)
        return RoutingAsyncSession(
            routing_config=self._routing_config,
            selectors=self._selectors,
            default_engine=self._default_engine,
            **session_config,
        )

    @property
    def primary_engine(self) -> AsyncEngine:
        """Get the primary (default) async engine.

        Returns:
            The primary database async engine.
        """
        return self._default_engine

    @property
    def replica_engines(self) -> list[AsyncEngine]:
        """Get the replica async engines (from read_group).

        Returns:
            List of replica database async engines.
        """
        return self._engines.get(self._routing_config.read_group, [])

    async def close_all(self) -> None:
        """Close all engines and release connections.

        Call this when shutting down to properly release database connections.
        """
        for engine_list in self._engines.values():
            for engine in engine_list:
                await engine.dispose()

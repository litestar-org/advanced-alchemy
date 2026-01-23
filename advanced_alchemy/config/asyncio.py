from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional, Union, cast

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from advanced_alchemy._listeners import set_async_context
from advanced_alchemy.config.common import (
    GenericAlembicConfig,
    GenericSessionConfig,
    GenericSQLAlchemyConfig,
)
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.utils.dataclass import Empty

if TYPE_CHECKING:
    from typing import Callable

    from sqlalchemy.orm import Session

    from advanced_alchemy.config.routing import RoutingConfig
    from advanced_alchemy.utils.dataclass import EmptyType

__all__ = (
    "AlembicAsyncConfig",
    "AsyncSessionConfig",
    "SQLAlchemyAsyncConfig",
)


@dataclass
class AsyncSessionConfig(GenericSessionConfig[AsyncConnection, AsyncEngine, AsyncSession]):
    """SQLAlchemy async session config."""

    sync_session_class: "Optional[Union[type[Session], EmptyType]]" = Empty
    """A :class:`Session <sqlalchemy.orm.Session>` subclass or other callable which will be used to construct the
    :class:`Session <sqlalchemy.orm.Session>` which will be proxied. This parameter may be used to provide custom
    :class:`Session <sqlalchemy.orm.Session>` subclasses. Defaults to the
    :attr:`AsyncSession.sync_session_class <sqlalchemy.ext.asyncio.AsyncSession.sync_session_class>` class-level
    attribute."""


@dataclass
class AlembicAsyncConfig(GenericAlembicConfig):
    """Configuration for an Async Alembic's Config class.

    .. seealso::
        https://alembic.sqlalchemy.org/en/latest/api/config.html
    """


@dataclass
class SQLAlchemyAsyncConfig(GenericSQLAlchemyConfig[AsyncEngine, AsyncSession, async_sessionmaker[AsyncSession]]):
    """Async SQLAlchemy Configuration.

    Note:
        The alembic configuration options are documented in the Alembic documentation.

    Example:
        Basic async configuration::

            config = SQLAlchemyAsyncConfig(
                connection_string="postgresql+asyncpg://user:pass@localhost/db",
            )

        Configuration with read/write routing::

            from advanced_alchemy.config.routing import RoutingConfig

            config = SQLAlchemyAsyncConfig(
                routing_config=RoutingConfig(
                    primary_connection_string="postgresql+asyncpg://user:pass@primary/db",
                    read_replicas=[
                        "postgresql+asyncpg://user:pass@replica/db"
                    ],
                ),
            )
    """

    create_engine_callable: "Callable[[str], AsyncEngine]" = create_async_engine
    """Callable that creates an :class:`AsyncEngine <sqlalchemy.ext.asyncio.AsyncEngine>` instance or instance of its
    subclass.
    """
    session_config: AsyncSessionConfig = field(default_factory=AsyncSessionConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration options for the :class:`async_sessionmaker<sqlalchemy.ext.asyncio.async_sessionmaker>`."""
    session_maker_class: "type[async_sessionmaker[AsyncSession]]" = async_sessionmaker  # pyright: ignore[reportIncompatibleVariableOverride]
    """Sessionmaker class to use."""
    alembic_config: "AlembicAsyncConfig" = field(default_factory=AlembicAsyncConfig)
    """Configuration for the SQLAlchemy Alembic migrations.

    The configuration options are documented in the Alembic documentation.
    """
    routing_config: "Optional[RoutingConfig]" = None
    """Optional read/write routing configuration.

    When provided, enables automatic routing of read operations to replicas
    and write operations to the primary database.

    .. note::
        When using ``routing_config``, do not set ``connection_string``.
        The primary connection is specified in the routing config.
    """

    def __post_init__(self) -> None:
        # Validate routing config vs connection_string
        if self.routing_config is not None and self.connection_string is not None:
            msg = "Provide either 'connection_string' or 'routing_config', not both"
            raise ImproperConfigurationError(msg)
        # If routing_config is set, use its primary as the connection_string for compatibility
        if self.routing_config is not None:
            self.connection_string = self.routing_config.primary_connection_string
            if self.connection_string is None:
                # Try to get from default group engines
                configs = self.routing_config.get_engine_configs(self.routing_config.default_group)
                if configs:
                    self.connection_string = configs[0].connection_string

        super().__post_init__()

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        return super().__eq__(other)

    def create_session_maker(self) -> "Callable[[], AsyncSession]":
        """Get a session maker.

        If routing is configured, returns a routing-aware session maker.
        Otherwise, returns a standard session maker.

        Returns:
            A callable that creates session instances.
        """
        if self.session_maker:
            return self.session_maker

        from sqlalchemy import event

        from advanced_alchemy._listeners import (
            AsyncCacheListener,
            AsyncFileObjectListener,
            touch_updated_timestamp,
        )

        # Use routing session maker if routing is configured
        if self.routing_config is not None:
            from advanced_alchemy.routing import RoutingAsyncSessionMaker

            routing_maker: Callable[[], AsyncSession] = RoutingAsyncSessionMaker(
                routing_config=self.routing_config,
                engine_config=self.engine_config_dict,
                session_config=self.session_config_dict,
            )
            self.session_maker = routing_maker
        else:
            self.session_maker = super().create_session_maker()

        if isinstance(self.session_maker, async_sessionmaker):
            session_maker = cast(async_sessionmaker[AsyncSession], self.session_maker)
            if self.enable_file_object_listener:
                event.listen(session_maker, "before_flush", AsyncFileObjectListener.before_flush)
                event.listen(session_maker, "after_commit", AsyncFileObjectListener.after_commit)
                event.listen(session_maker, "after_rollback", AsyncFileObjectListener.after_rollback)
            if self.enable_touch_updated_timestamp_listener:
                event.listen(session_maker, "before_flush", touch_updated_timestamp)
            event.listen(session_maker, "after_commit", AsyncCacheListener.after_commit)
            event.listen(session_maker, "after_rollback", AsyncCacheListener.after_rollback)

        assert self.session_maker is not None
        return self.session_maker

    @asynccontextmanager
    async def get_session(
        self,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get a session from the session maker.

        Yields:
            AsyncGenerator[AsyncSession, None]: An async context manager that yields an AsyncSession.
        """
        session_maker = self.create_session_maker()
        set_async_context(True)
        async with session_maker() as session:
            yield session

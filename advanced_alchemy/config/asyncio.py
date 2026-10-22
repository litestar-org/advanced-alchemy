from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from advanced_alchemy.config.common import (
    GenericAlembicConfig,
    GenericSessionConfig,
    GenericSQLAlchemyConfig,
)
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.utils.dataclass import Empty

if TYPE_CHECKING:
    from collections.abc import Callable

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

    sync_session_class: "type[Session] | EmptyType | None" = Empty
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
    routing_config: "RoutingConfig | None" = None
    """Optional read/write routing configuration.

    When provided, enables automatic routing of read operations to replicas
    and write operations to the primary database.

    .. note::
        When using ``routing_config``, do not set ``connection_string``.
        The primary connection is specified in the routing config.
    """
    encryption_key: "str | bytes | Callable[[], str | bytes] | None" = None
    """Optional default encryption key registered for :class:`~advanced_alchemy.types.EncryptedString`,
    :class:`~advanced_alchemy.types.EncryptedText`, and :class:`~advanced_alchemy.types.TOTPSecret` columns
    that omit an explicit ``key`` argument.
    """

    def __post_init__(self) -> None:
        if self.encryption_key is not None:
            from advanced_alchemy.types.encrypted_string import set_default_encryption_key

            set_default_encryption_key(self.encryption_key)
        if self.routing_config is not None and self.connection_string is not None:
            msg = "Provide either 'connection_string' or 'routing_config', not both"
            raise ImproperConfigurationError(msg)
        if self.routing_config is not None:
            self.connection_string = self.routing_config.primary_connection_string
            if self.connection_string is None:
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
        from advanced_alchemy.routing import RoutingAsyncSessionMaker, RoutingSyncSession

        if self.routing_config is not None:
            routing_maker: Callable[[], AsyncSession] = RoutingAsyncSessionMaker(
                routing_config=self.routing_config,
                engine_config=self.engine_config_dict,
                session_config=self.session_config_dict,
            )
            self.session_maker = routing_maker
        else:
            self.session_maker = cast("Callable[[], AsyncSession]", super().create_session_maker())  # type: ignore[redundant-cast]

        if isinstance(self.session_maker, (async_sessionmaker, RoutingAsyncSessionMaker)):
            is_routing_maker = isinstance(
                self.session_maker,  # pyright: ignore[reportUnknownMemberType]
                RoutingAsyncSessionMaker,
            )
            sync_maker: sync_sessionmaker[Any] = (
                sync_sessionmaker(class_=RoutingSyncSession) if is_routing_maker else sync_sessionmaker()
            )
            if self.enable_file_object_listener:
                event.listen(sync_maker, "before_flush", AsyncFileObjectListener.before_flush)
                event.listen(sync_maker, "after_commit", AsyncFileObjectListener.after_commit)
                event.listen(sync_maker, "after_rollback", AsyncFileObjectListener.after_rollback)
            if self.enable_touch_updated_timestamp_listener:
                event.listen(sync_maker, "before_flush", touch_updated_timestamp)
            event.listen(sync_maker, "after_commit", AsyncCacheListener.after_commit)
            event.listen(sync_maker, "after_rollback", AsyncCacheListener.after_rollback)
            if isinstance(self.session_maker, RoutingAsyncSessionMaker):  # pyright: ignore[reportUnknownMemberType]
                self.session_maker.configure(sync_session_class=sync_maker)
            else:
                session_maker = cast(
                    "async_sessionmaker[AsyncSession]",
                    self.session_maker,  # pyright: ignore[reportUnknownMemberType]
                )
                session_maker.configure(sync_session_class=sync_maker)

        if self.session_maker is None:  # pyright: ignore
            msg = "Session maker was not initialized."  # type: ignore[unreachable]
            raise ImproperConfigurationError(msg)
        return cast("async_sessionmaker[AsyncSession]", self.session_maker)  # pyright: ignore[reportUnknownMemberType]

    @asynccontextmanager
    async def get_session(
        self,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get a session from the session maker.

        Yields:
            AsyncGenerator[AsyncSession, None]: An async context manager that yields an AsyncSession.
        """
        session_maker = self.create_session_maker()
        async with session_maker() as session:
            yield session

"""Sync SQLAlchemy configuration module."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy._listeners import set_async_context
from advanced_alchemy.config.common import GenericAlembicConfig, GenericSessionConfig, GenericSQLAlchemyConfig
from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Callable

    from advanced_alchemy.config.routing import RoutingConfig


__all__ = (
    "AlembicSyncConfig",
    "SQLAlchemySyncConfig",
    "SyncSessionConfig",
)


@dataclass
class SyncSessionConfig(GenericSessionConfig[Connection, Engine, Session]):
    """Configuration for synchronous SQLAlchemy sessions."""


@dataclass
class AlembicSyncConfig(GenericAlembicConfig):
    """Configuration for Alembic's synchronous migrations.

    For details see: https://alembic.sqlalchemy.org/en/latest/api/config.html
    """


@dataclass
class SQLAlchemySyncConfig(GenericSQLAlchemyConfig[Engine, Session, sessionmaker[Session]]):
    """Synchronous SQLAlchemy Configuration.

    Note:
        The alembic configuration options are documented in the Alembic documentation.

    Example:
        Basic sync configuration::

            config = SQLAlchemySyncConfig(
                connection_string="postgresql://user:pass@localhost/db",
            )

        Configuration with read/write routing::

            from advanced_alchemy.config.routing import RoutingConfig

            config = SQLAlchemySyncConfig(
                routing_config=RoutingConfig(
                    primary_connection_string="postgresql://user:pass@primary/db",
                    read_replicas=["postgresql://user:pass@replica/db"],
                ),
            )
    """

    create_engine_callable: "Callable[[str], Engine]" = create_engine
    """Callable that creates an :class:`Engine <sqlalchemy.Engine>` instance or instance of its subclass."""
    session_config: SyncSessionConfig = field(default_factory=SyncSessionConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration options for the :class:`sessionmaker<sqlalchemy.orm.sessionmaker>`."""
    session_maker_class: type[sessionmaker[Session]] = sessionmaker  # pyright: ignore[reportIncompatibleVariableOverride]
    """Sessionmaker class to use."""
    alembic_config: AlembicSyncConfig = field(default_factory=AlembicSyncConfig)
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
        super().__post_init__()

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        return super().__eq__(other)

    def create_session_maker(self) -> "Callable[[], Session]":
        """Get a session maker.

        If routing is configured, returns a routing-aware session maker.
        Otherwise, returns a standard session maker.

        Returns:
            A callable that creates session instances.
        """
        if self.session_maker:
            return self.session_maker

        # Use routing session maker if routing is configured
        if self.routing_config is not None:
            from advanced_alchemy.routing import RoutingSyncSessionMaker

            routing_maker = RoutingSyncSessionMaker(
                routing_config=self.routing_config,
                engine_config=self.engine_config_dict,
                session_config=self.session_config_dict,
            )
            self.session_maker = routing_maker
            return routing_maker

        # Default behavior from parent
        return super().create_session_maker()

    @contextmanager
    def get_session(self) -> "Generator[Session, None, None]":
        """Get a session context manager.

        Yields:
            Generator[sqlalchemy.orm.Session, None, None]: A context manager yielding an active SQLAlchemy Session.

        Examples:
            Using the session context manager:

            >>> with config.get_session() as session:
            ...     session.execute(...)
        """
        session_maker = self.create_session_maker()
        set_async_context(False)  # Set context for standalone usage
        with session_maker() as session:
            yield session

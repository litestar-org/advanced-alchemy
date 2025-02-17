"""Sync SQLAlchemy configuration module."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.config.common import GenericAlembicConfig, GenericSessionConfig, GenericSQLAlchemyConfig

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Callable


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

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        return super().__eq__(other)

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
        with session_maker() as session:
            yield session

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generator

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.config.common import GenericAlembicConfig, GenericSessionConfig, GenericSQLAlchemyConfig

if TYPE_CHECKING:
    from typing import Callable


__all__ = (
    "SQLAlchemySyncConfig",
    "SyncSessionConfig",
    "AlembicSyncConfig",
)


class SyncSessionConfig(GenericSessionConfig[Connection, Engine, Session]):
    pass


@dataclass
class AlembicSyncConfig(GenericAlembicConfig):
    """Configuration for a Sync Alembic's :class:`Config <alembic.config.Config>`.

    For details see: https://alembic.sqlalchemy.org/en/latest/api/config.html
    """


@dataclass
class SQLAlchemySyncConfig(GenericSQLAlchemyConfig[Engine, Session, sessionmaker[Session]]):
    """Sync SQLAlchemy Configuration."""

    create_engine_callable: Callable[[str], Engine] = create_engine
    """Callable that creates an :class:`AsyncEngine <sqlalchemy.ext.asyncio.AsyncEngine>` instance or instance of its
    subclass.
    """
    session_config: SyncSessionConfig = field(default_factory=SyncSessionConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration options for the :class:`sessionmaker<sqlalchemy.orm.sessionmaker>`."""
    session_maker_class: type[sessionmaker[Session]] = sessionmaker  # pyright: ignore[reportIncompatibleVariableOverride]
    """Sessionmaker class to use."""
    alembic_config: AlembicSyncConfig = field(default_factory=AlembicSyncConfig)
    """Configuration for the SQLAlchemy Alembic migrations.

    The configuration options are documented in the Alembic documentation.
    """

    def __post_init__(self) -> None:
        if self.metadata:
            self.alembic_config.target_metadata = self.metadata
        super().__post_init__()

    @contextmanager
    def get_session(
        self,
    ) -> Generator[Session, None, None]:
        session_maker = self.create_session_maker()
        with session_maker() as session:
            yield session

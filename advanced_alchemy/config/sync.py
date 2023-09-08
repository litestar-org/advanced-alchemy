from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .common import GenericAlembicConfig, GenericSessionConfig, GenericSQLAlchemyConfig

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
class SQLAlchemySyncConfig(GenericSQLAlchemyConfig[Engine, Session, sessionmaker]):
    """Sync SQLAlchemy Configuration."""

    create_engine_callable: Callable[[str], Engine] = create_engine
    """Callable that creates an :class:`AsyncEngine <sqlalchemy.ext.asyncio.AsyncEngine>` instance or instance of its
    subclass.
    """
    session_config: SyncSessionConfig = field(default_factory=SyncSessionConfig)  # pyright:ignore  # noqa: PGH003
    """Configuration options for the :class:`sessionmaker<sqlalchemy.orm.sessionmaker>`."""
    session_maker_class: type[sessionmaker] = sessionmaker
    """Sessionmaker class to use."""
    alembic_config: AlembicSyncConfig = field(default_factory=AlembicSyncConfig)
    """Configuration for the SQLAlchemy Alembic migrations.

    The configuration options are documented in the Alembic documentation.
    """

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from advanced_alchemy.config.common import (
    GenericAlembicConfig,
    GenericSessionConfig,
    GenericSQLAlchemyConfig,
)
from advanced_alchemy.utils.dataclass import Empty

if TYPE_CHECKING:
    from typing import Callable

    from sqlalchemy.orm import Session

    from advanced_alchemy.utils.dataclass import EmptyType

__all__ = (
    "SQLAlchemyAsyncConfig",
    "AsyncSessionConfig",
    "AlembicAsyncConfig",
)


@dataclass
class AsyncSessionConfig(GenericSessionConfig[AsyncConnection, AsyncEngine, AsyncSession]):
    """SQLAlchemy async session config."""

    sync_session_class: type[Session] | None | EmptyType = Empty
    """A :class:`Session <sqlalchemy.orm.Session>` subclass or other callable which will be used to construct the
    :class:`Session <sqlalchemy.orm.Session>` which will be proxied. This parameter may be used to provide custom
    :class:`Session <sqlalchemy.orm.Session>` subclasses. Defaults to the
    :attr:`AsyncSession.sync_session_class <sqlalchemy.ext.asyncio.AsyncSession.sync_session_class>` class-level
    attribute."""


@dataclass
class AlembicAsyncConfig(GenericAlembicConfig):
    """Configuration for an Async Alembic's :class:`Config <alembic.config.Config>`.

    For details see: https://alembic.sqlalchemy.org/en/latest/api/config.html
    """


@dataclass
class SQLAlchemyAsyncConfig(GenericSQLAlchemyConfig[AsyncEngine, AsyncSession, async_sessionmaker[AsyncSession]]):
    """Async SQLAlchemy Configuration."""

    create_engine_callable: Callable[[str], AsyncEngine] = create_async_engine
    """Callable that creates an :class:`AsyncEngine <sqlalchemy.ext.asyncio.AsyncEngine>` instance or instance of its
    subclass.
    """
    session_config: AsyncSessionConfig = field(default_factory=AsyncSessionConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration options for the :class:`async_sessionmaker<sqlalchemy.ext.asyncio.async_sessionmaker>`."""
    session_maker_class: type[async_sessionmaker[AsyncSession]] = async_sessionmaker  # pyright: ignore[reportIncompatibleVariableOverride]
    """Sessionmaker class to use."""
    alembic_config: AlembicAsyncConfig = field(default_factory=AlembicAsyncConfig)
    """Configuration for the SQLAlchemy Alembic migrations.

    The configuration options are documented in the Alembic documentation.
    """

    def __post_init__(self) -> None:
        if self.metadata:
            self.alembic_config.target_metadata = self.metadata
        super().__post_init__()

    @asynccontextmanager
    async def get_session(
        self,
    ) -> AsyncGenerator[AsyncSession, None]:
        session_maker = self.create_session_maker()
        async with session_maker() as session:
            yield session

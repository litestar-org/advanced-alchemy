from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from advanced_alchemy.config.sync import SQLAlchemySyncConfig

if TYPE_CHECKING:
    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig


class Adapter(Protocol):
    supported_drivers: set[str] = set()
    dialect: str
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig
    encoding: str | None = None

    engine: Engine | None = None
    async_engine: AsyncEngine | None = None
    original_database_name: str | None = None

    def __init__(self, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig, encoding: str = "utf8") -> None:
        self.config = config
        self.encoding = encoding

        if isinstance(config, SQLAlchemySyncConfig):
            self.setup(config)
        else:
            self.setup_async(config)

    def setup_async(self, config: SQLAlchemyAsyncConfig) -> None: ...
    def setup(self, config: SQLAlchemySyncConfig) -> None: ...

    async def create_async(self) -> None: ...
    def create(self) -> None: ...

    async def drop_async(self) -> None: ...
    def drop(self) -> None: ...


class SQLiteAdapter(Adapter):
    supported_drivers: set[str] = {"pysqlite", "aiosqlite"}
    dialect: str = "sqlite"

    def setup(self, config: SQLAlchemySyncConfig) -> None:
        self.engine = config.get_engine()
        self.original_database_name = self.engine.url.database

    def setup_async(self, config: SQLAlchemyAsyncConfig) -> None:
        self.async_engine = config.get_engine()
        self.original_database_name = self.async_engine.url.database

    def create(self) -> None:
        if self.engine is not None and self.original_database_name and self.original_database_name != ":memory:":
            with self.engine.begin() as conn:
                conn.execute(text("CREATE TABLE DB(id int)"))
                conn.execute(text("DROP TABLE DB"))

    async def create_async(self) -> None:
        if self.async_engine is not None:
            async with self.async_engine.begin() as conn:
                await conn.execute(text("CREATE TABLE DB(id int)"))
                await conn.execute(text("DROP TABLE DB"))

    def drop(self) -> None:
        return self._drop()

    async def drop_async(self) -> None:
        return self._drop()

    def _drop(self) -> None:
        if self.original_database_name and self.original_database_name != ":memory:":
            Path(self.original_database_name).unlink()


class PostgresAdapter(Adapter):
    supported_drivers: set[str] = {"asyncpg", "pg8000", "psycopg", "psycopg2", "psycopg2cffi"}
    dialect: str = "postgresql"

    def _set_url(self, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> URL:
        original_url = self.config.get_engine().url
        self.original_database_name = original_url.database
        return original_url._replace(database="postgres")

    def setup(self, config: SQLAlchemySyncConfig) -> None:
        updated_url = self._set_url(config)
        self.engine = create_engine(updated_url, isolation_level="AUTOCOMMIT")

    def setup_async(self, config: SQLAlchemyAsyncConfig) -> None:
        updated_url = self._set_url(config)
        self.async_engine = create_async_engine(updated_url, isolation_level="AUTOCOMMIT")

    def create(self) -> None:
        if self.engine:
            with self.engine.begin() as conn:
                sql = f"CREATE DATABASE {self.original_database_name} ENCODING '{self.encoding}'"
                conn.execute(text(sql))

    async def create_async(self) -> None:
        if self.async_engine:
            async with self.async_engine.begin() as conn:
                sql = f"CREATE DATABASE {self.original_database_name} ENCODING '{self.encoding}'"
                await conn.execute(text(sql))

    def drop(self) -> None:
        if self.engine:
            with self.engine.begin() as conn:
                # Disconnect all users from the database we are dropping.
                version = conn.dialect.server_version_info
                sql = self._disconnect_users_sql(version, self.original_database_name)
                conn.execute(text(sql))
                conn.execute(text(f"DROP DATABASE {self.original_database_name}"))

    async def drop_async(self) -> None:
        if self.async_engine:
            async with self.async_engine.begin() as conn:
                # Disconnect all users from the database we are dropping.
                version = conn.dialect.server_version_info
                sql = self._disconnect_users_sql(version, self.original_database_name)
                await conn.execute(text(sql))
                await conn.execute(text(f"DROP DATABASE {self.original_database_name}"))

    def _disconnect_users_sql(self, version: tuple[int, int] | None, database: str | None) -> str:
        pid_column = ("pid" if version >= (9, 2) else "procpid") if version else "procpid"
        return f"""
        SELECT pg_terminate_backend(pg_stat_activity.{pid_column})
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{database}'
        AND {pid_column} <> pg_backend_pid();"""  # noqa: S608


ADAPTERS = {"sqlite": SQLiteAdapter, "postgresql": PostgresAdapter}


def get_adapter(config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig, encoding: str = "utf8") -> Adapter:
    dialect_name = config.get_engine().url.get_dialect().name
    adapter_class = ADAPTERS.get(dialect_name)

    if not adapter_class:
        msg = f"No adapter available for {dialect_name}"
        raise ValueError(msg)

    driver = config.get_engine().url.get_dialect().driver
    if driver not in adapter_class.supported_drivers:
        msg = f"{dialect_name} adapter does not support the {driver} driver"
        raise ValueError(msg)

    return adapter_class(config, encoding=encoding)


async def create_database(config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig, encoding: str = "utf8") -> None:
    adapter = get_adapter(config, encoding)
    if isinstance(config.get_engine(), AsyncEngine):
        await adapter.create_async()
    else:
        adapter.create()


async def drop_database(config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig) -> None:
    adapter = get_adapter(config)
    if isinstance(config.get_engine(), AsyncEngine):
        await adapter.drop_async()
    else:
        adapter.drop()

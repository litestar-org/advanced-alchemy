from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from advanced_alchemy.config.sync import SQLAlchemySyncConfig

if TYPE_CHECKING:
    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig


class Adapter(Protocol):
    supported_drivers: list[str] = []
    dialect: str
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig
    encoding: str

    _engine: Engine | None
    _async_engine: AsyncEngine | None
    _database: str | None

    def __init__(self, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig, encoding: str = "utf8") -> None:
        self.config = config
        self.encoding = encoding
        self._engine: Engine | None = None
        self._async_engine: AsyncEngine | None = None

        if isinstance(config, SQLAlchemySyncConfig):
            self._engine = config.get_engine()
            self._database = self._engine.url.database
        else:
            self._async_engine = config.get_engine()
            self._database = self._async_engine.url.database

    async def create_async(self) -> None: ...
    def create(self) -> None: ...

    async def drop_async(self) -> None: ...
    def drop(self) -> None: ...


class SQLiteAdapter(Adapter):
    supported_drivers: list[str] = ["pysqlite", "aiosqlite"]
    dialect: str = "sqlite"

    def create(self) -> None:
        if self._engine is not None and self._database and self._database != ":memory:":
            with self._engine.begin() as conn:
                conn.execute(text("CREATE TABLE DB(id int)"))
                conn.execute(text("DROP TABLE DB"))

    async def create_async(self) -> None:
        if self._async_engine is not None:
            async with self._async_engine.begin() as conn:
                await conn.execute(text("CREATE TABLE DB(id int)"))
                await conn.execute(text("DROP TABLE DB"))

    def drop(self) -> None:
        return self._drop()

    async def drop_async(self) -> None:
        return self._drop()

    def _drop(self) -> None:
        if self._database and self._database != ":memory:":
            Path(self._database).unlink()


ADAPTERS = {"sqlite": SQLiteAdapter}


def get_adapter(config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig, encoding: str = "utf8") -> Adapter:
    dialect_name = config.get_engine().url.get_dialect().name
    driver = config.get_engine().url.get_dialect().driver

    adapter_class = ADAPTERS.get(dialect_name)

    if not adapter_class:
        msg = f"No adapter available for {dialect_name}"
        raise ValueError(msg)

    if driver not in adapter_class.supported_drivers:
        msg = f"{dialect_name} adapter does not support the {driver} driver"
        raise ValueError(msg)

    return adapter_class(config, encoding=encoding)


async def create_database(config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig, encoding: str = "utf8") -> None:
    adapter = get_adapter(config, encoding)
    engine = config.get_engine()
    if isinstance(engine, AsyncEngine):
        await adapter.create_async()
    else:
        adapter.create()


async def drop_database(config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig) -> None:
    adapter = get_adapter(config)
    engine = config.get_engine()
    if isinstance(engine, AsyncEngine):
        await adapter.drop_async()
    else:
        adapter.drop()

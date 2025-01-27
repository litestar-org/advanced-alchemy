from __future__ import annotations

import asyncio
from copy import copy
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from advanced_alchemy.utils.dataclass import Empty

if TYPE_CHECKING:
    from sqlalchemy.engine.url import URL

    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig


def _set_engine_database_url(url: URL, database: str | None) -> URL:
    if hasattr(url, "_replace"):
        new_url = url._replace(database=database)
    else:  # SQLAlchemy <1.4
        new_url = copy(url)
        new_url.database = database  # type: ignore  # noqa: PGH003
    return new_url


def get_masterdb_url(url: URL) -> URL:
    dialect_name = url.get_dialect().name

    if dialect_name == "postgresql":
        url = _set_engine_database_url(url, database="postgres")
    elif dialect_name == "mssql":
        url = _set_engine_database_url(url, database="master")
    elif dialect_name == "cockroachdb":
        url = _set_engine_database_url(url, database="defaultdb")
    elif dialect_name != "sqlite":
        url = _set_engine_database_url(url, database=None)

    return url


def create_database(config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig, encoding: str = "utf8") -> None:
    url = config.get_engine().url
    database = url.database
    dialect_name = url.get_dialect().name
    dialect_driver = url.get_dialect().driver

    url = get_masterdb_url(url)

    if (dialect_name == "mssql" and dialect_driver in {"pymssql", "pyodbc"}) or (
        dialect_name == "postgresql" and dialect_driver in {"asyncpg", "pg8000", "psycopg", "psycopg2", "psycopg2cffi"}
    ):
        config.engine_config.isolation_level = "AUTOCOMMIT"

    engine = config.create_engine_callable(str(url))
    if isinstance(engine, AsyncEngine):
        asyncio.run(create_database_async(engine, database, encoding))
    else:
        create_database_sync(engine, database, encoding)


def create_database_sync(engine: Engine, database: str | None, encoding: str = "utf8") -> None:
    dialect_name = engine.url.get_dialect().name
    if dialect_name == "postgresql":
        with engine.begin() as conn:
            sql = f"CREATE DATABASE {database} ENCODING '{encoding}'"
            conn.execute(text(sql))

    elif dialect_name == "mysql":
        with engine.begin() as conn:
            sql = f"CREATE DATABASE {database} CHARACTER SET = '{encoding}'"
            conn.execute(text(sql))

    elif dialect_name == "sqlite":
        if database and database != ":memory:":
            with engine.begin() as conn:
                conn.execute(text("CREATE TABLE DB(id int)"))
                conn.execute(text("DROP TABLE DB"))
        else:
            pass
    else:
        with engine.begin() as conn:
            sql = f"CREATE DATABASE {database}"
            conn.execute(text(sql))

    engine.dispose()


async def create_database_async(engine: AsyncEngine, database: str | None, encoding: str = "utf8") -> None:
    dialect_name = engine.url.get_dialect().name
    if dialect_name == "postgresql":
        async with engine.begin() as conn:
            sql = f"CREATE DATABASE {database} ENCODING '{encoding}'"
            await conn.execute(text(sql))

    elif dialect_name == "mysql":
        async with engine.begin() as conn:
            sql = f"CREATE DATABASE {database} CHARACTER SET = '{encoding}'"
            await conn.execute(text(sql))

    elif dialect_name == "sqlite":
        if database and database != ":memory:":
            async with engine.begin() as conn:
                await conn.execute(text("CREATE TABLE DB(id int)"))
                await conn.execute(text("DROP TABLE DB"))
        else:
            pass
    else:
        async with engine.begin() as conn:
            sql = f"CREATE DATABASE {database}"
            await conn.execute(text(sql))

    await engine.dispose()


def drop_database(config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> None:
    url = config.get_engine().url
    database = url.database
    dialect_name = url.get_dialect().name
    dialect_driver = url.get_dialect().driver

    url = get_masterdb_url(url)

    if dialect_name == "mssql" and dialect_driver in {"pymssql", "pyodbc"}:
        if config.engine_config.connect_args is Empty:
            config.engine_config.connect_args = {}
        else:
            config.engine_config.connect_args["autocommit"] = True  # type: ignore  # noqa: PGH003
    elif dialect_name == "postgresql" and dialect_driver in {
        "asyncpg",
        "pg8000",
        "psycopg",
        "psycopg2",
        "psycopg2cffi",
    }:
        config.engine_config.isolation_level = "AUTOCOMMIT"

    engine = config.create_engine_callable(str(url))
    if isinstance(engine, AsyncEngine):
        asyncio.run(drop_database_async(engine, database))
    else:
        drop_database_sync(engine, database)


def _disconnect_users_sql(version: tuple[int, int] | None, database: str | None) -> str:
    pid_column = ("pid" if version >= (9, 2) else "procpid") if version else "procpid"
    return f"""
    SELECT pg_terminate_backend(pg_stat_activity.{pid_column})
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = '{database}'
    AND {pid_column} <> pg_backend_pid();
    """  # noqa: S608


async def drop_database_async(engine: AsyncEngine, database: str | None) -> None:
    dialect_name = engine.url.get_dialect().name
    if dialect_name == "sqlite":
        if database and database != ":memory:":
            Path(database).unlink()
    elif dialect_name == "postgresql":
        async with engine.begin() as conn:
            # Disconnect all users from the database we are dropping.
            version = conn.dialect.server_version_info
            sql = _disconnect_users_sql(version, database)
            await conn.execute(text(sql))

            # Drop the database.
            sql = f"DROP DATABASE {database}"
            await conn.execute(text(sql))
    else:
        async with engine.begin() as conn:
            sql = f"DROP DATABASE {database}"
            await conn.execute(text(sql))

    await engine.dispose()


def drop_database_sync(engine: Engine, database: str | None) -> None:
    dialect_name = engine.url.get_dialect().name
    if dialect_name == "sqlite":
        if database and database != ":memory:":
            Path(database).unlink()
    elif dialect_name == "postgresql":
        with engine.begin() as conn:
            # Disconnect all users from the database we are dropping.
            version = conn.dialect.server_version_info
            sql = _disconnect_users_sql(version, database)
            conn.execute(text(sql))

            # Drop the database.
            sql = f"DROP DATABASE {database}"
            conn.execute(text(sql))
    else:
        with engine.begin() as conn:
            sql = f"DROP DATABASE {database}"
            conn.execute(text(sql))

    engine.dispose()

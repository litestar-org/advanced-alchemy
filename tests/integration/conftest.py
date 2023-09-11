from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator, Generator, cast

import pytest
from pytest import FixtureRequest
from sqlalchemy import URL, Engine, NullPool, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def _patch_bases(monkeypatch: MonkeyPatch) -> None:
    """Ensure new registry state for every test.

    This prevents errors such as "Table '...' is already defined for
    this MetaData instance...
    """
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base

    class NewUUIDBase(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        ...

    class NewUUIDAuditBase(base.UUIDPrimaryKey, base.CommonTableAttributes, base.AuditColumns, DeclarativeBase):
        ...

    class NewBigIntBase(base.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        ...

    class NewBigIntAuditBase(base.BigIntPrimaryKey, base.CommonTableAttributes, base.AuditColumns, DeclarativeBase):
        ...

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)
    monkeypatch.setattr(base, "UUIDAuditBase", NewUUIDAuditBase)
    monkeypatch.setattr(base, "BigIntBase", NewBigIntBase)
    monkeypatch.setattr(base, "BigIntAuditBase", NewBigIntAuditBase)


@pytest.fixture()
def duckdb_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_engine(f"duckdb:///{tmp_path}/test.duck.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def oracle18c_engine(docker_ip: str, oracle18c_service: None) -> Engine:
    """Oracle 18c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle18c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    return create_engine(
        "oracle+oracledb://:@",
        thick_mode=False,
        connect_args={
            "user": "app",
            "password": "super-secret",
            "host": docker_ip,
            "port": 1512,
            "service_name": "xepdb1",
            "encoding": "UTF-8",
            "nencoding": "UTF-8",
        },
        poolclass=NullPool,
    )


@pytest.fixture()
def oracle23c_engine(docker_ip: str, oracle23c_service: None) -> Engine:
    """Oracle 23c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle23c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    return create_engine(
        "oracle+oracledb://:@",
        thick_mode=False,
        connect_args={
            "user": "app",
            "password": "super-secret",
            "host": docker_ip,
            "port": 1513,
            "service_name": "FREEPDB1",
            "encoding": "UTF-8",
            "nencoding": "UTF-8",
        },
        poolclass=NullPool,
    )


@pytest.fixture()
def psycopg_engine(docker_ip: str, postgres_service: None) -> Engine:
    """Postgresql instance for end-to-end testing."""
    return create_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password="super-secret",
            host=docker_ip,
            port=5423,
            database="postgres",
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture()
def sqlite_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def spanner_engine(docker_ip: str, spanner_service: None, monkeypatch: MonkeyPatch) -> Engine:
    """Postgresql instance for end-to-end testing."""
    monkeypatch.setenv("SPANNER_EMULATOR_HOST", "localhost:9010")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "emulator-test-project")

    return create_engine(
        "spanner+spanner:///projects/emulator-test-project/instances/test-instance/databases/test-database",
    )


@pytest.fixture(
    name="engine",
    params=[
        pytest.param(
            "duckdb_engine",
            marks=[
                pytest.mark.duckdb,
                pytest.mark.integration,
                pytest.mark.xdist_group("duckdb"),
            ],
        ),
        pytest.param(
            "oracle18c_engine",
            marks=[
                pytest.mark.oracledb,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23c_engine",
            marks=[
                pytest.mark.oracledb,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle23"),
            ],
        ),
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
            ],
        ),
    ],
)
def engine(request: FixtureRequest) -> Engine:
    return cast(Engine, request.getfixturevalue(request.param))


@pytest.fixture()
def session_maker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def session(session_maker: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = session_maker()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
async def aiosqlite_engine(tmp_path: Path) -> AsyncGenerator[AsyncEngine, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def asyncmy_engine(docker_ip: str, mysql_service: None) -> AsyncEngine:
    """Postgresql instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="mysql+asyncmy",
            username="app",
            password="super-secret",
            host=docker_ip,
            port=3360,
            database="db",
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture()
async def asyncpg_engine(docker_ip: str, postgres_service: None) -> AsyncEngine:
    """Postgresql instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="postgresql+asyncpg",
            username="postgres",
            password="super-secret",
            host=docker_ip,
            port=5423,
            database="postgres",
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture()
async def psycopg_async_engine(docker_ip: str, postgres_service: None) -> AsyncEngine:
    """Postgresql instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="postgresql+psycopg",
            username="postgres",
            password="super-secret",
            host=docker_ip,
            port=5423,
            database="postgres",
            query={},  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture(
    name="async_engine",
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
            ],
        ),
        pytest.param(
            "asyncmy_engine",
            marks=[
                pytest.mark.asyncmy,
                pytest.mark.integration,
                pytest.mark.xdist_group("mysql"),
            ],
        ),
        pytest.param(
            "asyncpg_engine",
            marks=[
                pytest.mark.asyncpg,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "psycopg_async_engine",
            marks=[
                pytest.mark.psycopg_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
    ],
)
def async_engine(request: FixtureRequest) -> AsyncEngine:
    return cast(AsyncEngine, request.getfixturevalue(request.param))


@pytest.fixture()
def async_session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=async_engine, expire_on_commit=False)


@pytest.fixture()
async def async_session(
    async_engine: AsyncEngine,
    async_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    session = async_session_maker()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


# @pytest.fixture()
# async def sync_sqlalchemy_config(engine: Engine, session_maker: sessionmaker[Session]) -> SQLAlchemySyncConfig:
#
#
# @pytest.fixture()
# async def async_sqlalchemy_config(
#     async_engine: AsyncEngine,
#     async_session_maker: async_sessionmaker[AsyncSession],
# ) -> SQLAlchemyAsyncConfig:
#
#
# @pytest.fixture()
# async def sync_alembic_commands(sync_sqlalchemy_config: SQLAlchemySyncConfig) -> commands.AlembicCommands:
#
#
# @pytest.fixture()
# async def async_alembic_commands(async_sqlalchemy_config: SQLAlchemyAsyncConfig) -> commands.AlembicCommands:
#
#
# @pytest.fixture(params=["sync_alembic_commands", "async_alembic_commands"], autouse=True)
# def alembic_commands(request: FixtureRequest) -> commands.AlembicCommands:

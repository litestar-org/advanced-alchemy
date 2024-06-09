from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator, Generator, cast
from unittest.mock import NonCallableMagicMock, create_autospec

import pytest
from pytest import FixtureRequest
from sqlalchemy import URL, Dialect, Engine, NullPool, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def _patch_bases(monkeypatch: MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Ensure new registry state for every test.

    This prevents errors such as "Table '...' is already defined for
    this MetaData instance...
    """
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base

    class NewUUIDBase(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDAuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv6Base(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv6AuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv7Base(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv7AuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewBigIntBase(base.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewBigIntAuditBase(base.BigIntPrimaryKey, base.CommonTableAttributes, base.AuditColumns, DeclarativeBase): ...

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)
    monkeypatch.setattr(base, "UUIDAuditBase", NewUUIDAuditBase)
    monkeypatch.setattr(base, "UUIDv6Base", NewUUIDv6Base)
    monkeypatch.setattr(base, "UUIDv6AuditBase", NewUUIDv6AuditBase)
    monkeypatch.setattr(base, "UUIDv7Base", NewUUIDv7Base)
    monkeypatch.setattr(base, "UUIDv7AuditBase", NewUUIDv7AuditBase)
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
def mssql_engine(docker_ip: str, mssql_service: None) -> Engine:
    """MS SQL instance for end-to-end testing."""
    return create_engine(
        URL(
            drivername="mssql+pyodbc",
            username="sa",
            password="Super-secret1",
            host=docker_ip,
            port=1344,
            database="master",
            query={
                "driver": "ODBC Driver 18 for SQL Server",
                "encrypt": "no",
                "TrustServerCertificate": "yes",
            },  # type:ignore[arg-type]
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
        poolclass=NullPool,
    )


@pytest.fixture()
def cockroachdb_engine(docker_ip: str, cockroachdb_service: None) -> Engine:
    """CockroachDB instance for end-to-end testing."""
    return create_engine(
        url="cockroachdb://root@localhost:26257/defaultdb?sslmode=disable",
        poolclass=NullPool,
    )


@pytest.fixture()
async def mock_sync_engine() -> NonCallableMagicMock:
    """Return a mocked Engine instance."""
    mock = cast(NonCallableMagicMock, create_autospec(Engine, instance=True))
    mock.dialect = create_autospec(Dialect, instance=True)
    mock.dialect.name = "mock"
    return mock


@pytest.fixture(
    name="engine",
    params=[
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
            ],
        ),
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
                pytest.mark.oracledb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23c_engine",
            marks=[
                pytest.mark.oracledb_sync,
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
            "cockroachdb_engine",
            marks=[
                pytest.mark.cockroachdb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
        pytest.param(
            "mssql_engine",
            marks=[
                pytest.mark.mssql_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("mssql"),
            ],
        ),
        pytest.param(
            "mock_sync_engine",
            marks=[
                pytest.mark.mock_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("mock"),
            ],
        ),
    ],
)
def engine(request: FixtureRequest) -> Engine:
    return cast(Engine, request.getfixturevalue(request.param))


@pytest.fixture()
def session(engine: Engine, request: FixtureRequest) -> Generator[Session, None, None]:
    if "mock_sync_engine" in request.fixturenames:
        session = create_autospec(Session, instance=True)
        session.bind = engine
        yield session
    else:
        session = sessionmaker(bind=engine, expire_on_commit=False)()
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


@pytest.fixture()
async def cockroachdb_async_engine(docker_ip: str, cockroachdb_service: None) -> AsyncEngine:
    """Cockroach DB async engine instance for end-to-end testing."""
    return create_async_engine(
        url="cockroachdb+asyncpg://root@localhost:26257/defaultdb",
        poolclass=NullPool,
    )


@pytest.fixture()
async def mssql_async_engine(docker_ip: str, mssql_service: None) -> AsyncEngine:
    """MS SQL instance for end-to-end testing."""
    return create_async_engine(
        URL(
            drivername="mssql+aioodbc",
            username="sa",
            password="Super-secret1",
            host=docker_ip,
            port=1344,
            database="master",
            query={
                "driver": "ODBC Driver 18 for SQL Server",
                "encrypt": "no",
                "TrustServerCertificate": "yes",
                # NOTE: MARS_Connection is only needed for the concurrent async tests
                # lack of this causes some tests to fail
                # https://github.com/litestar-org/advanced-alchemy/actions/runs/6800623970/job/18493034767?pr=94
                "MARS_Connection": "yes",
            },  # type:ignore[arg-type]
        ),
        poolclass=NullPool,
    )


@pytest.fixture()
async def oracle18c_async_engine(docker_ip: str, oracle18c_service: None) -> AsyncEngine:
    """Oracle 18c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle18c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    return create_async_engine(
        "oracle+oracledb://:@",
        thick_mode=False,
        connect_args={
            "user": "app",
            "password": "super-secret",
            "host": docker_ip,
            "port": 1512,
            "service_name": "xepdb1",
        },
        poolclass=NullPool,
    )


@pytest.fixture()
async def oracle23c_async_engine(docker_ip: str, oracle23c_service: None) -> AsyncEngine:
    """Oracle 23c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle23c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    return create_async_engine(
        "oracle+oracledb://:@",
        thick_mode=False,
        connect_args={
            "user": "app",
            "password": "super-secret",
            "host": docker_ip,
            "port": 1513,
            "service_name": "FREEPDB1",
        },
        poolclass=NullPool,
    )


@pytest.fixture()
async def mock_async_engine() -> NonCallableMagicMock:
    """Return a mocked AsyncEngine instance."""
    mock = cast(NonCallableMagicMock, create_autospec(AsyncEngine, instance=True))
    mock.dialect = create_autospec(Dialect, instance=True)
    mock.dialect.name = "mock"
    return mock


@pytest.fixture(
    name="async_engine",
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
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
        pytest.param(
            "cockroachdb_async_engine",
            marks=[
                pytest.mark.cockroachdb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
        pytest.param(
            "mssql_async_engine",
            marks=[
                pytest.mark.mssql_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("mssql"),
            ],
        ),
        pytest.param(
            "oracle18c_async_engine",
            marks=[
                pytest.mark.oracledb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23c_async_engine",
            marks=[
                pytest.mark.oracledb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle23"),
            ],
        ),
        pytest.param(
            "mock_async_engine",
            marks=[
                pytest.mark.mock_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("mock"),
            ],
        ),
    ],
)
def async_engine(request: FixtureRequest) -> AsyncEngine:
    return cast(AsyncEngine, request.getfixturevalue(request.param))


@pytest.fixture()
async def async_session(
    async_engine: AsyncEngine,
    request: FixtureRequest,
) -> AsyncGenerator[AsyncSession, None]:
    if "mock_async_engine" in request.fixturenames:
        session = create_autospec(AsyncSession, instance=True)
        session.bind = async_engine
        yield session
    else:
        session = async_sessionmaker(bind=async_engine, expire_on_commit=False)()
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

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, cast
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

    from advanced_alchemy import base, mixins

    class NewUUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDAuditBase(
        mixins.UUIDPrimaryKey,
        base.CommonTableAttributes,
        mixins.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv6Base(mixins.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv6AuditBase(
        mixins.UUIDPrimaryKey,
        base.CommonTableAttributes,
        mixins.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv7Base(mixins.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv7AuditBase(
        mixins.UUIDPrimaryKey,
        base.CommonTableAttributes,
        mixins.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewNanoIDBase(mixins.NanoIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewNanoIDAuditBase(
        mixins.NanoIDPrimaryKey,
        base.CommonTableAttributes,
        mixins.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewBigIntBase(mixins.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewBigIntAuditBase(
        mixins.BigIntPrimaryKey,
        base.CommonTableAttributes,
        mixins.AuditColumns,
        DeclarativeBase,
    ): ...

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)
    monkeypatch.setattr(base, "UUIDAuditBase", NewUUIDAuditBase)
    monkeypatch.setattr(base, "UUIDv6Base", NewUUIDv6Base)
    monkeypatch.setattr(base, "UUIDv6AuditBase", NewUUIDv6AuditBase)
    monkeypatch.setattr(base, "UUIDv7Base", NewUUIDv7Base)
    monkeypatch.setattr(base, "UUIDv7AuditBase", NewUUIDv7AuditBase)
    monkeypatch.setattr(base, "NanoIDBase", NewNanoIDBase)
    monkeypatch.setattr(base, "NanoIDAuditBase", NewNanoIDAuditBase)
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
def oracle18c_engine(docker_ip: str, oracle18c_service: None) -> Generator[Engine, None, None]:
    """Oracle 18c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle18c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_engine(
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
def oracle23c_engine(docker_ip: str, oracle23c_service: None) -> Generator[Engine, None, None]:
    """Oracle 23c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle23c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_engine(
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
def psycopg_engine(docker_ip: str, postgres_service: None) -> Generator[Engine, None, None]:
    """Postgresql instance for end-to-end testing."""
    yield create_engine(
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
def mssql_engine(docker_ip: str, mssql_service: None) -> Generator[Engine, None, None]:
    """MS SQL instance for end-to-end testing."""
    yield create_engine(
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
def spanner_engine(docker_ip: str, spanner_service: None, monkeypatch: MonkeyPatch) -> Generator[Engine, None, None]:
    """Postgresql instance for end-to-end testing."""
    monkeypatch.setenv("SPANNER_EMULATOR_HOST", "localhost:9010")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "emulator-test-project")

    yield create_engine(
        "spanner+spanner:///projects/emulator-test-project/instances/test-instance/databases/test-database",
        poolclass=NullPool,
    )


@pytest.fixture()
def cockroachdb_engine(docker_ip: str, cockroachdb_service: None) -> Generator[Engine, None, None]:
    """CockroachDB instance for end-to-end testing."""
    yield create_engine(
        url="cockroachdb://root@localhost:26257/defaultdb?sslmode=disable",
        poolclass=NullPool,
    )


@pytest.fixture()
def mock_sync_engine() -> Generator[NonCallableMagicMock, None, None]:
    """Return a mocked Engine instance."""
    mock = cast(NonCallableMagicMock, create_autospec(Engine, instance=True))
    mock.dialect = create_autospec(Dialect, instance=True)
    mock.dialect.name = "mock"
    yield mock


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
def engine(request: FixtureRequest) -> Generator[Engine, None, None]:
    yield cast(Engine, request.getfixturevalue(request.param))


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
async def asyncmy_engine(docker_ip: str, mysql_service: None) -> AsyncGenerator[AsyncEngine, None]:
    """Postgresql instance for end-to-end testing."""
    yield create_async_engine(
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
async def asyncpg_engine(docker_ip: str, postgres_service: None) -> AsyncGenerator[AsyncEngine, None]:
    """Postgresql instance for end-to-end testing."""
    yield create_async_engine(
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
async def psycopg_async_engine(docker_ip: str, postgres_service: None) -> AsyncGenerator[AsyncEngine, None]:
    """Postgresql instance for end-to-end testing."""
    yield create_async_engine(
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
async def cockroachdb_async_engine(docker_ip: str, cockroachdb_service: None) -> AsyncGenerator[AsyncEngine, None]:
    """Cockroach DB async engine instance for end-to-end testing."""
    yield create_async_engine(
        url="cockroachdb+asyncpg://root@localhost:26257/defaultdb",
        poolclass=NullPool,
    )


@pytest.fixture()
async def mssql_async_engine(docker_ip: str, mssql_service: None) -> AsyncGenerator[AsyncEngine, None]:
    """MS SQL instance for end-to-end testing."""
    yield create_async_engine(
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
async def oracle18c_async_engine(docker_ip: str, oracle18c_service: None) -> AsyncGenerator[AsyncEngine, None]:
    """Oracle 18c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle18c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(
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
async def oracle23c_async_engine(docker_ip: str, oracle23c_service: None) -> AsyncGenerator[AsyncEngine, None]:
    """Oracle 23c instance for end-to-end testing.

    Args:
        docker_ip: IP address for TCP connection to Docker containers.
        oracle23c_service: ...

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(
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
async def mock_async_engine() -> AsyncGenerator[NonCallableMagicMock, None]:
    """Return a mocked AsyncEngine instance."""
    mock = cast(NonCallableMagicMock, create_autospec(AsyncEngine, instance=True))
    mock.dialect = create_autospec(Dialect, instance=True)
    mock.dialect.name = "mock"
    yield mock


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
async def async_engine(request: FixtureRequest) -> AsyncGenerator[AsyncEngine, None]:
    yield cast(AsyncEngine, request.getfixturevalue(request.param))


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

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, cast
from unittest.mock import NonCallableMagicMock, create_autospec

import pytest
from google.cloud import spanner  # pyright: ignore
from pytest import FixtureRequest
from sqlalchemy import Dialect, Engine, NullPool, create_engine, text
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
    engine = create_engine(f"duckdb:///{tmp_path}/test.duck.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def oracle18c_engine(oracle18c_url: str) -> Generator[Engine, None, None]:
    yield create_engine(oracle18c_url, poolclass=NullPool)


@pytest.fixture()
def oracle23ai_engine(oracle23ai_url: str) -> Generator[Engine, None, None]:
    yield create_engine(oracle23ai_url, poolclass=NullPool)


@pytest.fixture()
def psycopg_engine(postgres_psycopg_url: str) -> Generator[Engine, None, None]:
    yield create_engine(postgres_psycopg_url, poolclass=NullPool)


@pytest.fixture()
def mssql_engine(mssql_pyodbc_url: str) -> Generator[Engine, None, None]:
    yield create_engine(mssql_pyodbc_url, poolclass=NullPool)


@pytest.fixture()
def sqlite_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def spanner_engine(spanner_url: str, spanner_connection: spanner.Client) -> Generator[Engine, None, None]:
    # Environment variables are still set by set_spanner_emulator in root conftest,
    # but we use the explicit URL fixture now for consistency.

    yield create_engine(spanner_url, poolclass=NullPool, connect_args={"client": spanner_connection})


@pytest.fixture()
def cockroachdb_engine(cockroachdb_psycopg_url: str) -> Generator[Engine, None, None]:
    yield create_engine(cockroachdb_psycopg_url, poolclass=NullPool)


@pytest.fixture()
def mock_sync_engine() -> Generator[NonCallableMagicMock, None, None]:
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
            "oracle23ai_engine",
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
            "spanner_engine",
            marks=[
                pytest.mark.spanner,
                pytest.mark.integration,
                pytest.mark.xdist_group("spanner"),
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
    if "mock_sync_engine" in request.fixturenames or getattr(engine.dialect, "name", "") == "mock":
        session_mock = create_autospec(Session, instance=True)
        session_mock.bind = engine
        yield session_mock
    else:
        session_instance = sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            yield session_instance
        finally:
            session_instance.rollback()
            session_instance.close()


@pytest.fixture()
async def aiosqlite_engine(tmp_path: Path) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def asyncmy_engine(mysql_asyncmy_url: str) -> AsyncGenerator[AsyncEngine, None]:
    yield create_async_engine(mysql_asyncmy_url, poolclass=NullPool)


@pytest.fixture()
async def asyncpg_engine(postgres_asyncpg_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """AsyncPG engine fixture that ensures pgcrypto extension is created."""
    engine = create_async_engine(postgres_asyncpg_url, poolclass=NullPool)
    try:
        # Ensure pgcrypto extension is available
        async with engine.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            await conn.commit()  # Commit the extension creation
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def psycopg_async_engine(postgres_psycopg_url: str) -> AsyncGenerator[AsyncEngine, None]:
    yield create_async_engine(postgres_psycopg_url, poolclass=NullPool)


@pytest.fixture()
async def cockroachdb_async_engine(cockroachdb_asyncpg_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """Cockroach DB async engine instance for end-to-end testing using asyncpg.

    Args:
        cockroachdb_asyncpg_url: Connection URL provided by the cockroachdb_asyncpg_url fixture.

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(cockroachdb_asyncpg_url, poolclass=NullPool)


@pytest.fixture()
async def mssql_async_engine(mssql_aioodbc_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """MS SQL instance for end-to-end testing using aioodbc.

    Args:
        mssql_aioodbc_url: Connection URL provided by the mssql_aioodbc_url fixture.

    Returns:
        Async SQLAlchemy engine instance.
    """
    # Add MARS_Connection=yes needed for concurrent async tests
    url_to_use = mssql_aioodbc_url
    if "MARS_Connection=yes" not in url_to_use:
        separator = "&" if "?" in url_to_use else "?"
        url_to_use += f"{separator}MARS_Connection=yes"
    yield create_async_engine(url_to_use, poolclass=NullPool)


@pytest.fixture()
async def oracle18c_async_engine(oracle18c_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """Oracle 18c async instance for end-to-end testing.

    Args:
        oracle18c_url: Connection URL provided by the oracle18c_url fixture.

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(oracle18c_url, poolclass=NullPool)


@pytest.fixture()
async def oracle23ai_async_engine(oracle23ai_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """Oracle 23c async instance for end-to-end testing.

    Args:
        oracle23ai_url: Connection URL provided by the oracle23ai_url fixture.

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(oracle23ai_url, poolclass=NullPool)


@pytest.fixture()
async def mock_async_engine() -> AsyncGenerator[NonCallableMagicMock, None]:
    """Return a mocked AsyncEngine instance.

    Returns:
        Mocked Async SQLAlchemy engine instance.
    """
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
            "oracle23ai_async_engine",
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
    """Parametrized fixture to provide different async SQLAlchemy engines."""
    yield cast(AsyncEngine, request.getfixturevalue(request.param))


@pytest.fixture()
async def async_session(
    async_engine: AsyncEngine,
    request: FixtureRequest,
) -> AsyncGenerator[AsyncSession, None]:
    """Provides an async SQLAlchemy session for the parametrized async engine."""
    if "mock_async_engine" in request.fixturenames or getattr(async_engine.dialect, "name", "") == "mock":
        session_mock = create_autospec(AsyncSession, instance=True)
        session_mock.bind = async_engine
        yield session_mock
    else:
        session_instance = async_sessionmaker(bind=async_engine, expire_on_commit=False)()
        try:
            yield session_instance
        finally:
            await session_instance.rollback()
            await session_instance.close()

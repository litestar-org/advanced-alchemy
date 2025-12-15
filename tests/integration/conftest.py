from __future__ import annotations
# ruff: noqa: I001

import logging
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, cast
from unittest.mock import create_autospec, NonCallableMagicMock

import pytest
import pytest_asyncio
from google.cloud import spanner  # pyright: ignore
from pytest import FixtureRequest
from pytest_databases.docker.cockroachdb import CockroachDBService
from pytest_databases.docker.mssql import MSSQLService
from pytest_databases.docker.mysql import MySQLService
from pytest_databases.docker.oracle import OracleService
from pytest_databases.docker.postgres import PostgresService
from pytest_databases.docker.spanner import SpannerService
from sqlalchemy import Dialect, Engine, NullPool, create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

# Local test helpers and fixtures

# Import all fixtures from repository_fixtures
from tests.integration.repository_fixtures import *  # noqa: F403

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture(scope="session", autouse=True)
def configure_safe_logging(request: pytest.FixtureRequest) -> None:
    """Configure logging to prevent I/O errors during parallel test execution.

    Both Google Cloud Spanner and SQLAlchemy try to write logs during test execution with pytest-xdist,
    but worker processes have closed file streams, causing "I/O operation on closed file" errors.
    This fixture configures a safe logging handler to suppress these errors.
    """

    # Create a safe logging handler that won't fail on closed streams
    class SafeStreamHandler(logging.StreamHandler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                super().emit(record)
            except (ValueError, OSError):
                # Suppress I/O errors from closed streams during test execution
                pass

    # Configure loggers that can cause I/O issues during parallel test execution
    problematic_loggers = [
        # Google Cloud Spanner loggers
        "google.cloud.spanner_v1.database_sessions_manager",
        "google.cloud.spanner",
        "google.cloud",
        # SQLAlchemy engine loggers
        "sqlalchemy.engine.Engine",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        # Test helpers that log cleanup operations
        "tests.integration.helpers",
        # Pytest-xdist workers
        "xdist.remote",
        "xdist",
    ]

    for logger_name in problematic_loggers:
        logger = logging.getLogger(logger_name)
        # Remove existing handlers that might cause issues
        logger.handlers.clear()
        # Add our safe handler
        logger.addHandler(SafeStreamHandler())
        logger.setLevel(logging.WARNING)  # Reduce verbosity
        logger.propagate = False  # Prevent propagation to root logger

    # Add finalizer to ensure clean shutdown
    def cleanup() -> None:
        # Flush all handlers before pytest-xdist tears down
        for logger_name in problematic_loggers:
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers:
                try:
                    handler.flush()
                    handler.close()
                except Exception:
                    pass

    request.addfinalizer(cleanup)


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


@pytest.fixture(scope="session")
def duckdb_engine(
    tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> Generator[Engine, None, None]:
    # Workaround for DuckDB 1.4.0 unhashable DuckDBPyType
    # This is fixed in DuckDB 1.4.1 - can be removed once that's released
    # See: https://github.com/Mause/duckdb_engine/issues/1338
    try:
        import duckdb  # type: ignore[import-untyped]

        if hasattr(duckdb, "__version__") and duckdb.__version__.startswith("1.4.0"):
            from _duckdb import typing as duckdb_typing  # type: ignore[import-not-found]

            if hasattr(duckdb_typing, "DuckDBPyType"):
                # Test if the existing __hash__ method works
                try:
                    test_type = duckdb_typing.DuckDBPyType("INTEGER")
                    hash(test_type)
                except TypeError:
                    # Replace the broken __hash__ method with a working one
                    duckdb_typing.DuckDBPyType.__hash__ = lambda self: hash(str(self))
    except ImportError:
        pass

    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    tmp_path = tmp_path_factory.mktemp(f"duckdb_{worker_id}")
    engine = create_engine(f"duckdb:///{tmp_path}/test.duck.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def oracle18c_engine(oracle18c_url: str, oracle_18c_service: OracleService) -> Generator[Engine, None, None]:
    yield create_engine(oracle18c_url, poolclass=NullPool)


@pytest.fixture(scope="session")
def oracle23ai_engine(oracle23ai_url: str, oracle_23ai_service: OracleService) -> Generator[Engine, None, None]:
    yield create_engine(oracle23ai_url, poolclass=NullPool)


@pytest.fixture(scope="session")
def psycopg_engine(postgres_psycopg_url: str, postgres_service: PostgresService) -> Generator[Engine, None, None]:
    yield create_engine(postgres_psycopg_url, poolclass=NullPool)


@pytest.fixture(scope="session")
def mssql_engine(mssql_pyodbc_url: str, mssql_service: MSSQLService) -> Generator[Engine, None, None]:
    yield create_engine(mssql_pyodbc_url, poolclass=NullPool)


@pytest.fixture(scope="session")
def sqlite_engine(
    tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> Generator[Engine, None, None]:
    # Include worker ID in the database name to avoid conflicts
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    tmp_path = tmp_path_factory.mktemp(f"sqlite_{worker_id}")
    db_file = tmp_path / f"test_{worker_id}.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        poolclass=NullPool,
        connect_args={
            "timeout": 30,  # Wait up to 30 seconds for locks
            "check_same_thread": False,  # Allow usage from different threads
        },
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def spanner_engine(
    spanner_url: str, spanner_connection: spanner.Client, spanner_service: SpannerService
) -> Generator[Engine, None, None]:
    # Environment variables are still set by set_spanner_emulator in root conftest,
    # but we use the explicit URL fixture now for consistency.

    yield create_engine(spanner_url, poolclass=NullPool, connect_args={"client": spanner_connection})


@pytest.fixture(scope="session")
def cockroachdb_engine(
    cockroachdb_psycopg_url: str, cockroachdb_service: CockroachDBService
) -> Generator[Engine, None, None]:
    yield create_engine(cockroachdb_psycopg_url, poolclass=NullPool)


@pytest.fixture(scope="session")
def mock_sync_engine() -> Generator[NonCallableMagicMock, None, None]:
    mock = cast(NonCallableMagicMock, create_autospec(Engine, instance=True))
    mock.dialect = create_autospec(Dialect, instance=True)
    mock.dialect.name = "mock"
    mock.dialect.server_version_info = None
    yield mock


@pytest.fixture(
    scope="session",
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
def engine(request: FixtureRequest) -> Engine:
    return cast(Engine, request.getfixturevalue(request.param))


@pytest.fixture()
def session(engine: Engine, request: FixtureRequest) -> Generator[Session, None, None]:
    if "mock_sync_engine" in request.fixturenames or getattr(engine.dialect, "name", "") == "mock":
        session_mock = create_autospec(Session, instance=True)
        session_mock.bind = engine
        yield session_mock
    else:
        # Use improved transaction management to avoid savepoint issues
        # Spanner uses "spanner+spanner" as dialect name, CockroachDB uses "cockroachdb"
        dialect_name = engine.dialect.name
        supports_savepoints = not any(
            dialect_name.startswith(prefix) for prefix in ("sqlite", "duckdb", "spanner", "cockroachdb")
        )

        if supports_savepoints:
            # Use savepoint-based isolation for databases that support it
            connection = engine.connect()
            transaction = connection.begin()

            try:
                # Create session bound to this connection
                session_instance = Session(bind=connection, expire_on_commit=False)

                # Create savepoint for test isolation
                savepoint = connection.begin_nested()

                try:
                    yield session_instance
                finally:
                    # Cleanup order: session operations first, then transaction management
                    try:
                        session_instance.rollback()  # Rollback any pending changes
                    except Exception:
                        pass  # Ignore rollback errors
                    finally:
                        try:
                            session_instance.close()  # Close session first
                        except Exception:
                            pass

                    # Now handle savepoint cleanup
                    try:
                        if savepoint.is_active:
                            savepoint.rollback()
                    except Exception:
                        pass  # Ignore savepoint rollback errors

            finally:
                # Rollback the main transaction and close connection
                try:
                    if transaction.is_active:
                        transaction.rollback()
                except Exception:
                    pass
                finally:
                    try:
                        connection.close()
                    except Exception:
                        pass
        else:
            # For SQLite/DuckDB: use simple transaction-based isolation without savepoints
            connection = engine.connect()
            transaction = connection.begin()

            try:
                # Create session bound to this connection
                session_instance = Session(bind=connection, expire_on_commit=False)

                try:
                    yield session_instance
                finally:
                    # Cleanup: session first, then transaction
                    try:
                        session_instance.rollback()  # Rollback any changes
                    except Exception:
                        pass
                    finally:
                        try:
                            session_instance.close()
                        except Exception:
                            pass

            finally:
                # Always rollback transaction to clean up
                try:
                    if transaction.is_active:
                        transaction.rollback()
                except Exception:
                    pass
                finally:
                    try:
                        connection.close()
                    except Exception:
                        pass


# ---------------------------------------------------------------------------
# Global, per-test cleanup to ensure data isolation between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auto_clean_sync_db(request: FixtureRequest) -> Generator[None, None, None]:
    """Universal cleanup fixture for sync engine tests.

    Handles cleanup for all test types including:
    - Repository fixture tests (uuid/bigint session-based)
    - Filter tests (movie model)
    - Legacy tests with manual cleanup

    Only runs cleanup when appropriate and avoids conflicts.
    """
    yield

    # Skip cleanup for mock engines or if no sync engine available
    if "engine" not in request.fixturenames:
        return

    try:
        engine = request.getfixturevalue("engine")
    except Exception:
        return

    # Skip cleanup for mock engines
    if getattr(engine.dialect, "name", "") == "mock":
        return

    from tests.integration import helpers as test_helpers

    try:
        # 1. Handle repository fixture tests - these use transaction-based cleanup
        if any(
            fixture in request.fixturenames
            for fixture in ["test_session_sync", "uuid_test_session_sync", "bigint_test_session_sync"]
        ):
            # These fixtures handle their own transaction-based cleanup
            # No additional cleanup needed
            return

        # 2. Handle filter tests with movie models
        if "movie_model_sync" in request.fixturenames:
            try:
                movie_model = request.getfixturevalue("movie_model_sync")
                test_helpers.clean_tables(engine, movie_model.metadata)
            except Exception as e:
                # Log but don't fail on cleanup errors
                import logging

                logging.getLogger(__name__).warning(f"Movie model cleanup failed: {e}")
            return

        # 3. Handle legacy tests with repository models
        base_model = None
        if "uuid_models" in request.fixturenames:
            try:
                uuid_models = request.getfixturevalue("uuid_models")
                base_model = uuid_models["base"]
            except Exception:
                pass
        elif "bigint_models" in request.fixturenames:
            try:
                bigint_models = request.getfixturevalue("bigint_models")
                base_model = bigint_models["base"]
            except Exception:
                pass

        if base_model:
            test_helpers.clean_tables(engine, base_model.metadata)

    except Exception as e:
        # Log but don't fail the test on cleanup errors
        import logging

        logging.getLogger(__name__).warning(f"Sync cleanup failed: {e}")


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def _auto_clean_async_db(request: FixtureRequest) -> AsyncGenerator[None, None]:
    """Universal cleanup fixture for async engine tests.

    Handles cleanup for all async test types including:
    - Repository fixture tests (uuid/bigint session-based)
    - Filter tests (movie model)
    - Legacy tests with manual cleanup

    Only runs cleanup when appropriate and avoids conflicts.
    """
    yield

    # Skip cleanup if no async engine available
    if "async_engine" not in request.fixturenames:
        return

    try:
        async_engine = request.getfixturevalue("async_engine")
    except Exception:
        # Fixture might be torn down already
        return

    # Skip cleanup for mock engines
    if getattr(async_engine.dialect, "name", "") == "mock":
        return

    from tests.integration import helpers as test_helpers

    try:
        # 1. Handle repository fixture tests - these use transaction-based cleanup
        if any(
            fixture in request.fixturenames
            for fixture in ["test_session_async", "uuid_test_session_async", "bigint_test_session_async"]
        ):
            # These fixtures handle their own transaction-based cleanup
            # No additional cleanup needed
            return

        # 2. Handle filter tests with movie models
        if "movie_model_async" in request.fixturenames:
            try:
                movie_model = request.getfixturevalue("cached_movie_model")
                await test_helpers.async_clean_tables(async_engine, movie_model.metadata)
            except Exception as e:
                # Log but don't fail on cleanup errors
                import logging

                logging.getLogger(__name__).warning(f"Async movie model cleanup failed: {e}")
            return

        # 3. Handle legacy tests with repository models
        base_model = None
        if "uuid_models" in request.fixturenames:
            try:
                uuid_models = request.getfixturevalue("uuid_models")
                base_model = uuid_models["base"]
            except Exception:
                pass
        elif "bigint_models" in request.fixturenames:
            try:
                bigint_models = request.getfixturevalue("bigint_models")
                base_model = bigint_models["base"]
            except Exception:
                pass

        if base_model:
            await test_helpers.async_clean_tables(async_engine, base_model.metadata)

    except Exception as e:
        # Log but don't fail the test on cleanup errors
        import logging

        logging.getLogger(__name__).warning(f"Async cleanup failed: {e}")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def aiosqlite_engine(
    tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> AsyncGenerator[AsyncEngine, None]:
    # Include worker ID in the database name to avoid conflicts
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    tmp_path = tmp_path_factory.mktemp(f"aiosqlite_{worker_id}")
    db_file = tmp_path / f"test_{worker_id}.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=NullPool,
        connect_args={
            "timeout": 30,  # Wait up to 30 seconds for locks
            "check_same_thread": False,  # Allow usage from different threads
        },
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def asyncmy_engine(mysql_asyncmy_url: str, mysql_service: MySQLService) -> AsyncGenerator[AsyncEngine, None]:
    yield create_async_engine(mysql_asyncmy_url, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def asyncpg_engine(
    postgres_asyncpg_url: str, postgres_service: PostgresService
) -> AsyncGenerator[AsyncEngine, None]:
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


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def psycopg_async_engine(
    postgres_psycopg_url: str, postgres_service: PostgresService
) -> AsyncGenerator[AsyncEngine, None]:
    yield create_async_engine(postgres_psycopg_url, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def cockroachdb_async_engine(
    cockroachdb_asyncpg_url: str, cockroachdb_service: CockroachDBService
) -> AsyncGenerator[AsyncEngine, None]:
    """Cockroach DB async engine instance for end-to-end testing using asyncpg.

    Args:
        cockroachdb_asyncpg_url: Connection URL provided by the cockroachdb_asyncpg_url fixture.

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(cockroachdb_asyncpg_url, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mssql_async_engine(mssql_aioodbc_url: str, mssql_service: MSSQLService) -> AsyncGenerator[AsyncEngine, None]:
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


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def oracle18c_async_engine(
    oracle18c_url: str, oracle_18c_service: OracleService
) -> AsyncGenerator[AsyncEngine, None]:
    """Oracle 18c async instance for end-to-end testing.

    Args:
        oracle18c_url: Connection URL provided by the oracle18c_url fixture.

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(oracle18c_url, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def oracle23ai_async_engine(
    oracle23ai_url: str, oracle_23ai_service: OracleService
) -> AsyncGenerator[AsyncEngine, None]:
    """Oracle 23c async instance for end-to-end testing.

    Args:
        oracle23ai_url: Connection URL provided by the oracle23ai_url fixture.

    Returns:
        Async SQLAlchemy engine instance.
    """
    yield create_async_engine(oracle23ai_url, poolclass=NullPool)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mock_async_engine() -> AsyncGenerator[NonCallableMagicMock, None]:
    """Return a mocked AsyncEngine instance.

    Returns:
        Mocked Async SQLAlchemy engine instance.
    """
    mock = cast(NonCallableMagicMock, create_autospec(AsyncEngine, instance=True))
    mock.dialect = create_autospec(Dialect, instance=True)
    mock.dialect.name = "mock"
    mock.dialect.server_version_info = None
    yield mock


@pytest.fixture(
    scope="session",
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
def async_engine(request: FixtureRequest) -> AsyncEngine:
    """Parametrized fixture to provide different async SQLAlchemy engines."""
    return cast(AsyncEngine, request.getfixturevalue(request.param))


@pytest_asyncio.fixture(loop_scope="function")
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
        # Use improved transaction management to avoid savepoint issues
        # Spanner uses "spanner+spanner" as dialect name, CockroachDB uses "cockroachdb"
        dialect_name = async_engine.dialect.name
        supports_savepoints = not any(
            dialect_name.startswith(prefix) for prefix in ("sqlite", "duckdb", "spanner", "cockroachdb")
        )

        if supports_savepoints:
            # Use savepoint-based isolation for databases that support it
            connection = await async_engine.connect()
            transaction = await connection.begin()

            try:
                # Create session bound to this connection
                session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
                session_instance = session_factory()

                # Create savepoint for test isolation
                savepoint = await connection.begin_nested()

                try:
                    yield session_instance
                finally:
                    # Cleanup order: session operations first, then transaction management
                    try:
                        await session_instance.rollback()  # Rollback any pending changes
                    except Exception:
                        pass  # Ignore rollback errors
                    finally:
                        try:
                            await session_instance.close()  # Close session first
                        except Exception:
                            pass

                    # Now handle savepoint cleanup
                    try:
                        if savepoint.is_active:
                            await savepoint.rollback()
                    except Exception:
                        pass  # Ignore savepoint rollback errors

            finally:
                # Rollback the main transaction and close connection
                try:
                    if transaction.is_active:
                        await transaction.rollback()
                except Exception:
                    pass
                finally:
                    try:
                        await connection.close()
                    except Exception:
                        pass
        else:
            # For SQLite/DuckDB: use simple transaction-based isolation without savepoints
            connection = await async_engine.connect()
            transaction = await connection.begin()

            try:
                # Create session bound to this connection
                session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
                session_instance = session_factory()

                try:
                    yield session_instance
                finally:
                    # Cleanup: session first, then transaction
                    try:
                        await session_instance.rollback()  # Rollback any changes
                    except Exception:
                        pass
                    finally:
                        try:
                            await session_instance.close()
                        except Exception:
                            pass

            finally:
                # Always rollback transaction to clean up
                try:
                    if transaction.is_active:
                        await transaction.rollback()
                except Exception:
                    pass
                finally:
                    try:
                        await connection.close()
                    except Exception:
                        pass


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip relationship filter tests for Spanner and Oracle engines.

    These engines have issues with the UUID test models:
    - Spanner: Doesn't support direct UNIQUE constraints (used by Tag model)
    - Oracle: Has schema isolation issues with xdist groups
    """
    skip_spanner = pytest.mark.skip(reason="Spanner doesn't support direct UNIQUE constraints")
    skip_oracle = pytest.mark.skip(reason="Oracle has schema isolation issues with relationship filter tests")

    for item in items:
        # Only process items from test_relationship_filters.py
        if "test_relationship_filters" not in item.nodeid:
            continue

        # Check for Spanner engine
        if "spanner" in item.nodeid.lower():
            item.add_marker(skip_spanner)

        # Check for Oracle engine
        if "oracle" in item.nodeid.lower():
            item.add_marker(skip_oracle)

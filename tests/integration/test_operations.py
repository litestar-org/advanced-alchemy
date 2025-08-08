# pyright: ignore[reportMissingTypeArgument,reportOperatorIssue,reportAttributeAccessIssue]
"""Integration tests for advanced_alchemy.operations module.

These tests run against actual database instances to verify that the upsert
and MERGE operations work correctly across different database backends.
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any, Optional, cast

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from advanced_alchemy.operations import OnConflictUpsert
from tests.integration.helpers import async_clean_tables, clean_tables, get_worker_id

if TYPE_CHECKING:
    from pytest import FixtureRequest
    from sqlalchemy import Engine

pytestmark = [
    pytest.mark.integration,
]


# Module-level cache for test table
_test_table_cache: dict[str, Table] = {}


@pytest.fixture(scope="session")
def cached_test_table(request: FixtureRequest) -> Table:
    """Create test table once per session/worker."""
    worker_id = get_worker_id(request)
    cache_key = f"operation_test_{worker_id}"

    if cache_key not in _test_table_cache:
        metadata = MetaData()
        table = Table(
            f"operation_test_table_{worker_id}",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=False),
            Column("key", String(50), nullable=False, index=True),
            Column("namespace", String(50), nullable=False, index=True),
            Column("value", String(255)),
            Column("created_at", String(50)),
            # Note: For Spanner compatibility, we should use unique indexes instead
            # but for testing purposes, we'll skip Spanner tests that require UniqueConstraint
            UniqueConstraint("key", "namespace", name=f"uq_key_namespace_{worker_id}"),
        )
        _test_table_cache[cache_key] = table

    return _test_table_cache[cache_key]


@pytest.fixture
def test_table_sync(
    cached_test_table: Table,
    request: FixtureRequest,
) -> Generator[Table, None, None]:
    """Setup test table for sync engines with fast cleanup."""
    # Get the sync engine - either from any_engine or engine fixture
    if "any_engine" in request.fixturenames:
        engine = request.getfixturevalue("any_engine")
        if isinstance(engine, AsyncEngine):
            pytest.skip("Async engine provided to sync fixture")
    else:
        engine = request.getfixturevalue("engine")

    # Skip for mock and spanner engines (Spanner doesn't support UniqueConstraint)
    dialect_name = getattr(engine.dialect, "name", "")
    if "spanner" in dialect_name:
        # Skip entire test for Spanner - it doesn't support UniqueConstraint
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")
    elif dialect_name != "mock":
        # Create table once per engine type
        cached_test_table.create(engine, checkfirst=True)

    yield cached_test_table

    # Fast data-only cleanup between tests
    if dialect_name not in {"mock", "spanner+spanner"}:
        with engine.begin() as conn:
            conn.execute(cached_test_table.delete())
            conn.commit()

    # Drop table at session end (handled by teardown)


@pytest.fixture
async def test_table_async(
    cached_test_table: Table,
    request: FixtureRequest,
) -> AsyncGenerator[Table, None]:
    """Setup test table for async engines with fast cleanup."""
    # Get the async engine - either from any_engine or async_engine fixture
    if "any_engine" in request.fixturenames:
        engine = request.getfixturevalue("any_engine")
        if not isinstance(engine, AsyncEngine):
            pytest.skip("Sync engine provided to async fixture")
        async_engine = engine
    else:
        async_engine = request.getfixturevalue("async_engine")

    # Skip for mock and spanner engines (Spanner doesn't support UniqueConstraint)
    dialect_name = getattr(async_engine.dialect, "name", "")
    if "spanner" in dialect_name:
        # Skip table creation for Spanner - it doesn't support UniqueConstraint
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")
    elif dialect_name != "mock":
        # Create table once per engine type
        async with async_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: cached_test_table.create(sync_conn, checkfirst=True))

    yield cached_test_table

    # Fast data-only cleanup between tests
    if dialect_name not in {"mock"} and "spanner" not in dialect_name:
        async with async_engine.begin() as conn:
            await conn.execute(cached_test_table.delete())
            await conn.commit()

    # Drop table at session end (handled by teardown)


@pytest.fixture
def test_table(
    request: FixtureRequest,
) -> Table:
    """Unified test table fixture that works with any engine."""
    # Check if we have any_engine fixture
    if "any_engine" in request.fixturenames:
        engine = request.getfixturevalue("any_engine")
        if isinstance(engine, AsyncEngine):
            return cast(Table, request.getfixturevalue("test_table_async"))
        return cast(Table, request.getfixturevalue("test_table_sync"))
    # Check which fixtures are available in the request
    if "test_table_sync" in request.fixturenames:
        return cast(Table, request.getfixturevalue("test_table_sync"))
    if "test_table_async" in request.fixturenames:
        return cast(Table, request.getfixturevalue("test_table_async"))
    # Fallback to cached table for tests that don't use engines
    return cast(Table, request.getfixturevalue("cached_test_table"))


# Module-level cache for store model
_store_model_cache: dict[str, type] = {}


@pytest.fixture(scope="session")
def cached_store_model(request: FixtureRequest) -> type[DeclarativeBase]:
    """Create store model once per session/worker."""
    from advanced_alchemy.base import BigIntBase, UUIDv7Base

    worker_id = get_worker_id(request)
    cache_key = f"store_model_{worker_id}"

    if cache_key not in _store_model_cache:
        # Check if we're using Spanner - it's in the worker_id for parallel tests
        is_spanner = True if "spanner" in worker_id.lower() else False

        # Define distinct local classes to avoid pyright redefinition warnings, then select one
        class _TestStoreModelUUID(UUIDv7Base):  # pyright: ignore[reportPrivateUsage]
            __tablename__ = f"test_store_{worker_id}"

            key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
            namespace: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
            value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
            expires_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

            # Spanner doesn't support UniqueConstraint, use indexes instead
            __table_args__ = ()

        class _TestStoreModelBigInt(BigIntBase):
            __tablename__ = f"test_store_{worker_id}"

            key: Mapped[str] = mapped_column(String(50), nullable=False)
            namespace: Mapped[str] = mapped_column(String(50), nullable=False)
            value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
            expires_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

            __table_args__ = (UniqueConstraint("key", "namespace", name=f"uq_store_key_ns_{worker_id}"),)

        chosen: type[DeclarativeBase] = cast(
            type[DeclarativeBase], _TestStoreModelUUID if is_spanner else _TestStoreModelBigInt
        )
        _store_model_cache[cache_key] = chosen

    return _store_model_cache[cache_key]


@pytest.fixture
def store_model_sync(
    cached_store_model: type[DeclarativeBase],
    request: FixtureRequest,
) -> Generator[type[DeclarativeBase], None, None]:
    """Setup store model for sync engines with fast cleanup."""
    # Get the sync engine - either from any_engine or engine fixture
    if "any_engine" in request.fixturenames:
        engine = request.getfixturevalue("any_engine")
        if isinstance(engine, AsyncEngine):
            pytest.skip("Async engine provided to sync fixture")
    else:
        engine = request.getfixturevalue("engine")

    # Skip for mock and spanner engines (Spanner doesn't support UniqueConstraint)
    dialect_name = getattr(engine.dialect, "name", "")
    if "spanner" in dialect_name:
        # Skip table creation for Spanner - it doesn't support UniqueConstraint
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")
    elif dialect_name != "mock":
        # Create table once per engine type
        cached_store_model.metadata.create_all(engine, checkfirst=True)

    yield cached_store_model

    # Fast data-only cleanup between tests
    if dialect_name not in {"mock"} and "spanner" not in dialect_name:
        clean_tables(engine, cached_store_model.metadata)

    # Drop table at session end (handled by teardown)


@pytest.fixture
async def store_model_async(
    cached_store_model: type[DeclarativeBase],
    request: FixtureRequest,
) -> AsyncGenerator[type[DeclarativeBase], None]:
    """Setup store model for async engines with fast cleanup."""
    # Get the async engine - either from any_engine or async_engine fixture
    if "any_engine" in request.fixturenames:
        engine = request.getfixturevalue("any_engine")
        if not isinstance(engine, AsyncEngine):
            pytest.skip("Sync engine provided to async fixture")
        async_engine = engine
    else:
        async_engine = request.getfixturevalue("async_engine")

    # Skip for mock and spanner engines (Spanner doesn't support UniqueConstraint)
    dialect_name = getattr(async_engine.dialect, "name", "")
    if "spanner" in dialect_name:
        # Skip table creation for Spanner - it doesn't support UniqueConstraint
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")
    elif dialect_name != "mock":
        # Create table once per engine type
        async with async_engine.begin() as conn:
            await conn.run_sync(cached_store_model.metadata.create_all)

    yield cached_store_model

    # Fast data-only cleanup between tests
    if dialect_name not in {"mock"} and "spanner" not in dialect_name:
        await async_clean_tables(async_engine, cached_store_model.metadata)

    # Drop table at session end (handled by teardown)


@pytest.fixture
def store_model(
    request: FixtureRequest,
) -> type[DeclarativeBase]:
    """Unified store model fixture that works with any engine."""
    # Check if we have any_engine fixture
    if "any_engine" in request.fixturenames:
        engine = request.getfixturevalue("any_engine")
        if isinstance(engine, AsyncEngine):
            return cast(type[DeclarativeBase], request.getfixturevalue("store_model_async"))
        return cast(type[DeclarativeBase], request.getfixturevalue("store_model_sync"))
    # Check which fixtures are available in the request
    if "store_model_sync" in request.fixturenames:
        return cast(type[DeclarativeBase], request.getfixturevalue("store_model_sync"))
    if "store_model_async" in request.fixturenames:
        return cast(type[DeclarativeBase], request.getfixturevalue("store_model_async"))
    # Fallback to cached model for tests that don't use engines
    return cast(type[DeclarativeBase], request.getfixturevalue("cached_store_model"))


@pytest.fixture
def upsert_values() -> dict[str, Any]:
    """Sample values for upsert operations."""
    return {
        "id": 1,
        "key": "test_key",
        "namespace": "test_ns",
        "value": "test_value",
        "created_at": datetime.datetime.now().isoformat(),
    }


@pytest.fixture
def updated_values() -> dict[str, Any]:
    """Updated values for upsert operations."""
    return {
        "id": 1,
        "key": "test_key",
        "namespace": "test_ns",
        "value": "updated_value",
        "created_at": datetime.datetime.now().isoformat(),
    }


@pytest.fixture(
    params=[
        # Sync engines
        pytest.param(
            "sqlite_engine",
            marks=[pytest.mark.sqlite, pytest.mark.integration, pytest.mark.xdist_group("sqlite")],
        ),
        pytest.param(
            "duckdb_engine",
            marks=[pytest.mark.duckdb, pytest.mark.integration, pytest.mark.xdist_group("duckdb")],
        ),
        pytest.param(
            "psycopg_engine",
            marks=[pytest.mark.psycopg_sync, pytest.mark.integration, pytest.mark.xdist_group("postgres")],
        ),
        pytest.param(
            "mssql_engine",
            marks=[pytest.mark.mssql_sync, pytest.mark.integration, pytest.mark.xdist_group("mssql")],
        ),
        pytest.param(
            "oracle18c_engine",
            marks=[pytest.mark.oracledb_sync, pytest.mark.integration, pytest.mark.xdist_group("oracle18")],
        ),
        pytest.param(
            "oracle23ai_engine",
            marks=[pytest.mark.oracledb_sync, pytest.mark.integration, pytest.mark.xdist_group("oracle23")],
        ),
        pytest.param(
            "cockroachdb_engine",
            marks=[pytest.mark.cockroachdb_sync, pytest.mark.integration, pytest.mark.xdist_group("cockroachdb")],
        ),
        pytest.param(
            "spanner_engine",
            marks=[pytest.mark.spanner, pytest.mark.integration, pytest.mark.xdist_group("spanner")],
        ),
        pytest.param(
            "mock_sync_engine",
            marks=[pytest.mark.mock_sync, pytest.mark.integration, pytest.mark.xdist_group("mock")],
        ),
        # Async engines
        pytest.param(
            "aiosqlite_engine",
            marks=[pytest.mark.aiosqlite, pytest.mark.integration, pytest.mark.xdist_group("sqlite")],
        ),
        pytest.param(
            "asyncmy_engine",
            marks=[pytest.mark.asyncmy, pytest.mark.integration, pytest.mark.xdist_group("mysql")],
        ),
        pytest.param(
            "asyncpg_engine",
            marks=[pytest.mark.asyncpg, pytest.mark.integration, pytest.mark.xdist_group("postgres")],
        ),
        pytest.param(
            "psycopg_async_engine",
            marks=[pytest.mark.psycopg_async, pytest.mark.integration, pytest.mark.xdist_group("postgres")],
        ),
        pytest.param(
            "cockroachdb_async_engine",
            marks=[pytest.mark.cockroachdb_async, pytest.mark.integration, pytest.mark.xdist_group("cockroachdb")],
        ),
        pytest.param(
            "mssql_async_engine",
            marks=[pytest.mark.mssql_async, pytest.mark.integration, pytest.mark.xdist_group("mssql")],
        ),
        pytest.param(
            "oracle18c_async_engine",
            marks=[pytest.mark.oracledb_async, pytest.mark.integration, pytest.mark.xdist_group("oracle18")],
        ),
        pytest.param(
            "oracle23ai_async_engine",
            marks=[pytest.mark.oracledb_async, pytest.mark.integration, pytest.mark.xdist_group("oracle23")],
        ),
        pytest.param(
            "mock_async_engine",
            marks=[pytest.mark.mock_async, pytest.mark.integration, pytest.mark.xdist_group("mock")],
        ),
    ]
)
def any_engine(request: FixtureRequest) -> Engine | AsyncEngine:
    """Return any available engine for testing."""
    return cast("Engine | AsyncEngine", request.getfixturevalue(request.param))


# Session-level teardown to ensure tables are dropped
@pytest.fixture(scope="session", autouse=True)
def cleanup_operations_tables(request: FixtureRequest) -> Generator[None, None, None]:
    """Ensure all operation test tables are dropped at session end."""
    yield

    # Clean up all cached tables at session end
    for cache_key, table in _test_table_cache.items():
        # Drop table from all engines if they exist
        # This is handled by individual fixtures, but we ensure cleanup here
        pass

    for cache_key, model in _store_model_cache.items():
        # Drop model tables from all engines if they exist
        # This is handled by individual fixtures, but we ensure cleanup here
        pass


async def test_supports_native_upsert_all_dialects(any_engine: Engine | AsyncEngine) -> None:
    """Test dialect support detection against actual engines."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name
    expected_support = dialect_name in {"postgresql", "cockroachdb", "sqlite", "mysql", "mariadb", "duckdb"}

    actual_support = OnConflictUpsert.supports_native_upsert(dialect_name)
    assert actual_support == expected_support, f"Dialect '{dialect_name}' support mismatch"


async def test_create_upsert_with_supported_dialects(
    any_engine: Engine | AsyncEngine,
    test_table: Table,
    upsert_values: dict[str, Any],
) -> None:
    """Test upsert creation against supported database dialects."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    if "spanner" in dialect_name:
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")

    if not OnConflictUpsert.supports_native_upsert(dialect_name):
        pytest.skip(f"Dialect '{dialect_name}' does not support native upsert")

    # Tables are already created by fixtures, no need to create here
    conflict_columns = ["key", "namespace"]
    update_columns = ["value", "created_at"]

    # Create upsert statement
    upsert_stmt = OnConflictUpsert.create_upsert(
        table=test_table,
        values=upsert_values,
        conflict_columns=conflict_columns,
        update_columns=update_columns,
        dialect_name=dialect_name,
    )

    # Verify the statement was created
    assert upsert_stmt is not None

    # Execute the upsert
    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.execute(upsert_stmt)
            await conn.commit()
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            conn.execute(upsert_stmt)
            conn.commit()


async def test_upsert_insert_then_update_cycle(
    any_engine: Engine | AsyncEngine,
    test_table: Table,
    upsert_values: dict[str, Any],
    updated_values: dict[str, Any],
) -> None:
    """Test that upsert properly inserts and then updates on conflict."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    if "spanner" in dialect_name:
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")

    if not OnConflictUpsert.supports_native_upsert(dialect_name):
        pytest.skip(f"Dialect '{dialect_name}' does not support native upsert")

    # Tables are already created by fixtures
    conflict_columns = ["key", "namespace"]
    update_columns = ["value", "created_at"]

    # First upsert - should insert
    upsert_stmt = OnConflictUpsert.create_upsert(
        table=test_table,
        values=upsert_values,
        conflict_columns=conflict_columns,
        update_columns=update_columns,
        dialect_name=dialect_name,
    )

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.execute(upsert_stmt)
            await conn.commit()

            # Verify insert
            result = await conn.execute(
                select(test_table.c.value).where(
                    (test_table.c.key == upsert_values["key"]) & (test_table.c.namespace == upsert_values["namespace"])
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "test_value"
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            conn.execute(upsert_stmt)
            conn.commit()

            # Verify insert
            result = conn.execute(
                select(test_table.c.value).where(
                    (test_table.c.key == upsert_values["key"]) & (test_table.c.namespace == upsert_values["namespace"])
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "test_value"

    # Second upsert - should update
    upsert_stmt2 = OnConflictUpsert.create_upsert(
        table=test_table,
        values=updated_values,
        conflict_columns=conflict_columns,
        update_columns=update_columns,
        dialect_name=dialect_name,
    )

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.execute(upsert_stmt2)
            await conn.commit()

            # Verify update
            result = await conn.execute(
                select(test_table.c.value).where(
                    (test_table.c.key == updated_values["key"])
                    & (test_table.c.namespace == updated_values["namespace"])
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "updated_value"

            # Verify only one row exists
            count_result = await conn.execute(select(test_table).where(test_table.c.key == "test_key"))
            rows = count_result.fetchall()
            assert len(rows) == 1
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            conn.execute(upsert_stmt2)
            conn.commit()

            # Verify update
            result = conn.execute(
                select(test_table.c.value).where(
                    (test_table.c.key == updated_values["key"])
                    & (test_table.c.namespace == updated_values["namespace"])
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "updated_value"

            # Verify only one row exists
            count_result = conn.execute(select(test_table).where(test_table.c.key == "test_key"))
            rows = count_result.fetchall()
            assert len(rows) == 1


async def test_batch_upsert_operations(any_engine: Engine | AsyncEngine, test_table: Table) -> None:
    """Test batch upsert operations with multiple rows."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    if "spanner" in dialect_name:
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")

    if not OnConflictUpsert.supports_native_upsert(dialect_name):
        pytest.skip(f"Dialect '{dialect_name}' does not support native upsert")

    # Tables are already created by fixtures
    batch_values = [
        {"id": 1, "key": "key1", "namespace": "ns1", "value": "value1", "created_at": "2024-01-01"},
        {"id": 2, "key": "key2", "namespace": "ns1", "value": "value2", "created_at": "2024-01-02"},
        {"id": 3, "key": "key3", "namespace": "ns2", "value": "value3", "created_at": "2024-01-03"},
    ]

    conflict_columns = ["key", "namespace"]
    update_columns = ["value", "created_at"]

    # Create batch upsert
    upsert_stmt = OnConflictUpsert.create_upsert(
        table=test_table,
        values=batch_values,  # type: ignore[arg-type]
        conflict_columns=conflict_columns,
        update_columns=update_columns,
        dialect_name=dialect_name,
    )

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.execute(upsert_stmt)
            await conn.commit()

            # Verify all rows inserted
            result = await conn.execute(select(test_table).order_by(test_table.c.id))
            rows = result.fetchall()
            assert len(rows) == 3
            assert rows[0].value == "value1"
            assert rows[1].value == "value2"
            assert rows[2].value == "value3"
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            conn.execute(upsert_stmt)
            conn.commit()

            # Verify all rows inserted
            result = conn.execute(select(test_table).order_by(test_table.c.id))
            rows = result.fetchall()
            assert len(rows) == 3
            assert rows[0].value == "value1"
            assert rows[1].value == "value2"
            assert rows[2].value == "value3"

    # Update batch with conflicts
    updated_batch = [
        {"id": 1, "key": "key1", "namespace": "ns1", "value": "updated1", "created_at": "2024-02-01"},
        {"id": 4, "key": "key4", "namespace": "ns2", "value": "value4", "created_at": "2024-01-04"},
    ]

    upsert_stmt2 = OnConflictUpsert.create_upsert(
        table=test_table,
        values=updated_batch,  # type: ignore[arg-type]
        conflict_columns=conflict_columns,
        update_columns=update_columns,
        dialect_name=dialect_name,
    )

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.execute(upsert_stmt2)
            await conn.commit()

            # Verify mixed insert/update
            result = await conn.execute(select(test_table).order_by(test_table.c.id))
            rows = result.fetchall()
            assert len(rows) == 4
            assert rows[0].value == "updated1"  # Updated
            assert rows[3].value == "value4"  # Inserted
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            conn.execute(upsert_stmt2)
            conn.commit()

            # Verify mixed insert/update
            result = conn.execute(select(test_table).order_by(test_table.c.id))
            rows = result.fetchall()
            assert len(rows) == 4
            assert rows[0].value == "updated1"  # Updated
            assert rows[3].value == "value4"  # Inserted


async def test_merge_statement_with_oracle_postgres(
    any_engine: Engine | AsyncEngine,
    test_table: Table,
    upsert_values: dict[str, Any],
    updated_values: dict[str, Any],
) -> None:
    """Test MERGE statement for Oracle and PostgreSQL 15+."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    # Only test on supported dialects (CockroachDB doesn't support MERGE)
    if dialect_name not in {"oracle", "postgresql"}:
        pytest.skip(f"MERGE not tested for dialect '{dialect_name}'")

    # PostgreSQL needs version 15+ for MERGE
    if dialect_name == "postgresql":
        server_version_info = getattr(any_engine.dialect, "server_version_info", (0,))
        try:
            major = int(server_version_info[0]) if isinstance(server_version_info, tuple) and server_version_info else 0
        except Exception:
            major = 0
        if major < 15:
            pytest.skip("PostgreSQL MERGE requires version 15+")

    # Tables are already created by fixtures
    # First insert a record
    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.execute(test_table.insert(), upsert_values)
            await conn.commit()
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            conn.execute(test_table.insert(), upsert_values)
            conn.commit()

    # Create MERGE statement for update
    merge_stmt, additional_params = OnConflictUpsert.create_merge_upsert(
        table=test_table,
        values=updated_values,
        conflict_columns=["key", "namespace"],
        update_columns=["value", "created_at"],
        dialect_name=dialect_name,
    )

    # Execute MERGE
    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            if dialect_name in {"oracle", "mssql"}:
                merged_params = {**updated_values, **additional_params}
                await conn.execute(merge_stmt, merged_params)
            elif dialect_name in {"postgresql", "cockroachdb"}:
                # PostgreSQL MERGE only needs source parameters (src references are used in UPDATE/INSERT)
                pg_params = {f"src_{k}": v for k, v in updated_values.items()}
                await conn.execute(merge_stmt, pg_params)
            else:
                await conn.execute(merge_stmt, updated_values)
            await conn.commit()

            # Verify update
            result = await conn.execute(
                select(test_table.c.value).where(
                    (test_table.c.key == updated_values["key"])
                    & (test_table.c.namespace == updated_values["namespace"])
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "updated_value"
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            if dialect_name in {"oracle", "mssql"}:
                merged_params = {**updated_values, **additional_params}
                conn.execute(merge_stmt, merged_params)
            elif dialect_name in {"postgresql", "cockroachdb"}:
                # PostgreSQL needs unique parameter names for each clause
                pg_params = {
                    **{f"src_{k}": v for k, v in updated_values.items()},  # Source VALUES clause
                    **{
                        f"upd_{k}": v for k, v in updated_values.items() if k in ["value", "created_at"]
                    },  # UPDATE clause
                    **{f"ins_{k}": v for k, v in updated_values.items()},  # INSERT clause
                }
                conn.execute(merge_stmt, pg_params)
            else:
                conn.execute(merge_stmt, updated_values)
            conn.commit()

            # Verify update
            result = conn.execute(
                select(test_table.c.value).where(
                    (test_table.c.key == updated_values["key"])
                    & (test_table.c.namespace == updated_values["namespace"])
                )
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "updated_value"

    # Test MERGE with new record (insert)
    new_values = {
        "id": 2,
        "key": "new_key",
        "namespace": "new_ns",
        "value": "new_value",
        "created_at": datetime.datetime.now().isoformat(),
    }

    merge_stmt2, additional_params2 = OnConflictUpsert.create_merge_upsert(
        table=test_table,
        values=new_values,
        conflict_columns=["key", "namespace"],
        update_columns=["value", "created_at"],
        dialect_name=dialect_name,
    )

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            if dialect_name in {"oracle", "mssql"}:
                merged_params2 = {**new_values, **additional_params2}
                await conn.execute(merge_stmt2, merged_params2)
            elif dialect_name in {"postgresql", "cockroachdb"}:
                # PostgreSQL MERGE only needs source parameters (src references are used in UPDATE/INSERT)
                pg_params2 = {f"src_{k}": v for k, v in new_values.items()}
                await conn.execute(merge_stmt2, pg_params2)
            else:
                await conn.execute(merge_stmt2, new_values)
            await conn.commit()

            # Verify insert
            result = await conn.execute(select(test_table).where(test_table.c.key == "new_key"))
            row = result.fetchone()
            assert row is not None
            assert row.value == "new_value"
    else:
        with any_engine.connect() as conn:  # type: ignore[attr-defined]
            if dialect_name in {"oracle", "mssql"}:
                merged_params2 = {**new_values, **additional_params2}
                conn.execute(merge_stmt2, merged_params2)
            elif dialect_name in {"postgresql", "cockroachdb"}:
                # PostgreSQL needs unique parameter names for each clause
                pg_params2 = {
                    **{f"src_{k}": v for k, v in new_values.items()},  # Source VALUES clause
                    **{f"upd_{k}": v for k, v in new_values.items() if k in ["value", "created_at"]},  # UPDATE clause
                    **{f"ins_{k}": v for k, v in new_values.items()},  # INSERT clause
                }
                conn.execute(merge_stmt2, pg_params2)
            else:
                conn.execute(merge_stmt2, new_values)
            conn.commit()

            # Verify insert
            result = conn.execute(select(test_table).where(test_table.c.key == "new_key"))
            row = result.fetchone()
            assert row is not None
            assert row.value == "new_value"


async def test_merge_compilation_oracle_postgres(any_engine: Engine | AsyncEngine) -> None:
    """Test MERGE statement compilation for different dialects."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test compilation")

    dialect_name = any_engine.dialect.name

    # Only test on supported dialects (CockroachDB doesn't support MERGE)
    if dialect_name not in {"oracle", "postgresql"}:
        pytest.skip(f"MERGE compilation not tested for dialect '{dialect_name}'")

    # PostgreSQL needs version 15+ for MERGE
    if dialect_name == "postgresql":
        server_version_info = getattr(any_engine.dialect, "server_version_info", (0,))
        try:
            major = int(server_version_info[0]) if isinstance(server_version_info, tuple) and server_version_info else 0
        except Exception:
            major = 0
        if major < 15:
            pytest.skip("PostgreSQL MERGE requires version 15+")

    # Create a simple test table
    metadata = MetaData()
    test_compile_table = Table(
        "compile_test",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("key", String(50)),
        Column("value", String(100)),
    )

    test_values = {"id": 1, "key": "test", "value": "data"}

    # Create MERGE statement
    merge_stmt, _ = OnConflictUpsert.create_merge_upsert(
        table=test_compile_table,
        values=test_values,
        conflict_columns=["key"],
        update_columns=["value"],
        dialect_name=dialect_name,
    )

    # Compile the statement
    if isinstance(any_engine, AsyncEngine):
        compiled = merge_stmt.compile(dialect=any_engine.dialect)  # type: ignore[attr-defined]
    else:
        compiled = merge_stmt.compile(dialect=any_engine.dialect)

    # Verify it compiled
    assert compiled is not None
    assert str(compiled)  # Should produce SQL string


async def test_store_upsert_integration(
    any_engine: Engine | AsyncEngine,
    store_model: type[DeclarativeBase],
) -> None:
    """Test store-like upsert pattern with model class."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    if dialect_name == "spanner+spanner":
        pytest.skip("Spanner does not support UniqueConstraint - requires unique indexes")

    # Cast to Any to avoid pyright attribute errors in test expressions
    TestStoreModel: Any = store_model

    # Tables are already created by fixtures
    # The base class will handle id generation (integer or UUID)
    store_data = {
        "key": "cache_key",
        "namespace": "default",
        "value": "cached_data",
        "expires_at": (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat(),
    }

    # Create upsert for store pattern
    additional_params: dict[str, Any] = {}
    if OnConflictUpsert.supports_native_upsert(dialect_name):
        upsert_stmt = OnConflictUpsert.create_upsert(
            table=TestStoreModel.__table__,  # type: ignore[arg-type]
            values=store_data,
            conflict_columns=["key", "namespace"],
            update_columns=["value", "expires_at"],
            dialect_name=dialect_name,
        )
    elif dialect_name == "oracle":
        upsert_stmt, additional_params = OnConflictUpsert.create_merge_upsert(  # type: ignore[assignment]
            table=TestStoreModel.__table__,  # type: ignore[arg-type]
            values=store_data,
            conflict_columns=["key", "namespace"],
            update_columns=["value", "expires_at"],
            dialect_name=dialect_name,
        )
    else:
        pytest.skip(f"No upsert support for dialect '{dialect_name}'")
    additional_params2: dict[str, Any] = {}
    # Execute and verify
    if isinstance(any_engine, AsyncEngine):
        async_session_factory = async_sessionmaker(bind=any_engine)
        async with async_session_factory() as session:
            if dialect_name == "oracle":
                # Pass the values for MERGE statements
                merged_params = {**store_data, **additional_params}
                await session.execute(upsert_stmt, merged_params)
            else:
                await session.execute(upsert_stmt)
            await session.commit()

            # Verify insertion
            result = await session.execute(
                select(TestStoreModel).where(
                    (TestStoreModel.key == store_data["key"]) & (TestStoreModel.namespace == store_data["namespace"])
                )
            )
            obj = result.scalar_one_or_none()
            assert obj is not None
            assert obj.value == "cached_data"

        # Update with new expiration
        updated_store = store_data.copy()
        updated_store["value"] = "updated_cache"
        updated_store["expires_at"] = (datetime.datetime.now() + datetime.timedelta(hours=2)).isoformat()

        if OnConflictUpsert.supports_native_upsert(dialect_name):
            upsert_stmt2 = OnConflictUpsert.create_upsert(
                table=TestStoreModel.__table__,  # type: ignore[arg-type]
                values=updated_store,
                conflict_columns=["key", "namespace"],
                update_columns=["value", "expires_at"],
                dialect_name=dialect_name,
            )
        else:
            upsert_stmt2, additional_params2 = OnConflictUpsert.create_merge_upsert(  # type: ignore[assignment]
                table=TestStoreModel.__table__,  # type: ignore[arg-type]  # type: ignore[arg-type]
                values=updated_store,
                conflict_columns=["key", "namespace"],
                update_columns=["value", "expires_at"],
                dialect_name=dialect_name,
            )

        async with async_session_factory() as session:
            if dialect_name == "oracle":
                merged_params2 = {**updated_store, **additional_params2}
                await session.execute(upsert_stmt2, merged_params2)
            else:
                await session.execute(upsert_stmt2)
            await session.commit()

            # Verify update
            result = await session.execute(
                select(TestStoreModel).where(
                    (TestStoreModel.key == updated_store["key"])
                    & (TestStoreModel.namespace == updated_store["namespace"])
                )
            )
            obj = result.scalar_one_or_none()
            assert obj is not None
            assert obj.value == "updated_cache"
    else:
        session_factory = sessionmaker(bind=any_engine)
        with session_factory() as session:
            if dialect_name == "oracle":
                # Pass the values for MERGE statements
                merged_params = {**store_data, **additional_params}
                session.execute(upsert_stmt, merged_params)
            else:
                session.execute(upsert_stmt)
            session.commit()

            # Verify insertion
            result = session.execute(
                select(TestStoreModel).where(
                    (TestStoreModel.key == store_data["key"]) & (TestStoreModel.namespace == store_data["namespace"])
                )
            )
            obj = result.scalar_one_or_none()
            assert obj is not None
            assert obj.value == "cached_data"

        # Update with new expiration
        updated_store = store_data.copy()
        updated_store["value"] = "updated_cache"
        updated_store["expires_at"] = (datetime.datetime.now() + datetime.timedelta(hours=2)).isoformat()

        if OnConflictUpsert.supports_native_upsert(dialect_name):
            upsert_stmt2 = OnConflictUpsert.create_upsert(
                table=TestStoreModel.__table__,  # type: ignore[arg-type]
                values=updated_store,
                conflict_columns=["key", "namespace"],
                update_columns=["value", "expires_at"],
                dialect_name=dialect_name,
            )
        else:
            upsert_stmt2, additional_params2 = OnConflictUpsert.create_merge_upsert(  # type: ignore[assignment]
                table=TestStoreModel.__table__,  # type: ignore[arg-type]  # type: ignore[arg-type]
                values=updated_store,
                conflict_columns=["key", "namespace"],
                update_columns=["value", "expires_at"],
                dialect_name=dialect_name,
            )

        with session_factory() as session:
            if dialect_name == "oracle":
                merged_params2 = {**updated_store, **additional_params2}
                session.execute(upsert_stmt2, merged_params2)
            else:
                session.execute(upsert_stmt2)
            session.commit()

            # Verify update
            result = session.execute(
                select(TestStoreModel).where(
                    (TestStoreModel.key == updated_store["key"])
                    & (TestStoreModel.namespace == updated_store["namespace"])
                )
            )
            obj = result.scalar_one_or_none()
            assert obj is not None
            assert obj.value == "updated_cache"

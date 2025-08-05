"""Integration tests for advanced_alchemy.operations module.

These tests run against actual database instances to verify that the upsert
and MERGE operations work correctly across different database backends.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from advanced_alchemy.operations import MergeStatement, OnConflictUpsert

if TYPE_CHECKING:
    from pytest import FixtureRequest
    from sqlalchemy import Engine

pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture
def test_table() -> Table:
    """Create a test table for operations testing."""
    metadata = MetaData()
    return Table(
        "operation_test_table",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("key", String(50), nullable=False),
        Column("namespace", String(50), nullable=False),
        Column("value", String(255)),
        Column("created_at", String(50)),
        UniqueConstraint("key", "namespace", name="uq_key_namespace"),
    )


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
        "sqlite_engine",
        "duckdb_engine",
        "psycopg_engine",
        "mssql_engine",
        "oracle18c_engine",
        "oracle23ai_engine",
        "cockroachdb_engine",
        "spanner_engine",
        "mock_sync_engine",
        # Async engines
        "aiosqlite_engine",
        "asyncmy_engine",
        "asyncpg_engine",
        "psycopg_async_engine",
        "cockroachdb_async_engine",
        "mssql_async_engine",
        "oracle18c_async_engine",
        "oracle23ai_async_engine",
        "mock_async_engine",
    ]
)
def any_engine(request: FixtureRequest) -> Engine | AsyncEngine:
    """Return any available engine for testing."""
    return cast("Engine | AsyncEngine", request.getfixturevalue(request.param))


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

    if not OnConflictUpsert.supports_native_upsert(dialect_name):
        pytest.skip(f"Dialect '{dialect_name}' does not support native upsert")

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.run_sync(test_table.create)
            await conn.commit()
    else:
        test_table.create(any_engine)  # type: ignore[arg-type]

    try:
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

        # Verify the statement has the expected dialect-specific attributes
        if dialect_name in {"postgresql", "cockroachdb", "sqlite", "duckdb"}:
            assert hasattr(upsert_stmt, "on_conflict_do_update")
        elif dialect_name in {"mysql", "mariadb"}:
            assert hasattr(upsert_stmt, "on_duplicate_key_update")

    finally:
        if isinstance(any_engine, AsyncEngine):
            async with any_engine.connect() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(lambda sync_conn: test_table.drop(sync_conn, checkfirst=True))
                await conn.commit()
        else:
            test_table.drop(any_engine, checkfirst=True)  # type: ignore[arg-type]


async def test_upsert_insert_then_update_cycle(
    any_engine: Engine | AsyncEngine,
    test_table: Table,
    upsert_values: dict[str, Any],
    updated_values: dict[str, Any],
) -> None:
    """Test complete upsert cycle: insert new, then update existing."""
    from tests.helpers import maybe_async

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    if not OnConflictUpsert.supports_native_upsert(dialect_name):
        pytest.skip(f"Dialect '{dialect_name}' does not support native upsert")

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.run_sync(test_table.create)
            await conn.commit()
    else:
        test_table.create(any_engine)  # type: ignore[arg-type]

    try:
        if isinstance(any_engine, AsyncEngine):
            async_session_factory = async_sessionmaker(bind=any_engine)
            any_session = async_session_factory()
        else:
            session_factory = sessionmaker(bind=any_engine)
            any_session = session_factory()

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

        await maybe_async(any_session.execute(upsert_stmt))
        await maybe_async(any_session.commit())

        # Verify record was inserted
        result = await maybe_async(
            any_session.execute(
                select(test_table).where(
                    test_table.c.key == upsert_values["key"], test_table.c.namespace == upsert_values["namespace"]
                )
            )
        )
        row = result.fetchone()  # type: ignore[attr-defined]

        assert row is not None
        assert row.value == upsert_values["value"]

        # Second upsert - should update
        update_stmt = OnConflictUpsert.create_upsert(
            table=test_table,
            values=updated_values,
            conflict_columns=conflict_columns,
            update_columns=update_columns,
            dialect_name=dialect_name,
        )

        await maybe_async(any_session.execute(update_stmt))
        await maybe_async(any_session.commit())

        # Verify record was updated
        updated_result = await maybe_async(
            any_session.execute(
                select(test_table).where(
                    test_table.c.key == updated_values["key"], test_table.c.namespace == updated_values["namespace"]
                )
            )
        )
        updated_row = updated_result.fetchone()  # type: ignore[attr-defined]  # type: ignore[attr-defined]

        assert updated_row is not None
        assert updated_row.value == updated_values["value"]

        # Verify only one record exists
        count_result = await maybe_async(any_session.execute(select(test_table)))
        all_rows = count_result.fetchall()  # type: ignore[attr-defined]
        assert len(all_rows) == 1

        await maybe_async(any_session.close())

    finally:
        if isinstance(any_engine, AsyncEngine):
            async with any_engine.connect() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(lambda sync_conn: test_table.drop(sync_conn, checkfirst=True))
                await conn.commit()
        else:
            test_table.drop(any_engine, checkfirst=True)  # type: ignore[arg-type]


async def test_batch_upsert_operations(any_engine: Engine | AsyncEngine, test_table: Table) -> None:
    """Test batch upsert operations with multiple records."""
    from tests.helpers import maybe_async

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    if not OnConflictUpsert.supports_native_upsert(dialect_name):
        pytest.skip(f"Dialect '{dialect_name}' does not support native upsert")

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.run_sync(test_table.create)
            await conn.commit()
    else:
        test_table.create(any_engine)  # type: ignore[arg-type]

    try:
        if isinstance(any_engine, AsyncEngine):
            async_session_factory = async_sessionmaker(bind=any_engine)
            any_session = async_session_factory()
        else:
            session_factory = sessionmaker(bind=any_engine)
            any_session = session_factory()

        conflict_columns = ["key", "namespace"]
        update_columns = ["value", "created_at"]

        # Insert multiple records using separate upsert operations
        records = [
            {"id": 1, "key": "key1", "namespace": "ns1", "value": "value1", "created_at": "2024-01-01"},
            {"id": 2, "key": "key2", "namespace": "ns1", "value": "value2", "created_at": "2024-01-01"},
            {"id": 3, "key": "key1", "namespace": "ns2", "value": "value3", "created_at": "2024-01-01"},
        ]

        for record in records:
            upsert_stmt = OnConflictUpsert.create_upsert(
                table=test_table,
                values=record,
                conflict_columns=conflict_columns,
                update_columns=update_columns,
                dialect_name=dialect_name,
            )
            await maybe_async(any_session.execute(upsert_stmt))

        await maybe_async(any_session.commit())

        # Verify all records were inserted
        all_results = await maybe_async(any_session.execute(select(test_table)))
        all_rows = all_results.fetchall()  # type: ignore[attr-defined]
        assert len(all_rows) == 3

        # Update one of the records
        updated_record = {
            "id": 1,
            "key": "key1",
            "namespace": "ns1",
            "value": "updated_value1",
            "created_at": "2024-01-02",
        }
        update_stmt = OnConflictUpsert.create_upsert(
            table=test_table,
            values=updated_record,
            conflict_columns=conflict_columns,
            update_columns=update_columns,
            dialect_name=dialect_name,
        )
        await maybe_async(any_session.execute(update_stmt))
        await maybe_async(any_session.commit())

        # Verify record was updated and count remains the same
        final_results = await maybe_async(any_session.execute(select(test_table)))
        final_rows = final_results.fetchall()  # type: ignore[attr-defined]
        assert len(final_rows) == 3

        # Find the updated record
        updated_result = await maybe_async(
            any_session.execute(select(test_table).where(test_table.c.key == "key1", test_table.c.namespace == "ns1"))
        )
        updated_row = updated_result.fetchone()  # type: ignore[attr-defined]  # type: ignore[attr-defined]

        assert updated_row is not None
        assert updated_row.value == "updated_value1"

        await maybe_async(any_session.close())

    finally:
        if isinstance(any_engine, AsyncEngine):
            async with any_engine.connect() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(lambda sync_conn: test_table.drop(sync_conn, checkfirst=True))
                await conn.commit()
        else:
            test_table.drop(any_engine, checkfirst=True)  # type: ignore[arg-type]


async def test_merge_statement_with_oracle_postgres(
    any_engine: Engine | AsyncEngine,
    test_table: Table,
    upsert_values: dict[str, Any],
    updated_values: dict[str, Any],
) -> None:
    """Test MERGE statement operations with Oracle and PostgreSQL 15+."""
    from tests.helpers import maybe_async

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    supports_merge = dialect_name == "oracle" or (
        dialect_name == "postgresql"
        and hasattr(any_engine.dialect, "server_version_info")
        and any_engine.dialect.server_version_info
        and any_engine.dialect.server_version_info[0] >= 15
    )

    if not supports_merge:
        pytest.skip(f"Dialect '{dialect_name}' does not support MERGE statements")

    if isinstance(any_engine, AsyncEngine):
        async with any_engine.connect() as conn:
            await conn.run_sync(test_table.create)
            await conn.commit()
    else:
        test_table.create(any_engine)  # type: ignore[arg-type]

    try:
        if isinstance(any_engine, AsyncEngine):
            async_session_factory = async_sessionmaker(bind=any_engine)
            any_session = async_session_factory()
        else:
            session_factory = sessionmaker(bind=any_engine)
            any_session = session_factory()

        conflict_columns = ["key", "namespace"]
        update_columns = ["value", "created_at"]

        # Create MERGE statement
        merge_stmt, additional_params = OnConflictUpsert.create_merge_upsert(
            table=test_table,
            values=upsert_values,
            conflict_columns=conflict_columns,
            update_columns=update_columns,
            dialect_name=dialect_name,
        )
        merge_values = {**upsert_values, **additional_params}

        assert isinstance(merge_stmt, MergeStatement)

        # Execute MERGE - should insert
        await maybe_async(any_session.execute(merge_stmt, merge_values))
        await maybe_async(any_session.commit())

        # Verify record was inserted
        result = await maybe_async(
            any_session.execute(
                select(test_table).where(
                    test_table.c.key == upsert_values["key"], test_table.c.namespace == upsert_values["namespace"]
                )
            )
        )
        row = result.fetchone()  # type: ignore[attr-defined]

        assert row is not None
        assert row.value == upsert_values["value"]

        # Execute MERGE again with updated values - should update
        update_merge_stmt, update_additional_params = OnConflictUpsert.create_merge_upsert(
            table=test_table,
            values=updated_values,
            conflict_columns=conflict_columns,
            update_columns=update_columns,
            dialect_name=dialect_name,
        )
        update_merge_values = {**updated_values, **update_additional_params}

        await maybe_async(any_session.execute(update_merge_stmt, update_merge_values))
        await maybe_async(any_session.commit())

        # Verify record was updated
        updated_result = await maybe_async(
            any_session.execute(
                select(test_table).where(
                    test_table.c.key == updated_values["key"], test_table.c.namespace == updated_values["namespace"]
                )
            )
        )
        updated_row = updated_result.fetchone()  # type: ignore[attr-defined]  # type: ignore[attr-defined]

        assert updated_row is not None
        assert updated_row.value == updated_values["value"]

        # Verify only one record exists
        count_result = await maybe_async(any_session.execute(select(test_table)))
        all_rows = count_result.fetchall()  # type: ignore[attr-defined]
        assert len(all_rows) == 1

        await maybe_async(any_session.close())

    finally:
        if isinstance(any_engine, AsyncEngine):
            async with any_engine.connect() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(lambda sync_conn: test_table.drop(sync_conn, checkfirst=True))
                await conn.commit()
        else:
            test_table.drop(any_engine, checkfirst=True)  # type: ignore[arg-type]


async def test_merge_compilation_oracle_postgres(any_engine: Engine | AsyncEngine) -> None:
    """Test MERGE statement compilation for Oracle and PostgreSQL."""

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    dialect_name = any_engine.dialect.name

    supports_merge = dialect_name == "oracle" or (
        dialect_name == "postgresql"
        and hasattr(any_engine.dialect, "server_version_info")
        and any_engine.dialect.server_version_info
        and any_engine.dialect.server_version_info[0] >= 15
    )

    if not supports_merge:
        pytest.skip(f"Dialect '{dialect_name}' does not support MERGE statements")

    metadata = MetaData()
    test_table = Table(
        "merge_test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("key", String(50)),
        Column("value", String(100)),
        UniqueConstraint("key", name="uq_merge_key"),
    )

    values = {"id": 1, "key": "test", "value": "test_value"}
    conflict_columns = ["key"]

    merge_stmt, additional_params = OnConflictUpsert.create_merge_upsert(
        table=test_table,
        values=values,
        conflict_columns=conflict_columns,
        dialect_name=dialect_name,
    )

    # Compile the statement to SQL
    compiled = merge_stmt.compile(bind=any_engine)
    sql_str = str(compiled)

    # Verify the compiled SQL contains expected MERGE keywords
    assert "MERGE" in sql_str.upper()
    assert "USING" in sql_str.upper()
    assert "WHEN MATCHED" in sql_str.upper() or "WHEN NOT MATCHED" in sql_str.upper()


async def test_store_upsert_integration(any_engine: Engine | AsyncEngine) -> None:
    """Test that SQLAlchemyStore correctly uses new upsert operations."""
    from advanced_alchemy.extensions.litestar.plugins.init import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
    from advanced_alchemy.extensions.litestar.store import SQLAlchemyStore, StoreModelMixin
    from tests.helpers import maybe_async

    if getattr(any_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    # Create a test store model
    class TestStoreModel(StoreModelMixin):
        __tablename__ = "test_store_operations"

    # Create table
    if isinstance(any_engine, AsyncEngine):
        # Async engine
        async with any_engine.connect() as conn:
            await conn.run_sync(TestStoreModel.metadata.create_all)
            await conn.commit()
    else:
        # Sync engine
        TestStoreModel.metadata.create_all(any_engine)  # type: ignore[arg-type]

    try:
        # Create store configuration
        if isinstance(any_engine, AsyncEngine):
            config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig = SQLAlchemyAsyncConfig(engine_instance=any_engine)  # type: ignore[arg-type]
        else:
            config = SQLAlchemySyncConfig(engine_instance=any_engine)  # type: ignore[arg-type]

        store = SQLAlchemyStore(config=config, model=TestStoreModel, namespace="test_ops")

        # Test set operation (should use upsert operations internally)
        expiration_seconds = 3600  # 1 hour
        await maybe_async(store.set("test_key", "test_value", expires_in=expiration_seconds))

        # Verify the value was set
        result = await maybe_async(store.get("test_key"))
        assert result == b"test_value"

        # Test update operation (should use upsert operations internally)
        await maybe_async(store.set("test_key", "updated_value", expires_in=expiration_seconds))

        # Verify the value was updated
        updated_result = await maybe_async(store.get("test_key"))
        assert updated_result == b"updated_value"

        # Verify only one record exists in the store
        if isinstance(any_engine, AsyncEngine):
            # Async
            from sqlalchemy import func
            from sqlalchemy.ext.asyncio import async_sessionmaker

            async_session_factory = async_sessionmaker(bind=any_engine)  # type: ignore[arg-type]
            async with async_session_factory() as async_session:
                count_result = await async_session.execute(select(func.count()).select_from(TestStoreModel))
                count = count_result.scalar()
                assert count == 1
        else:
            # Sync
            from sqlalchemy import func
            from sqlalchemy.orm import sessionmaker

            session_factory = sessionmaker(bind=any_engine)  # type: ignore[arg-type]
            with session_factory() as sync_session:
                count = sync_session.scalar(select(func.count()).select_from(TestStoreModel))
                assert count == 1

    finally:
        if isinstance(any_engine, AsyncEngine):
            # Async engine
            async with any_engine.connect() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(TestStoreModel.metadata.drop_all)
                await conn.commit()
        else:
            # Sync engine
            TestStoreModel.metadata.drop_all(any_engine)  # type: ignore[arg-type]

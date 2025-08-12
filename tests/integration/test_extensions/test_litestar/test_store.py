"""Integration tests for Litestar store extensions.

These tests run against actual database instances to verify that store implementations
work correctly across all supported database backends.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.store import SQLAlchemyStore, StoreModelMixin
from tests.integration.helpers import async_clean_tables, clean_tables

if TYPE_CHECKING:
    from sqlalchemy import Engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("litestar_store"),
]


# Module-level cache for model classes to prevent recreation
_store_model_cache: dict[str, type] = {}


@pytest.fixture(scope="session")
def store_model_class(request: pytest.FixtureRequest) -> type[StoreModelMixin]:
    """Create store model class once per session/worker.

    This fixture creates a unique model class per pytest session or xdist worker
    to prevent metadata conflicts while allowing table reuse across tests.
    """
    # Get worker ID for xdist parallel execution
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    cache_key = f"store_{worker_id}"

    if cache_key not in _store_model_cache:

        class TestStoreBase(DeclarativeBase):
            pass

        class IntegrationTestStoreModel(StoreModelMixin, TestStoreBase):
            """Test store model for integration tests."""

            __tablename__ = f"integration_test_store_{worker_id}"

        _store_model_cache[cache_key] = IntegrationTestStoreModel

    return _store_model_cache[cache_key]


@pytest.fixture
def store_tables_setup(
    engine: Engine, store_model_class: type[StoreModelMixin]
) -> Generator[type[StoreModelMixin], None, None]:
    """Create store tables for each test run but reuse model classes.

    Tables are created per database engine type but model classes are cached
    to prevent recreation. Fast data cleanup is used between individual tests.
    """
    # Skip for Spanner and CockroachDB - table conflicts with BigInt models
    dialect_name = getattr(engine.dialect, "name", "")
    if dialect_name == "spanner+spanner":
        pytest.skip("Spanner doesn't support direct UNIQUE constraints creation")
    if dialect_name.startswith("cockroach"):
        pytest.skip("CockroachDB has table conflicts with BigInt models")

    # Skip table creation for mock engines
    if dialect_name != "mock":
        store_model_class.metadata.create_all(engine)

    yield store_model_class

    # Clean up tables at end of test run for this engine
    if getattr(engine.dialect, "name", "") != "mock":
        store_model_class.metadata.drop_all(engine, checkfirst=True)


@pytest.fixture
async def async_store_tables_setup(
    async_engine: AsyncEngine, store_model_class: type[StoreModelMixin]
) -> AsyncGenerator[type[StoreModelMixin], None]:
    """Create async store tables for each test run but reuse model classes.

    Tables are created per database engine type but model classes are cached
    to prevent recreation. Fast data cleanup is used between individual tests.
    """
    # Skip for Spanner and CockroachDB - table conflicts with BigInt models
    dialect_name = getattr(async_engine.dialect, "name", "")
    if dialect_name == "spanner+spanner":
        pytest.skip("Spanner doesn't support direct UNIQUE constraints creation")
    if dialect_name.startswith("cockroach"):
        pytest.skip("CockroachDB has table conflicts with BigInt models")

    # Skip table creation for mock engines
    if dialect_name != "mock":
        async with async_engine.begin() as conn:
            await conn.run_sync(store_model_class.metadata.create_all)

    yield store_model_class

    # Clean up tables at end of test run for this engine
    if getattr(async_engine.dialect, "name", "") != "mock":
        async with async_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: store_model_class.metadata.drop_all(sync_conn, checkfirst=True))


@pytest.fixture
def test_store_model(
    store_tables_setup: type[StoreModelMixin], engine: Engine
) -> Generator[type[StoreModelMixin], None, None]:
    """Per-test fixture with fast data cleanup.

    This fixture provides the store model class and ensures data cleanup
    between tests without recreating tables.
    """
    model_class = store_tables_setup
    yield model_class

    # Fast data-only cleanup between tests
    if getattr(engine.dialect, "name", "") != "mock":
        clean_tables(engine, model_class.metadata)


@pytest.fixture
async def async_test_store_model(
    async_store_tables_setup: type[StoreModelMixin], async_engine: AsyncEngine
) -> AsyncGenerator[type[StoreModelMixin], None]:
    """Per-test async fixture with fast data cleanup.

    This fixture provides the store model class and ensures data cleanup
    between tests without recreating tables.
    """
    model_class = async_store_tables_setup
    yield model_class

    # Fast data-only cleanup between tests
    if getattr(async_engine.dialect, "name", "") != "mock":
        await async_clean_tables(async_engine, model_class.metadata)


# Store fixtures
@pytest.fixture
def sync_store_config(engine: Engine) -> SQLAlchemySyncConfig:
    """Create sync config with test engine."""
    return SQLAlchemySyncConfig(
        engine_instance=engine,
        session_dependency_key="db_session",
    )


@pytest.fixture
async def async_store_config(async_engine: AsyncEngine) -> SQLAlchemyAsyncConfig:
    """Create async config with test engine."""
    return SQLAlchemyAsyncConfig(
        engine_instance=async_engine,
        session_dependency_key="db_session",
    )


@pytest.fixture
def sync_store(sync_store_config: SQLAlchemySyncConfig, test_store_model: type[StoreModelMixin]) -> SQLAlchemyStore:
    """Create sync store."""
    return SQLAlchemyStore(config=sync_store_config, model=test_store_model, namespace="test")


@pytest.fixture
def async_store(
    async_store_config: SQLAlchemyAsyncConfig, async_test_store_model: type[StoreModelMixin]
) -> SQLAlchemyStore:
    """Create async store."""
    return SQLAlchemyStore(config=async_store_config, model=async_test_store_model, namespace="test")


# Legacy database setup fixtures - now no-ops since tables are session-scoped
@pytest.fixture
def setup_sync_database() -> Generator[None, None, None]:
    """Legacy fixture - tables are now session-scoped, no setup needed."""
    yield


@pytest.fixture
async def setup_async_database() -> AsyncGenerator[None, None]:
    """Legacy fixture - tables are now session-scoped, no setup needed."""
    yield


# Store Tests
async def test_async_store_complete_lifecycle(
    async_store: SQLAlchemyStore,
    setup_async_database: None,
) -> None:
    """Test complete store lifecycle: set, get, update, delete."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = async_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    key = "test_key"
    original_value = "test_value"
    updated_value = "updated_value"
    expires_in = 3600

    # Set value
    await async_store.set(key, original_value, expires_in=expires_in)

    # Get value
    result = await async_store.get(key)
    assert result == original_value.encode()

    # Update value
    await async_store.set(key, updated_value, expires_in=expires_in)

    # Verify update
    result = await async_store.get(key)
    assert result == updated_value.encode()

    # Check expiration time
    expires_time = await async_store.expires_in(key)
    assert expires_time is not None
    assert expires_time > 3500  # Should be close to 3600 seconds

    # Delete value
    await async_store.delete(key)

    # Verify deletion
    result = await async_store.get(key)
    assert result is None


async def test_sync_store_complete_lifecycle(
    sync_store: SQLAlchemyStore,
    setup_sync_database: None,
) -> None:
    """Test complete store lifecycle with sync store."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = sync_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    key = "sync_key"
    original_value = "sync_value"
    updated_value = "sync_updated"
    expires_in = 3600

    # Set value
    await sync_store.set(key, original_value, expires_in=expires_in)

    # Get value
    result = await sync_store.get(key)
    assert result == original_value.encode()

    # Update value
    await sync_store.set(key, updated_value, expires_in=expires_in)

    # Verify update
    result = await sync_store.get(key)
    assert result == updated_value.encode()

    # Check expiration time
    expires_time = await sync_store.expires_in(key)
    assert expires_time is not None
    assert expires_time > 3500  # Should be close to 3600 seconds

    # Delete value
    await sync_store.delete(key)

    # Verify deletion
    result = await sync_store.get(key)
    assert result is None


async def test_async_store_delete_all(
    async_store: SQLAlchemyStore,
    setup_async_database: None,
) -> None:
    """Test deletion of all store entries."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = async_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    # Set multiple values
    keys = ["key1", "key2", "key3"]
    for key in keys:
        await async_store.set(key, f"value_{key}", expires_in=3600)

    # Verify they exist
    for key in keys:
        result = await async_store.get(key)
        assert result == f"value_{key}".encode()

    # Delete all
    await async_store.delete_all()

    # Verify all deleted
    for key in keys:
        result = await async_store.get(key)
        assert result is None


async def test_sync_store_delete_all(
    sync_store: SQLAlchemyStore,
    setup_sync_database: None,
) -> None:
    """Test deletion of all store entries with sync store."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = sync_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    # Set multiple values
    keys = ["sync_key1", "sync_key2", "sync_key3"]
    for key in keys:
        await sync_store.set(key, f"sync_value_{key}", expires_in=3600)

    # Verify they exist
    for key in keys:
        result = await sync_store.get(key)
        assert result == f"sync_value_{key}".encode()

    # Delete all
    await sync_store.delete_all()

    # Verify all deleted
    for key in keys:
        result = await sync_store.get(key)
        assert result is None


async def test_store_with_namespace(
    async_store: SQLAlchemyStore,
    setup_async_database: None,
) -> None:
    """Test store namespace functionality."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = async_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    # Create namespaced store
    namespaced_store = async_store.with_namespace("sub")
    assert namespaced_store.namespace == "test_sub"

    # Set value in original store
    await async_store.set("key", "original", expires_in=3600)

    # Set value in namespaced store
    await namespaced_store.set("key", "namespaced", expires_in=3600)

    # Verify both values exist independently
    original_result = await async_store.get("key")
    namespaced_result = await namespaced_store.get("key")

    assert original_result == b"original"
    assert namespaced_result == b"namespaced"


async def test_store_exists_functionality(
    async_store: SQLAlchemyStore,
    setup_async_database: None,
) -> None:
    """Test store exists functionality."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = async_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    key = "exists_test"
    value = "test_exists_value"

    # Key should not exist initially
    assert await async_store.exists(key) is False

    # Set value
    await async_store.set(key, value, expires_in=3600)

    # Key should exist now
    assert await async_store.exists(key) is True

    # Delete key
    await async_store.delete(key)

    # Key should not exist anymore
    assert await async_store.exists(key) is False


async def test_store_database_upsert_integration(
    async_store: SQLAlchemyStore,
    setup_async_database: None,
) -> None:
    """Test that store correctly uses upsert operations internally."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = async_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    key = "upsert_test_key"
    value1 = "initial_value"
    value2 = "updated_value"
    expires_in = 3600

    # First set - should insert
    await async_store.set(key, value1, expires_in=expires_in)

    # Verify insert
    result = await async_store.get(key)
    assert result == value1.encode()

    # Second set - should update using upsert
    await async_store.set(key, value2, expires_in=expires_in)

    # Verify update
    result = await async_store.get(key)
    assert result == value2.encode()

    # Verify only one record exists in the store
    engine = async_store._config.engine_instance
    model = async_store._model

    if isinstance(engine, AsyncEngine):
        # Async engine
        async_session_factory = async_sessionmaker(bind=engine)
        async with async_session_factory() as session:
            count_result = await session.execute(
                select(func.count()).select_from(model).where(model.key == key, model.namespace == "test")
            )
            count = count_result.scalar()
            assert count == 1
    else:
        # Sync engine
        session_factory = sessionmaker(bind=engine)
        with session_factory() as session:
            count = session.scalar(
                select(func.count()).select_from(model).where(model.key == key, model.namespace == "test")
            )
            assert count == 1


async def test_store_renew_functionality(
    async_store: SQLAlchemyStore,
    setup_async_database: None,
) -> None:
    """Test store renew functionality."""

    # Skip mock engines - integration tests should test real databases
    engine_instance = async_store._config.engine_instance
    if engine_instance is not None and getattr(engine_instance.dialect, "name", "") == "mock":
        pytest.skip("Mock engine cannot test real database operations")

    key = "renew_test"
    value = "test_renew_value"
    initial_expires_in = 3600
    renew_for = 7200

    # Set value with initial expiration
    await async_store.set(key, value, expires_in=initial_expires_in)

    # Get value with renewal
    result = await async_store.get(key, renew_for=renew_for)
    assert result == value.encode()

    # Check that expiration was extended
    expires_time = await async_store.expires_in(key)
    assert expires_time is not None
    assert expires_time > 6000  # Should be close to 7200 seconds (renewed time)

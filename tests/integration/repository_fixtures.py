"""Session-scoped fixtures for repository tests to minimize DDL operations."""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fixtures.bigint import models as models_bigint
from tests.fixtures.uuid import models as models_uuid
from tests.integration.helpers import async_clean_tables, clean_tables, get_worker_id

if TYPE_CHECKING:
    from pytest import FixtureRequest

# Module-level caches for model classes
_uuid_model_cache: dict[str, dict[str, type]] = {}
_bigint_model_cache: dict[str, dict[str, type]] = {}
_tables_created_sync: dict[str, bool] = {}
_tables_created_async: dict[str, bool] = {}


class RepositoryModelRegistry:
    """Registry for cached repository test models with worker isolation."""

    @classmethod
    def get_uuid_models(cls, worker_id: str) -> dict[str, type]:
        """Get all UUID-based models for a worker."""
        cache_key = f"uuid_{worker_id}"
        if cache_key not in _uuid_model_cache:
            # Simply reuse the existing models - they already have proper structure
            # Use the Author model as the base since it has metadata
            _uuid_model_cache[cache_key] = {
                "base": models_uuid.UUIDAuthor,  # Use a model that has the metadata
                "author": models_uuid.UUIDAuthor,
                "book": models_uuid.UUIDBook,
                "rule": models_uuid.UUIDRule,
                "secret": models_uuid.UUIDSecret,
                "slug_book": models_uuid.UUIDSlugBook,
                "item": models_uuid.UUIDItem,
                "tag": models_uuid.UUIDTag,
                "model_with_fetched_value": models_uuid.UUIDModelWithFetchedValue,
                "file_document": models_uuid.UUIDFileDocument,
            }

        return _uuid_model_cache[cache_key]

    @classmethod
    def get_bigint_models(cls, worker_id: str) -> dict[str, type]:
        """Get all BigInt-based models for a worker."""
        cache_key = f"bigint_{worker_id}"
        if cache_key not in _bigint_model_cache:
            # Simply reuse the existing models - they already have proper structure
            _bigint_model_cache[cache_key] = {
                "base": models_bigint.BigIntAuthor,  # Use a model that has the metadata
                "author": models_bigint.BigIntAuthor,
                "book": models_bigint.BigIntBook,
                "rule": models_bigint.BigIntRule,
                "secret": models_bigint.BigIntSecret,
                "slug_book": models_bigint.BigIntSlugBook,
                "item": models_bigint.BigIntItem,
                "tag": models_bigint.BigIntTag,
                "model_with_fetched_value": models_bigint.BigIntModelWithFetchedValue,
                "file_document": models_bigint.BigIntFileDocument,
            }

        return _bigint_model_cache[cache_key]


def reseed_data_sync(engine: Engine, models: dict[str, type], pk_type: str) -> None:
    """Reseed data to original state for sync test isolation."""
    from sqlalchemy import delete, insert

    seed_data = get_seed_data(pk_type)

    with engine.begin() as conn:
        # Delete existing data in reverse dependency order
        for table in reversed(models["base"].metadata.sorted_tables):
            conn.execute(delete(table))

        # Re-insert seed data
        conn.execute(insert(models["author"]), seed_data["authors"])
        conn.execute(insert(models["rule"]), seed_data["rules"])
        conn.execute(insert(models["secret"]), seed_data["secrets"])


async def reseed_data_async(async_engine: AsyncEngine, models: dict[str, type], pk_type: str) -> None:
    """Reseed data to original state for async test isolation."""
    from sqlalchemy import delete, insert

    seed_data = get_seed_data(pk_type)

    async with async_engine.begin() as conn:
        # Delete existing data in reverse dependency order
        for table in reversed(models["base"].metadata.sorted_tables):
            await conn.execute(delete(table))

        # Re-insert seed data
        await conn.execute(insert(models["author"]), seed_data["authors"])
        await conn.execute(insert(models["rule"]), seed_data["rules"])
        await conn.execute(insert(models["secret"]), seed_data["secrets"])


def get_seed_data(pk_type: str) -> dict[str, list[dict[str, Any]]]:
    """Get seed data for the given PK type."""
    if pk_type == "uuid":
        return {
            "authors": [
                {
                    "id": UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
                    "name": "Agatha Christie",
                    "dob": datetime.date(1890, 9, 15),
                    "created_at": datetime.datetime(2023, 3, 1, tzinfo=datetime.timezone.utc),
                    "updated_at": datetime.datetime(2023, 5, 11, tzinfo=datetime.timezone.utc),
                },
                {
                    "id": UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"),
                    "name": "Leo Tolstoy",
                    "dob": datetime.date(1828, 9, 9),
                    "created_at": datetime.datetime(2023, 5, 2, tzinfo=datetime.timezone.utc),
                    "updated_at": datetime.datetime(2023, 5, 15, tzinfo=datetime.timezone.utc),
                },
            ],
            "rules": [
                {
                    "id": UUID("f34545b9-663c-4fce-915d-dd1ae9cea42a"),
                    "name": "Initial loading rule.",
                    "config": {"url": "https://example.org", "setting_123": 1},
                    "created_at": datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc),
                    "updated_at": datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc),
                },
                {
                    "id": UUID("f34545b9-663c-4fce-915d-dd1ae9cea34b"),
                    "name": "Secondary loading rule.",
                    "config": {"url": "https://example.org", "bar": "foo", "setting_123": 4},
                    "created_at": datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc),
                    "updated_at": datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc),
                },
            ],
            "secrets": [
                {
                    "id": UUID("f34545b9-663c-4fce-915d-dd1ae9cea42a"),
                    "secret": "I'm a secret!",
                    "long_secret": "It's clobbering time.",
                },
            ],
        }
    # bigint
    return {
        "authors": [
            {
                "id": 2023,
                "name": "Agatha Christie",
                "dob": datetime.date(1890, 9, 15),
                "created_at": datetime.datetime(2023, 3, 1, tzinfo=datetime.timezone.utc),
                "updated_at": datetime.datetime(2023, 5, 11, tzinfo=datetime.timezone.utc),
            },
            {
                "id": 2024,
                "name": "Leo Tolstoy",
                "dob": datetime.date(1828, 9, 9),
                "created_at": datetime.datetime(2023, 5, 2, tzinfo=datetime.timezone.utc),
                "updated_at": datetime.datetime(2023, 5, 15, tzinfo=datetime.timezone.utc),
            },
        ],
        "rules": [
            {
                "id": 2025,
                "name": "Initial loading rule.",
                "config": {"url": "https://example.org", "setting_123": 1},
                "created_at": datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc),
                "updated_at": datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc),
            },
            {
                "id": 2026,
                "name": "Secondary loading rule.",
                "config": {"url": "https://example.org", "bar": "foo", "setting_123": 4},
                "created_at": datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc),
                "updated_at": datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc),
            },
        ],
        "secrets": [
            {
                "id": 2025,
                "secret": "I'm a secret!",
                "long_secret": "It's clobbering time.",
            },
        ],
    }


# UUID Model Fixtures
@pytest.fixture(scope="session")
def uuid_models(request: FixtureRequest) -> dict[str, type]:
    """Get all UUID models for the current worker."""
    worker_id = get_worker_id(request)
    return RepositoryModelRegistry.get_uuid_models(worker_id)


@pytest.fixture(scope="session")
def uuid_author_model(uuid_models: dict[str, type]) -> type:
    """Get UUID Author model."""
    return uuid_models["author"]


@pytest.fixture(scope="session")
def uuid_book_model(uuid_models: dict[str, type]) -> type:
    """Get UUID Book model."""
    return uuid_models["book"]


@pytest.fixture(scope="session")
def uuid_rule_model(uuid_models: dict[str, type]) -> type:
    """Get UUID Rule model."""
    return uuid_models["rule"]


@pytest.fixture(scope="session")
def uuid_secret_model(uuid_models: dict[str, type]) -> type:
    """Get UUID Secret model."""
    return uuid_models["secret"]


@pytest.fixture(scope="session")
def uuid_slug_book_model(uuid_models: dict[str, type]) -> type:
    """Get UUID SlugBook model."""
    return uuid_models["slug_book"]


# BigInt Model Fixtures
@pytest.fixture(scope="session")
def bigint_models(request: FixtureRequest) -> dict[str, type]:
    """Get all BigInt models for the current worker."""
    worker_id = get_worker_id(request)
    return RepositoryModelRegistry.get_bigint_models(worker_id)


@pytest.fixture(scope="session")
def bigint_author_model(bigint_models: dict[str, type]) -> type:
    """Get BigInt Author model."""
    return bigint_models["author"]


@pytest.fixture(scope="session")
def bigint_book_model(bigint_models: dict[str, type]) -> type:
    """Get BigInt Book model."""
    return bigint_models["book"]


@pytest.fixture(scope="session")
def bigint_rule_model(bigint_models: dict[str, type]) -> type:
    """Get BigInt Rule model."""
    return bigint_models["rule"]


@pytest.fixture(scope="session")
def bigint_secret_model(bigint_models: dict[str, type]) -> type:
    """Get BigInt Secret model."""
    return bigint_models["secret"]


@pytest.fixture(scope="session")
def bigint_slug_book_model(bigint_models: dict[str, type]) -> type:
    """Get BigInt SlugBook model."""
    return bigint_models["slug_book"]


# Sync Setup Fixtures
# These are function-scoped to ensure data is inserted for each test
# while engines remain session-scoped for performance
@pytest.fixture
def uuid_sync_setup(
    uuid_models: dict[str, type],
    engine: Engine,
) -> Generator[dict[str, type], None, None]:
    """Setup UUID tables and seed data for sync tests."""
    if getattr(engine.dialect, "name", "") != "mock":
        base_model = uuid_models["base"]
        engine_key = f"uuid_{engine.dialect.name}_{id(engine)}"

        # Create tables once per engine type
        if engine_key not in _tables_created_sync:
            # For CockroachDB, ensure careful table ordering due to foreign key constraints
            if "cockroach" in engine.dialect.name:
                try:
                    # Create tables with foreign key dependency order for CockroachDB
                    base_model.metadata.create_all(engine, checkfirst=True)
                except Exception as e:
                    # If there are dependency issues, create tables individually
                    try:
                        # Create author table first (no dependencies)
                        uuid_models["author"].__table__.create(engine, checkfirst=True)
                        # Then create other tables that might depend on author
                        for model_name in [
                            "rule",
                            "secret",
                            "book",
                            "item",
                            "tag",
                            "slug_book",
                            "model_with_fetched_value",
                            "file_document",
                        ]:
                            if model_name in uuid_models:
                                uuid_models[model_name].__table__.create(engine, checkfirst=True)
                    except Exception:
                        # If individual creation also fails, use the original error
                        raise e
            else:
                base_model.metadata.create_all(engine)
            _tables_created_sync[engine_key] = True

        # Always reseed data to ensure fresh state for each test
        reseed_data_sync(engine, uuid_models, "uuid")

    yield uuid_models
    # Cleanup is handled by auto-clean fixtures in conftest.py


@pytest.fixture
def bigint_sync_setup(
    bigint_models: dict[str, type],
    engine: Engine,
) -> Generator[dict[str, type], None, None]:
    """Setup BigInt tables and seed data for sync tests."""
    # Skip for Spanner and CockroachDB
    if engine.dialect.name.startswith(("spanner", "cockroach")):
        pytest.skip(f"{engine.dialect.name} doesn't support bigint PKs well")

    # Skip mock engines - they don't support proper BigInt operations
    if engine.dialect.name == "mock":
        pytest.skip("Mock engines don't support BigInt operations")

    base_model = bigint_models["base"]
    engine_key = f"bigint_{engine.dialect.name}_{id(engine)}"

    # Create tables once per engine type
    if engine_key not in _tables_created_sync:
        base_model.metadata.create_all(engine)
        _tables_created_sync[engine_key] = True

    # Always clean and re-insert seed data to ensure fresh state for each test
    try:
        clean_tables(engine, base_model.metadata)
    except Exception:
        # Ignore cleanup errors - tables might not exist yet
        pass

    # For Oracle, try a more aggressive cleanup approach
    if engine.dialect.name == "oracle":
        try:
            with engine.begin() as conn:
                # Use DELETE instead of TRUNCATE for better compatibility
                for table in reversed(base_model.metadata.sorted_tables):
                    try:
                        conn.execute(table.delete())
                    except Exception:
                        # Ignore individual table errors
                        pass
        except Exception:
            # Ignore cleanup errors
            pass

    # Always reseed data to ensure fresh state for each test
    reseed_data_sync(engine, bigint_models, "bigint")

    yield bigint_models
    # Cleanup is handled by auto-clean fixtures in conftest.py


# Async Setup Fixtures
@pytest_asyncio.fixture()
async def uuid_async_setup(
    uuid_models: dict[str, type],
    async_engine: AsyncEngine,
) -> AsyncGenerator[dict[str, type], None]:
    """Setup UUID tables and seed data for async tests."""
    if getattr(async_engine.dialect, "name", "") != "mock":
        base_model = uuid_models["base"]
        engine_key = f"uuid_{async_engine.dialect.name}_{id(async_engine)}"

        # Create tables once per engine type
        if engine_key not in _tables_created_async:
            # For CockroachDB, ensure careful table ordering due to foreign key constraints
            if "cockroach" in async_engine.dialect.name:
                try:
                    async with async_engine.begin() as conn:
                        await conn.run_sync(
                            lambda sync_conn: base_model.metadata.create_all(sync_conn, checkfirst=True)
                        )
                except Exception as e:
                    # If there are dependency issues, create tables individually
                    try:
                        async with async_engine.begin() as conn:
                            # Create author table first (no dependencies)
                            await conn.run_sync(
                                lambda sync_conn: uuid_models["author"].__table__.create(sync_conn, checkfirst=True)
                            )
                            # Then create other tables that might depend on author
                            for model_name in [
                                "rule",
                                "secret",
                                "book",
                                "item",
                                "tag",
                                "slug_book",
                                "model_with_fetched_value",
                                "file_document",
                            ]:
                                if model_name in uuid_models:
                                    table = uuid_models[model_name].__table__
                                    await conn.run_sync(lambda sync_conn, t=table: t.create(sync_conn, checkfirst=True))  # type: ignore[misc,unused-ignore]
                    except Exception:
                        # If individual creation also fails, use the original error
                        raise e
            else:
                async with async_engine.begin() as conn:
                    await conn.run_sync(base_model.metadata.create_all)
            _tables_created_async[engine_key] = True

        # Always clean and re-insert seed data to ensure fresh state for each test
        try:
            await async_clean_tables(async_engine, base_model.metadata)
        except Exception:
            # Ignore cleanup errors - tables might not exist yet
            pass

        # For Oracle, try a more aggressive cleanup approach
        if async_engine.dialect.name == "oracle":
            try:
                async with async_engine.begin() as conn:
                    # Use DELETE instead of TRUNCATE for better compatibility
                    for table in reversed(base_model.metadata.sorted_tables):
                        try:
                            await conn.execute(table.delete())
                        except Exception:
                            # Ignore individual table errors
                            pass
            except Exception:
                # Ignore cleanup errors
                pass

        # Always reseed data to ensure fresh state for each test
        await reseed_data_async(async_engine, uuid_models, "uuid")

    yield uuid_models
    # Cleanup is handled by auto-clean fixtures in conftest.py


@pytest_asyncio.fixture()
async def bigint_async_setup(
    bigint_models: dict[str, type],
    async_engine: AsyncEngine,
) -> AsyncGenerator[dict[str, type], None]:
    """Setup BigInt tables and seed data for async tests."""
    # Skip for Spanner and CockroachDB
    if async_engine.dialect.name.startswith(("spanner", "cockroach")):
        pytest.skip(f"{async_engine.dialect.name} doesn't support bigint PKs well")

    # Skip mock engines - they don't support proper BigInt operations
    if async_engine.dialect.name == "mock":
        pytest.skip("Mock engines don't support BigInt operations")

    base_model = bigint_models["base"]
    engine_key = f"bigint_{async_engine.dialect.name}_{id(async_engine)}"

    # Create tables once per engine type
    if engine_key not in _tables_created_async:
        async with async_engine.begin() as conn:
            await conn.run_sync(base_model.metadata.create_all)
        _tables_created_async[engine_key] = True

    # Always clean and re-insert seed data to ensure fresh state for each test
    try:
        await async_clean_tables(async_engine, base_model.metadata)
    except Exception:
        # Ignore cleanup errors - tables might not exist yet
        pass

    # For Oracle, try a more aggressive cleanup approach
    if async_engine.dialect.name == "oracle":
        try:
            async with async_engine.begin() as conn:
                # Use DELETE instead of TRUNCATE for better compatibility
                for table in reversed(base_model.metadata.sorted_tables):
                    try:
                        await conn.execute(table.delete())
                    except Exception:
                        # Ignore individual table errors
                        pass
        except Exception:
            # Ignore cleanup errors
            pass

    # Always reseed data to ensure fresh state for each test
    await reseed_data_async(async_engine, bigint_models, "bigint")

    yield bigint_models
    # Cleanup is handled by auto-clean fixtures in conftest.py


# Primary key type fixture
@pytest.fixture(params=["uuid", "bigint"])
def repository_pk_type(request: FixtureRequest) -> str:
    """Return the primary key type of the repository."""
    pk_type = str(request.param)

    # Skip BigInt tests for CockroachDB and Spanner - they only support UUID primary keys
    if pk_type == "bigint":
        # Try to determine the engine being used from fixture names
        # This is not ideal but works with the current architecture
        fixture_names = request.fixturenames

        # Check for known unsupported engines in fixture names
        if any("cockroach" in name for name in fixture_names):
            pytest.skip("BigInt primary keys not supported for CockroachDB")
        elif any("spanner" in name for name in fixture_names):
            pytest.skip("BigInt primary keys not supported for Spanner")

        # Also check if we can get the session to check the dialect
        # This works when any_session is available
        if "any_session" in fixture_names:
            try:
                session = request.getfixturevalue("any_session")
                if hasattr(session, "bind") and session.bind:
                    dialect_name = getattr(session.bind.dialect, "name", "")
                    if "cockroach" in dialect_name or "spanner" in dialect_name:
                        pytest.skip(f"BigInt primary keys not supported for {dialect_name}")
            except Exception:
                # If we can't get the session, continue with other checks
                pass

    return pk_type  # type: ignore[no-any-return]


# Combined fixtures that select based on PK type
@pytest.fixture
def repository_models_sync(
    repository_pk_type: str,
    request: FixtureRequest,
) -> dict[str, type]:
    """Get the correct models based on PK type for sync tests."""
    if repository_pk_type == "uuid":
        return request.getfixturevalue("uuid_sync_setup")  # type: ignore[no-any-return]
    return request.getfixturevalue("bigint_sync_setup")  # type: ignore[no-any-return]


@pytest_asyncio.fixture()
async def repository_models_async(
    repository_pk_type: str,
    uuid_async_setup: dict[str, type],
    bigint_async_setup: dict[str, type],
) -> dict[str, type]:
    """Get the correct models based on PK type for async tests."""
    if repository_pk_type == "uuid":
        return uuid_async_setup
    return bigint_async_setup

"""Session-scoped fixtures for repository tests to minimize DDL operations."""

from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, insert
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


def get_seed_data(pk_type: str) -> dict[str, list[dict[str, Any]]]:
    """Get seed data for the given PK type."""
    if pk_type == "uuid":
        return {
            "authors": [
                {
                    "id": UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
                    "name": "Agatha Christie",
                    "dob": datetime.date(1890, 9, 15),
                    "created_at": datetime.datetime(2023, 5, 1, tzinfo=datetime.timezone.utc),
                    "updated_at": datetime.datetime(2023, 5, 11, tzinfo=datetime.timezone.utc),
                },
                {
                    "id": UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"),
                    "name": "Leo Tolstoy",
                    "dob": datetime.date(1828, 9, 9),
                    "created_at": datetime.datetime(2023, 5, 2, tzinfo=datetime.timezone.utc),
                    "updated_at": datetime.datetime(2023, 5, 12, tzinfo=datetime.timezone.utc),
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
                "created_at": datetime.datetime(2023, 5, 1, tzinfo=datetime.timezone.utc),
                "updated_at": datetime.datetime(2023, 5, 11, tzinfo=datetime.timezone.utc),
            },
            {
                "id": 2024,
                "name": "Leo Tolstoy",
                "dob": datetime.date(1828, 9, 9),
                "created_at": datetime.datetime(2023, 5, 2, tzinfo=datetime.timezone.utc),
                "updated_at": datetime.datetime(2023, 5, 12, tzinfo=datetime.timezone.utc),
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
            base_model.metadata.create_all(engine)
            _tables_created_sync[engine_key] = True

        # Insert seed data
        seed_data = get_seed_data("uuid")
        with engine.begin() as conn:
            conn.execute(insert(uuid_models["author"]), seed_data["authors"])
            conn.execute(insert(uuid_models["rule"]), seed_data["rules"])
            conn.execute(insert(uuid_models["secret"]), seed_data["secrets"])

    yield uuid_models

    # Clean data between tests
    if getattr(engine.dialect, "name", "") != "mock":
        clean_tables(engine, uuid_models["base"].metadata)


@pytest.fixture
def bigint_sync_setup(
    bigint_models: dict[str, type],
    engine: Engine,
) -> Generator[dict[str, type], None, None]:
    """Setup BigInt tables and seed data for sync tests."""
    # Skip for Spanner and CockroachDB
    if engine.dialect.name.startswith(("spanner", "cockroach")):
        pytest.skip(f"{engine.dialect.name} doesn't support bigint PKs well")

    if getattr(engine.dialect, "name", "") != "mock":
        base_model = bigint_models["base"]
        engine_key = f"bigint_{engine.dialect.name}_{id(engine)}"

        # Create tables once per engine type
        if engine_key not in _tables_created_sync:
            base_model.metadata.create_all(engine)
            _tables_created_sync[engine_key] = True

        # Insert seed data
        seed_data = get_seed_data("bigint")
        with engine.begin() as conn:
            conn.execute(insert(bigint_models["author"]), seed_data["authors"])
            conn.execute(insert(bigint_models["rule"]), seed_data["rules"])
            conn.execute(insert(bigint_models["secret"]), seed_data["secrets"])

    yield bigint_models

    # Clean data between tests
    if getattr(engine.dialect, "name", "") != "mock":
        clean_tables(engine, bigint_models["base"].metadata)


# Async Setup Fixtures
@pytest.fixture
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
            async with async_engine.begin() as conn:
                await conn.run_sync(base_model.metadata.create_all)
            _tables_created_async[engine_key] = True

        # Insert seed data
        seed_data = get_seed_data("uuid")
        async with async_engine.begin() as conn:
            await conn.execute(insert(uuid_models["author"]), seed_data["authors"])
            await conn.execute(insert(uuid_models["rule"]), seed_data["rules"])
            await conn.execute(insert(uuid_models["secret"]), seed_data["secrets"])

    yield uuid_models

    # Clean data between tests
    if getattr(async_engine.dialect, "name", "") != "mock":
        await async_clean_tables(async_engine, uuid_models["base"].metadata)


@pytest.fixture
async def bigint_async_setup(
    bigint_models: dict[str, type],
    async_engine: AsyncEngine,
) -> AsyncGenerator[dict[str, type], None]:
    """Setup BigInt tables and seed data for async tests."""
    # Skip for Spanner and CockroachDB
    if async_engine.dialect.name.startswith(("spanner", "cockroach")):
        pytest.skip(f"{async_engine.dialect.name} doesn't support bigint PKs well")

    if getattr(async_engine.dialect, "name", "") != "mock":
        base_model = bigint_models["base"]
        engine_key = f"bigint_{async_engine.dialect.name}_{id(async_engine)}"

        # Create tables once per engine type
        if engine_key not in _tables_created_async:
            async with async_engine.begin() as conn:
                await conn.run_sync(base_model.metadata.create_all)
            _tables_created_async[engine_key] = True

        # Insert seed data
        seed_data = get_seed_data("bigint")
        async with async_engine.begin() as conn:
            await conn.execute(insert(bigint_models["author"]), seed_data["authors"])
            await conn.execute(insert(bigint_models["rule"]), seed_data["rules"])
            await conn.execute(insert(bigint_models["secret"]), seed_data["secrets"])

    yield bigint_models

    # Clean data between tests
    if getattr(async_engine.dialect, "name", "") != "mock":
        await async_clean_tables(async_engine, bigint_models["base"].metadata)


# Primary key type fixture
@pytest.fixture(params=["uuid", "bigint"])
def repository_pk_type(request: FixtureRequest) -> str:
    """Return the primary key type of the repository."""
    pk_type = str(request.param)

    # Skip BigInt tests for CockroachDB and Spanner - they only support UUID primary keys
    if pk_type == "bigint":
        # Check if we're using CockroachDB or Spanner engines
        worker_id = get_worker_id(request)
        if any(dialect in worker_id.lower() for dialect in ["cockroach", "spanner"]):
            pytest.skip(f"BigInt primary keys not supported for {worker_id}")

    return pk_type  # type: ignore[no-any-return]


# Combined fixtures that select based on PK type
@pytest.fixture
def repository_models_sync(
    repository_pk_type: str,
    request: FixtureRequest,
) -> dict[str, type]:
    """Get the correct models based on PK type for sync tests."""
    if repository_pk_type == "uuid":
        return request.getfixturevalue("uuid_sync_setup")
    return request.getfixturevalue("bigint_sync_setup")


@pytest.fixture
async def repository_models_async(
    repository_pk_type: str,
    request: FixtureRequest,
) -> dict[str, type]:
    """Get the correct models based on PK type for async tests."""
    if repository_pk_type == "uuid":
        return request.getfixturevalue("uuid_async_setup")
    return request.getfixturevalue("bigint_async_setup")

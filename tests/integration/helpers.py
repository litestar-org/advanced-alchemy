from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any, TypeVar

import pytest
from sqlalchemy import Engine, MetaData, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase

from tests.integration.cleanup import clean_tables

if TYPE_CHECKING:
    pass

ModelT = TypeVar("ModelT", bound=DeclarativeBase)

# Module-level cache for model classes to prevent recreation
_model_class_cache: dict[str, type] = {}


class CachedModelRegistry:
    """Registry for caching test model classes with worker isolation.

    This registry creates isolated model classes per worker to prevent
    metadata conflicts during parallel test execution.
    """

    _cache: dict[tuple[str, str, str], type] = {}

    @classmethod
    def get_model(
        cls,
        pk_type: str,
        model_name: str,
        worker_id: str,
        base_module: Any,
    ) -> type:
        """Get or create a cached model class with isolated metadata.

        Args:
            pk_type: Primary key type ('uuid' or 'bigint')
            model_name: Name of the model class
            worker_id: pytest-xdist worker ID
            base_module: Module containing the model classes

        Returns:
            Cached model class with isolated metadata
        """
        cache_key = (pk_type, model_name, worker_id)

        if cache_key not in cls._cache:
            # Get the original model class
            original_model = getattr(base_module, model_name)

            # Create isolated base with new metadata
            class IsolatedBase(DeclarativeBase):
                pass

            # Create new model with worker-specific table name
            table_name = f"{original_model.__tablename__}_{worker_id}"

            # Create a new model class inheriting from the original
            class_dict = {
                "__tablename__": table_name,
                "__mapper_args__": {"concrete": True},
            }

            # Copy all mapped columns and relationships from original
            for key, value in original_model.__dict__.items():
                if not key.startswith("_") and key not in ("__tablename__", "__mapper_args__"):
                    if hasattr(value, "property"):  # It's a mapped property
                        class_dict[key] = value

            IsolatedModel = type(
                f"{model_name}_{worker_id}",
                (original_model.__class__, IsolatedBase),
                class_dict,
            )

            cls._cache[cache_key] = IsolatedModel

        return cls._cache[cache_key]

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the model cache."""
        cls._cache.clear()


def get_worker_id(request: pytest.FixtureRequest) -> str:
    """Get the xdist worker ID for table isolation."""
    return str(getattr(request.config, "workerinput", {}).get("workerid", "master"))


def create_cached_model(
    cache_key: str,
    base_model: type[ModelT],
    table_suffix: str | None = None,
) -> type[ModelT]:
    """Create or retrieve a cached model class with isolated metadata.

    Args:
        cache_key: Unique key for caching the model
        base_model: The base model class to extend
        table_suffix: Optional suffix for table name (defaults to cache_key)

    Returns:
        A unique model class with isolated metadata
    """
    if cache_key not in _model_class_cache:
        # Create new base with isolated metadata
        class IsolatedBase(DeclarativeBase):
            pass

        # Create the model with unique table name
        table_name = f"{base_model.__tablename__}_{table_suffix or cache_key}"

        class IsolatedModel(base_model, IsolatedBase):  # type: ignore[misc,valid-type]
            __tablename__ = table_name
            __mapper_args__ = {"concrete": True}

        _model_class_cache[cache_key] = IsolatedModel

    return _model_class_cache[cache_key]  # type: ignore[return-value]


def create_session_fixtures(
    model_class: type[ModelT],
    table_prefix: str,
    seed_data: list[dict[str, Any]] | None = None,
) -> tuple[Any, Any, Any, Any]:
    """Generate session-scoped fixtures for any model class.

    This is the standard pattern for all integration tests to minimize DDL operations.

    Args:
        model_class: The SQLAlchemy model class
        table_prefix: Prefix for the table name (used for caching)
        seed_data: Optional seed data to insert at session start

    Returns:
        Tuple of (cached_model_fixture, sync_setup_fixture, async_setup_fixture, model_fixture)
    """

    @pytest.fixture(scope="session")
    def cached_model(request: pytest.FixtureRequest) -> type[ModelT]:
        """Create model class once per session/worker."""
        worker_id = get_worker_id(request)
        cache_key = f"{table_prefix}_{worker_id}"
        return create_cached_model(cache_key, model_class, worker_id)

    @pytest.fixture
    def sync_setup(
        cached_model: type[ModelT],
        engine: Engine,
    ) -> Generator[type[ModelT], None, None]:
        """Setup tables and seed data for sync tests."""
        # Skip for mock engines
        if getattr(engine.dialect, "name", "") != "mock":
            # Create tables once per engine type
            cached_model.metadata.create_all(engine)

            # Insert seed data if provided
            if seed_data:
                with engine.begin() as conn:
                    conn.execute(insert(cached_model.__table__), seed_data)  # type: ignore[arg-type]

        yield cached_model

        # Clean up tables at end of test run
        if getattr(engine.dialect, "name", "") != "mock":
            cached_model.metadata.drop_all(engine, checkfirst=True)

    @pytest.fixture
    async def async_setup(
        cached_model: type[ModelT],
        async_engine: AsyncEngine,
    ) -> AsyncGenerator[type[ModelT], None]:
        """Setup tables and seed data for async tests."""
        # Skip for mock engines
        if getattr(async_engine.dialect, "name", "") != "mock":
            # Create tables once per engine type
            async with async_engine.begin() as conn:
                await conn.run_sync(cached_model.metadata.create_all)

                # Insert seed data if provided
                if seed_data:
                    await conn.execute(insert(cached_model.__table__), seed_data)  # type: ignore[arg-type]

        yield cached_model

        # Clean up tables at end of test run
        if getattr(async_engine.dialect, "name", "") != "mock":
            async with async_engine.begin() as conn:
                await conn.run_sync(lambda sync_conn: cached_model.metadata.drop_all(sync_conn, checkfirst=True))

    @pytest.fixture
    def model_fixture(
        sync_setup: type[ModelT] | None = None,
        async_setup: type[ModelT] | None = None,
        engine: Engine | None = None,
        async_engine: AsyncEngine | None = None,
    ) -> Generator[type[ModelT], None, None]:
        """Per-test fixture with fast data cleanup."""
        # Determine which setup to use
        model_class = sync_setup if sync_setup is not None else async_setup
        db_engine = engine if engine is not None else async_engine

        yield model_class  # type: ignore[misc]

        # Fast data-only cleanup between tests
        if db_engine is not None and getattr(db_engine.dialect, "name", "") != "mock":
            clean_tables(db_engine, model_class.metadata)  # type: ignore[union-attr,arg-type]

    return cached_model, sync_setup, async_setup, model_fixture


class SeedDataManager:
    """Manage test seed data efficiently with bulk operations and dependency tracking."""

    def __init__(self, metadata: MetaData):
        self.metadata = metadata
        self._dependencies: dict[str, list[str]] = {}

    def track_dependencies(self, table_name: str, depends_on: list[str]) -> None:
        """Track foreign key dependencies between tables."""
        self._dependencies[table_name] = depends_on

    def get_cleanup_order(self) -> list[str]:
        """Get the correct order for cleaning tables based on dependencies."""
        # Simple topological sort
        visited = set()
        order = []

        def visit(table: str) -> None:
            if table in visited:
                return
            visited.add(table)
            for dep in self._dependencies.get(table, []):
                visit(dep)
            order.append(table)

        for table in self.metadata.tables:
            visit(table)

        return order

    def bulk_insert(
        self,
        engine: Engine,
        model: type[DeclarativeBase],
        data: list[dict[str, Any]],
    ) -> None:
        """Perform bulk insert of seed data."""
        if not data:
            return

        with engine.begin() as conn:
            conn.execute(insert(model.__table__), data)  # type: ignore[arg-type]

    async def async_bulk_insert(
        self,
        async_engine: AsyncEngine,
        model: type[DeclarativeBase],
        data: list[dict[str, Any]],
    ) -> None:
        """Perform async bulk insert of seed data."""
        if not data:
            return

        async with async_engine.begin() as conn:
            await conn.execute(insert(model.__table__), data)  # type: ignore[arg-type]


def update_raw_records(raw_authors: list[dict[str, Any]], raw_rules: list[dict[str, Any]]) -> None:
    for raw_author in raw_authors:
        raw_author["dob"] = datetime.datetime.strptime(raw_author["dob"], "%Y-%m-%d").date()
        raw_author["created_at"] = datetime.datetime.strptime(raw_author["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc,
        )
        raw_author["updated_at"] = datetime.datetime.strptime(raw_author["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc,
        )
    for raw_rule in raw_rules:
        raw_rule["created_at"] = datetime.datetime.strptime(raw_rule["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc
        )
        raw_rule["updated_at"] = datetime.datetime.strptime(raw_rule["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            datetime.timezone.utc
        )

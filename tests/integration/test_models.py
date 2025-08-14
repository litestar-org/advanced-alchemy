"""Centralized test models and metadata management.

This module provides isolated metadata registries per database dialect and centralized
model definitions to prevent metadata pollution between test runs.

## Test Infrastructure Overview

This module solves several critical testing issues in Advanced Alchemy:

### 1. Database Locking and Hanging Tests

**Problem**: Tests were hanging due to database locks from improper session/connection management
and session-scoped async fixtures with `loop_scope="session"`.

**Solution**:
- Changed all async engine fixtures to `scope="function"`
- Removed `loop_scope="session"` which caused deadlocks with pytest-asyncio
- Enabled autocleanup fixtures with proper scoping

### 2. Engine Management Consistency

**Problem**: Multiple test files created their own engine fixtures instead of using centralized ones.

**Solution**:
- All tests now use engines from `conftest.py`
- Removed duplicate engine definitions from `test_password_hash.py` and `test_unique_mixin.py`
- Mock engines now have consistent scoping with real engines (session scope)

### 3. Metadata Isolation

**Problem**: Metadata pollution between parallel tests causing table conflicts.

**Solution**:
- `MetadataRegistry` provides isolated metadata instances per database dialect
- `DatabaseCapabilities` provides feature detection for database-specific skipping
- Worker-specific table prefixes prevent conflicts in parallel execution

### 4. Standardized Model Creation

**Problem**: Different approaches to model creation and table management everywhere.

**Solution**:
- `create_test_models()` and `create_bigint_models()` provide standardized model creation
- `get_models_for_engine()` automatically selects appropriate models based on database capabilities
- `create_tables_for_engine()` handles database-specific table creation requirements

## Usage Patterns

### For New Test Files

```python
from tests.integration.test_models import (
    DatabaseCapabilities,
    test_models_sync,
    test_models_async,
)


def test_my_feature(
    engine: Engine, test_models_sync: dict[str, type]
) -> None:
    # Skip if database doesn't support required features
    if DatabaseCapabilities.should_skip_bigint(
        engine.dialect.name
    ):
        pytest.skip("BigInt PKs not supported")

    # Use models from the standardized fixture
    Author = test_models_sync["Author"]
    Book = test_models_sync["Book"]
    # ... test implementation


async def test_my_async_feature(
    async_engine: AsyncEngine,
    test_models_async: dict[str, type],
) -> None:
    # Models are automatically created and cleaned up
    Author = test_models_async["Author"]
    # ... test implementation
```

### For Custom Models

```python
from tests.integration.test_models import (
    MetadataRegistry,
    DatabaseCapabilities,
)


def test_custom_models(engine: Engine) -> None:
    # Get isolated metadata for this engine
    base = MetadataRegistry.get_base(engine.dialect.name)

    class MyModel(base):
        __tablename__ = "my_test_table"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String(50))

    # Create tables
    base.metadata.create_all(engine)
    # ... test implementation

    # Cleanup happens automatically via conftest.py fixtures
```

### Database-Specific Skipping

```python
from tests.integration.test_models import (
    skip_if_unsupported,
    skip_for_dialects,
)


@skip_if_unsupported(
    "supports_bigint_pk", "supports_unique_constraints"
)
def test_advanced_features(engine: Engine) -> None:
    # Test runs only on databases that support both features
    pass


@skip_for_dialects("spanner", "cockroach")
def test_complex_queries(engine: Engine) -> None:
    # Test skipped for Spanner and CockroachDB
    pass
```

## Key Benefits

1. **No More Hanging Tests**: Function-scoped async fixtures prevent deadlocks
2. **Consistent Engine Usage**: All tests use centralized engines from conftest.py
3. **Automatic Cleanup**: Per-test cleanup ensures data isolation without manual intervention
4. **Database Compatibility**: Automatic feature detection and skipping for unsupported operations
5. **Parallel Test Safety**: Worker-specific metadata prevents conflicts in pytest-xdist execution
6. **Easy Maintenance**: Centralized model definitions and standardized patterns

## Migration Guide

To migrate existing test files:

1. Remove custom engine fixtures - use `engine` and `async_engine` from conftest.py
2. Replace custom model definitions with `test_models_sync`/`test_models_async` fixtures
3. Add database capability checks using `DatabaseCapabilities.should_skip_*()` methods
4. Remove manual cleanup code - it's handled automatically
5. Use `MetadataRegistry.get_base()` for custom models that need isolated metadata

This infrastructure ensures reliable, fast, and maintainable tests across all database backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, TypeVar

import pytest
from sqlalchemy import ForeignKey, Integer, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine


class DatabaseCapabilities:
    """Registry of database-specific capabilities and limitations."""

    CAPABILITIES = {
        "postgresql": {
            "supports_bigint_pk": True,
            "supports_uuid_pk": True,
            "supports_unique_constraints": True,
            "supports_merge": True,
            "supports_sequences": True,
            "supports_exists_filters": True,
        },
        "sqlite": {
            "supports_bigint_pk": True,
            "supports_uuid_pk": True,
            "supports_unique_constraints": True,
            "supports_merge": False,
            "supports_sequences": False,
            "supports_exists_filters": True,
        },
        "duckdb": {
            "supports_bigint_pk": True,
            "supports_uuid_pk": True,
            "supports_unique_constraints": True,
            "supports_merge": False,
            "supports_sequences": False,
            "supports_exists_filters": True,
        },
        "spanner+spanner": {
            "supports_bigint_pk": False,  # Spanner has issues with bigint PKs
            "supports_uuid_pk": True,
            "supports_unique_constraints": False,
            "supports_merge": False,
            "supports_sequences": False,
            "supports_exists_filters": False,  # Spanner emulator has constraints
        },
        "cockroachdb": {
            "supports_bigint_pk": False,  # CockroachDB has issues with bigint PKs
            "supports_uuid_pk": True,
            "supports_unique_constraints": True,
            "supports_merge": False,
            "supports_sequences": False,
            "supports_exists_filters": True,
        },
        "oracle": {
            "supports_bigint_pk": True,
            "supports_uuid_pk": True,
            "supports_unique_constraints": True,
            "supports_merge": True,
            "supports_sequences": True,
            "supports_exists_filters": True,
        },
        "mssql": {
            "supports_bigint_pk": True,
            "supports_uuid_pk": True,
            "supports_unique_constraints": True,
            "supports_merge": True,
            "supports_sequences": True,
            "supports_exists_filters": True,
        },
        "mysql": {
            "supports_bigint_pk": True,
            "supports_uuid_pk": True,
            "supports_unique_constraints": True,
            "supports_merge": False,
            "supports_sequences": False,
            "supports_exists_filters": True,
        },
    }

    @classmethod
    def supports_feature(cls, dialect_name: str, feature: str) -> bool:
        """Check if a database dialect supports a specific feature."""
        dialect_key = cls._normalize_dialect_name(dialect_name)
        return cls.CAPABILITIES.get(dialect_key, {}).get(feature, True)

    @classmethod
    def should_skip_bigint(cls, dialect_name: str) -> bool:
        """Check if bigint PKs should be skipped for this dialect."""
        return not cls.supports_feature(dialect_name, "supports_bigint_pk")

    @classmethod
    def should_skip_exists_filter(cls, dialect_name: str) -> bool:
        """Check if EXISTS filter tests should be skipped for this dialect."""
        return not cls.supports_feature(dialect_name, "supports_exists_filters")

    @classmethod
    def should_skip_unique_constraints(cls, dialect_name: str) -> bool:
        """Check if unique constraint tests should be skipped for this dialect."""
        return not cls.supports_feature(dialect_name, "supports_unique_constraints")

    @classmethod
    def _normalize_dialect_name(cls, dialect_name: str) -> str:
        """Normalize dialect names to handle variations."""
        if "spanner" in dialect_name.lower():
            return "spanner+spanner"
        if "cockroach" in dialect_name.lower():
            return "cockroachdb"
        if "sqlite" in dialect_name.lower():
            return "sqlite"
        if (
            "postgresql" in dialect_name.lower()
            or "psycopg" in dialect_name.lower()
            or "asyncpg" in dialect_name.lower()
        ):
            return "postgresql"
        if "duckdb" in dialect_name.lower():
            return "duckdb"
        if "oracle" in dialect_name.lower():
            return "oracle"
        if "mssql" in dialect_name.lower() or "pyodbc" in dialect_name.lower() or "aioodbc" in dialect_name.lower():
            return "mssql"
        if "mysql" in dialect_name.lower() or "asyncmy" in dialect_name.lower():
            return "mysql"
        return dialect_name.lower()


class MetadataRegistry:
    """Manages isolated metadata instances per database dialect."""

    _registries: dict[str, MetaData] = {}
    _base_classes: dict[str, type[DeclarativeBase]] = {}

    @classmethod
    def get_metadata(cls, dialect_name: str) -> MetaData:
        """Get isolated metadata for a specific database dialect."""
        key = DatabaseCapabilities._normalize_dialect_name(dialect_name)
        if key not in cls._registries:
            cls._registries[key] = MetaData()
        return cls._registries[key]

    @classmethod
    def get_base(cls, dialect_name: str) -> type[DeclarativeBase]:
        """Get isolated DeclarativeBase for a specific database dialect."""
        key = DatabaseCapabilities._normalize_dialect_name(dialect_name)
        if key not in cls._base_classes:
            isolated_metadata = cls.get_metadata(dialect_name)

            class IsolatedBase(DeclarativeBase):
                metadata = isolated_metadata
                __abstract__ = True

            cls._base_classes[key] = IsolatedBase
        return cls._base_classes[key]

    @classmethod
    def clear_metadata(cls, dialect_name: str) -> None:
        """Clear metadata for a specific dialect."""
        key = DatabaseCapabilities._normalize_dialect_name(dialect_name)
        if key in cls._registries:
            cls._registries[key].clear()

    @classmethod
    def clear_all(cls) -> None:
        """Clear all metadata registries."""
        for metadata in cls._registries.values():
            metadata.clear()
        cls._registries.clear()
        cls._base_classes.clear()


F = TypeVar("F", bound=Callable[..., Any])


def skip_if_unsupported(*features: str) -> Callable[[F], F]:
    """Decorator to skip tests based on database capabilities."""

    def decorator(test_func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract engine from fixture parameters
            for arg in args:
                if hasattr(arg, "dialect"):
                    capabilities = DatabaseCapabilities()
                    dialect_name = getattr(arg.dialect, "name", "")
                    for feature in features:
                        if not capabilities.supports_feature(dialect_name, feature):
                            pytest.skip(f"Database {dialect_name} doesn't support {feature}")
                    break
            return test_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def skip_for_dialects(*dialect_patterns: str) -> Callable[[F], F]:
    """Decorator to skip tests for specific database dialects."""

    def decorator(test_func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract engine from fixture parameters
            for arg in args:
                if hasattr(arg, "dialect"):
                    dialect_name = getattr(arg.dialect, "name", "").lower()
                    for pattern in dialect_patterns:
                        if pattern.lower() in dialect_name:
                            pytest.skip(f"Test skipped for {dialect_name}")
                    break
            return test_func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


# Centralized model definitions that can be instantiated with different bases
def create_test_models(base: type[DeclarativeBase], table_prefix: str = "") -> dict[str, type[Any]]:
    """Create test model classes with the given base and optional table prefix.

    Args:
        base: The DeclarativeBase to use for these models
        table_prefix: Optional prefix for table names to ensure uniqueness

    Returns:
        Dictionary of model name to model class
    """
    models: dict[str, type[Any]] = {}

    # UUID-based models
    from advanced_alchemy.base import UUIDAuditBase, UUIDBase

    # Use type: ignore for dynamic base class mixing
    class Author(UUIDAuditBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}uuid_author"
        __table_args__ = {"extend_existing": True}

        name: Mapped[str] = mapped_column(String(100))
        dob: Mapped[str | None] = mapped_column(String(50), nullable=True)

    class Book(UUIDAuditBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}uuid_book"
        __table_args__ = {"extend_existing": True}

        title: Mapped[str] = mapped_column(String(250))
        author_id: Mapped[Any] = mapped_column(ForeignKey(f"{table_prefix}uuid_author.id"))
        author: Mapped[Author] = relationship(lazy="joined", innerjoin=True, viewonly=True)

    class Secret(UUIDBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}uuid_secret"
        __table_args__ = {"extend_existing": True}

        secret: Mapped[str] = mapped_column(Text())
        long_secret: Mapped[str | None] = mapped_column(Text(), nullable=True)

    class Item(UUIDBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}uuid_item"
        __table_args__ = {"extend_existing": True}

        name: Mapped[str] = mapped_column(String(50))
        quantity: Mapped[int] = mapped_column(Integer, default=0)

    class Tag(UUIDAuditBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}uuid_tag"
        __table_args__ = {"extend_existing": True}

        name: Mapped[str] = mapped_column(String(50))

    models.update(
        {
            "Author": Author,
            "Book": Book,
            "Secret": Secret,
            "Item": Item,
            "Tag": Tag,
        }
    )

    return models


def create_bigint_models(base: type[DeclarativeBase], table_prefix: str = "") -> dict[str, type[Any]]:
    """Create BigInt-based test model classes.

    Args:
        base: The DeclarativeBase to use for these models
        table_prefix: Optional prefix for table names to ensure uniqueness

    Returns:
        Dictionary of model name to model class
    """
    from advanced_alchemy.base import BigIntAuditBase, BigIntBase

    models: dict[str, type[Any]] = {}

    class BigIntAuthor(BigIntAuditBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}bigint_author"
        __table_args__ = {"extend_existing": True}

        name: Mapped[str] = mapped_column(String(100))
        dob: Mapped[str | None] = mapped_column(String(50), nullable=True)

    class BigIntBook(BigIntAuditBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}bigint_book"
        __table_args__ = {"extend_existing": True}

        title: Mapped[str] = mapped_column(String(250))
        author_id: Mapped[int] = mapped_column(ForeignKey(f"{table_prefix}bigint_author.id"))
        author: Mapped[BigIntAuthor] = relationship(lazy="joined", innerjoin=True, viewonly=True)

    class BigIntItem(BigIntBase, base):  # type: ignore[misc, valid-type]
        __tablename__ = f"{table_prefix}bigint_item"
        __table_args__ = {"extend_existing": True}

        name: Mapped[str] = mapped_column(String(50))
        quantity: Mapped[int] = mapped_column(Integer, default=0)

    models.update(
        {
            "BigIntAuthor": BigIntAuthor,
            "BigIntBook": BigIntBook,
            "BigIntItem": BigIntItem,
        }
    )

    return models


def get_models_for_engine(engine: Engine | AsyncEngine, worker_id: str = "master") -> dict[str, type[Any]]:
    """Get appropriate models for the given engine based on its capabilities.

    Args:
        engine: The database engine
        worker_id: Worker ID for table name prefixing

    Returns:
        Dictionary of model name to model class
    """
    dialect_name = getattr(engine.dialect, "name", "")
    base = MetadataRegistry.get_base(dialect_name)
    table_prefix = f"{worker_id}_" if worker_id != "master" else ""

    models: dict[str, type[Any]] = {}

    # Always include UUID models as they're universally supported
    models.update(create_test_models(base, table_prefix))

    # Only include BigInt models if the database supports them
    if not DatabaseCapabilities.should_skip_bigint(dialect_name):
        models.update(create_bigint_models(base, table_prefix))

    return models


def create_tables_for_engine(engine: Engine | AsyncEngine, models: dict[str, type[Any]] | None = None) -> None:
    """Create tables for the given engine, handling database-specific requirements.

    Args:
        engine: The database engine
        models: Optional specific models to create, otherwise creates all appropriate models
    """
    from sqlalchemy import inspect

    if models is None:
        models = get_models_for_engine(engine)

    dialect_name = getattr(engine.dialect, "name", "")
    metadata = MetadataRegistry.get_metadata(dialect_name)

    # For CockroachDB, need to create tables in dependency order
    if "cockroach" in dialect_name.lower():
        # Create tables without foreign keys first
        inspector = inspect(engine)  # type: ignore[arg-type]
        existing_tables = inspector.get_table_names()

        # First pass: tables without foreign keys
        for model in models.values():
            if model.__tablename__ not in existing_tables:
                # Check if table has foreign keys
                has_fk = any(col.foreign_keys for col in model.__table__.columns)
                if not has_fk:
                    model.__table__.create(engine, checkfirst=True)  # type: ignore[arg-type]

        # Second pass: tables with foreign keys
        for model in models.values():
            if model.__tablename__ not in existing_tables:
                model.__table__.create(engine, checkfirst=True)  # type: ignore[arg-type]
    else:
        # Standard creation for other databases
        metadata.create_all(engine)  # type: ignore[arg-type]


async def create_tables_for_async_engine(engine: AsyncEngine, models: dict[str, type[Any]] | None = None) -> None:
    """Create tables for the given async engine.

    Args:
        engine: The async database engine
        models: Optional specific models to create, otherwise creates all appropriate models
    """
    from sqlalchemy import inspect

    if models is None:
        models = get_models_for_engine(engine)

    dialect_name = getattr(engine.dialect, "name", "")
    metadata = MetadataRegistry.get_metadata(dialect_name)

    async with engine.begin() as conn:
        if "cockroach" in dialect_name.lower():
            # CockroachDB needs dependency ordering
            inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))
            existing_tables = await conn.run_sync(lambda sync_conn: inspector.get_table_names())

            # First pass: tables without foreign keys
            for model in models.values():
                if model.__tablename__ not in existing_tables:
                    has_fk = any(col.foreign_keys for col in model.__table__.columns)
                    if not has_fk:
                        await conn.run_sync(lambda sync_conn: model.__table__.create(sync_conn, checkfirst=True))

            # Second pass: tables with foreign keys
            for model in models.values():
                if model.__tablename__ not in existing_tables:
                    await conn.run_sync(lambda sync_conn: model.__table__.create(sync_conn, checkfirst=True))
        else:
            # Standard creation for other databases
            await conn.run_sync(metadata.create_all)


def cleanup_metadata_for_engine(engine: Engine | AsyncEngine) -> None:
    """Clean up metadata for the given engine."""
    dialect_name = getattr(engine.dialect, "name", "")
    MetadataRegistry.clear_metadata(dialect_name)


# pytest fixtures for standardized model handling across tests
@pytest.fixture()
def test_models_sync(engine: Engine, request: pytest.FixtureRequest) -> dict[str, type[Any]]:
    """Get appropriate test models for the given sync engine.

    This fixture creates isolated models with proper metadata management and
    table creation/cleanup.
    """
    if getattr(engine.dialect, "name", "") == "mock":
        # For mock engines, return empty models dict
        return {}

    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    models = get_models_for_engine(engine, worker_id)

    # Create tables for these models
    create_tables_for_engine(engine, models)

    # Ensure cleanup after test
    def cleanup() -> None:
        try:
            cleanup_metadata_for_engine(engine)
        except Exception:
            pass  # Ignore cleanup errors

    request.addfinalizer(cleanup)
    return models


@pytest.fixture()
async def test_models_async(async_engine: AsyncEngine, request: pytest.FixtureRequest) -> dict[str, type[Any]]:
    """Get appropriate test models for the given async engine.

    This fixture creates isolated models with proper metadata management and
    table creation/cleanup.
    """
    if getattr(async_engine.dialect, "name", "") == "mock":
        # For mock engines, return empty models dict
        return {}

    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    models = get_models_for_engine(async_engine, worker_id)

    # Create tables for these models
    await create_tables_for_async_engine(async_engine, models)

    # Ensure cleanup after test
    def cleanup() -> None:
        try:
            cleanup_metadata_for_engine(async_engine)
        except Exception:
            pass  # Ignore cleanup errors

    request.addfinalizer(cleanup)
    return models

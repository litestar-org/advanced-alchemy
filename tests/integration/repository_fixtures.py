"""Comprehensive fixture system for session-based testing with data isolation.

This module provides a two-tier fixture architecture that separates DDL operations
from DML operations, ensuring proper test isolation and preventing metadata conflicts.
"""

import datetime
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any, Optional, Union
from uuid import UUID

import pytest
import pytest_asyncio

# Import at module level for SQLAlchemy annotation resolution
from sqlalchemy import Column, Engine, FetchedValue, ForeignKey, MetaData, String, Table, delete, insert, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

# Import types for annotations
from advanced_alchemy.types.json import JsonB
from tests.integration.helpers import get_worker_id

if TYPE_CHECKING:
    from pytest import FixtureRequest


def create_dynamic_models(base_type: str = "uuid", worker_id: str = "master") -> dict[str, type]:
    """Create model classes using the current patched base classes.

    This function must be called during test execution after _patch_bases
    has run to ensure we use the correct registry.

    Args:
        base_type: Primary key type ("uuid" or "bigint")
        worker_id: Worker ID to ensure unique class names across parallel test workers
    """
    # Create unique suffix for class names to avoid registry conflicts
    from advanced_alchemy import base
    from advanced_alchemy.types import EncryptedString, EncryptedText

    if base_type == "uuid":
        # Use the patched UUID base classes - all should use the same registry
        # So we'll use the same UUIDAuditBase for all models to ensure same registry
        BaseClass = base.UUIDAuditBase
        SimpleBaseClass = base.UUIDAuditBase  # Changed from UUIDBase
        SecretBaseClass = base.UUIDAuditBase  # Changed from UUIDv7Base
        FetchedValueBaseClass = base.UUIDAuditBase  # Changed from UUIDv6Base

        # Define UUID models using patched bases with unique class names

        class IntegrationUUIDAuthor(BaseClass):  # type: ignore[valid-type,misc]
            """The Author domain object."""

            __tablename__ = f"uuid_author_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_author_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=100))
            string_field: Mapped[Optional[str]] = mapped_column(String(20), default="static value", nullable=True)
            dob: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)

        class IntegrationUUIDBook(SimpleBaseClass):  # type: ignore[valid-type,misc]
            """The Book domain object."""

            __tablename__ = f"uuid_book_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_book_{worker_id}"}

            title: Mapped[str] = mapped_column(String(length=250))
            author_id: Mapped[UUID] = mapped_column(ForeignKey(f"uuid_author_{worker_id}.id"))

        # Define relationships after both classes exist to avoid forward references
        IntegrationUUIDAuthor.books = relationship(
            IntegrationUUIDBook,
            lazy="selectin",
            back_populates="author",
            cascade="all, delete",
        )
        IntegrationUUIDBook.author = relationship(
            IntegrationUUIDAuthor, lazy="joined", innerjoin=True, back_populates="books"
        )

        class IntegrationUUIDRule(BaseClass):  # type: ignore[valid-type,misc]
            """The rule domain object."""

            __tablename__ = f"uuid_rule_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_rule_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=250))
            config: Mapped[dict] = mapped_column(JsonB, default=lambda: {})

        class IntegrationUUIDSecret(SecretBaseClass):  # type: ignore[valid-type,misc]
            """The secret domain object."""

            __tablename__ = f"uuid_secret_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_secret_{worker_id}"}

            secret: Mapped[str] = mapped_column(EncryptedString(key="test_secret_key"))
            long_secret: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)

        class IntegrationUUIDSlugBook(BaseClass):  # type: ignore[valid-type,misc]
            """The SlugBook domain object."""

            __tablename__ = f"uuid_slug_book_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_slug_book_{worker_id}"}

            title: Mapped[str] = mapped_column(String(length=250))
            slug: Mapped[str] = mapped_column(String(100), unique=True)

        class IntegrationUUIDItem(BaseClass):  # type: ignore[valid-type,misc]
            """The Item domain object."""

            __tablename__ = f"uuid_item_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_item_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50))

        class IntegrationUUIDTag(BaseClass):  # type: ignore[valid-type,misc]
            """The Tag domain object."""

            __tablename__ = f"uuid_tag_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_tag_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50), unique=True)

        # Define association table for many-to-many relationship
        uuid_item_tag_table = Table(
            f"uuid_item_tag_{worker_id}",
            BaseClass.metadata,
            Column("item_id", ForeignKey(f"uuid_item_{worker_id}.id"), primary_key=True),
            Column("tag_id", ForeignKey(f"uuid_tag_{worker_id}.id"), primary_key=True),
        )

        # Define many-to-many relationships after classes and table exist
        IntegrationUUIDItem.tags = relationship(
            IntegrationUUIDTag, secondary=uuid_item_tag_table, back_populates="items"
        )
        IntegrationUUIDTag.items = relationship(
            IntegrationUUIDItem, secondary=uuid_item_tag_table, back_populates="tags"
        )

        class IntegrationUUIDModelWithFetchedValue(FetchedValueBaseClass):  # type: ignore[valid-type,misc]
            """Model with fetched value."""

            __tablename__ = f"uuid_model_with_fetched_value_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_model_with_fetched_value_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50))
            # Use a simple default instead of random() to avoid MSSQL compatibility issues
            val: Mapped[int] = mapped_column(FetchedValue(), server_default=text("1"))

        class IntegrationUUIDFileDocument(BaseClass):  # type: ignore[valid-type,misc]
            """FileDocument with JsonB storage for cross-database compatibility."""

            __tablename__ = f"uuid_file_document_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"uuid_file_document_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50))
            # Use JsonB for better database compatibility instead of BLOB storage
            file_data: Mapped[Optional[dict]] = mapped_column(JsonB, nullable=True)
            files_data: Mapped[Optional[dict]] = mapped_column(JsonB, nullable=True)
            file_metadata: Mapped[Optional[dict]] = mapped_column(JsonB, nullable=True)

    else:  # bigint
        # Use the patched BigInt base classes - all should use the same registry
        BaseClass = base.BigIntAuditBase  # type: ignore[assignment]
        SimpleBaseClass = base.BigIntAuditBase  # type: ignore[assignment]
        SecretBaseClass = base.BigIntAuditBase  # type: ignore[assignment]
        FetchedValueBaseClass = base.BigIntAuditBase  # type: ignore[assignment]

        # Define BigInt models using patched bases with unique class names
        class BigIntAuthor(BaseClass):  # type: ignore[valid-type,misc]
            """The Author domain object."""

            __tablename__ = f"bigint_author_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_author_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=100))
            string_field: Mapped[Optional[str]] = mapped_column(String(20), default="static value", nullable=True)
            dob: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)

        class BigIntBook(SimpleBaseClass):  # type: ignore[valid-type,misc]
            """The Book domain object."""

            __tablename__ = f"bigint_book_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_book_{worker_id}"}

            title: Mapped[str] = mapped_column(String(length=250))
            author_id: Mapped[int] = mapped_column(ForeignKey(f"bigint_author_{worker_id}.id"))

        # Define relationships after both classes exist to avoid forward references
        BigIntAuthor.books = relationship(
            BigIntBook,
            lazy="selectin",
            back_populates="author",
            cascade="all, delete",
        )
        BigIntBook.author = relationship(BigIntAuthor, lazy="joined", innerjoin=True, back_populates="books")

        class BigIntRule(BaseClass):  # type: ignore[valid-type,misc]
            """The rule domain object."""

            __tablename__ = f"bigint_rule_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_rule_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=250))
            config: Mapped[dict] = mapped_column(JsonB, default=lambda: {})

        class BigIntSecret(SecretBaseClass):  # type: ignore[valid-type,misc]
            """The secret domain object."""

            __tablename__ = f"bigint_secret_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_secret_{worker_id}"}

            secret: Mapped[str] = mapped_column(EncryptedString(key="test_secret_key"))
            long_secret: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)

        class BigIntSlugBook(BaseClass):  # type: ignore[valid-type,misc]
            """The SlugBook domain object."""

            __tablename__ = f"bigint_slug_book_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_slug_book_{worker_id}"}

            title: Mapped[str] = mapped_column(String(length=250))
            slug: Mapped[str] = mapped_column(String(100), unique=True)

        class BigIntItem(BaseClass):  # type: ignore[valid-type,misc]
            """The Item domain object."""

            __tablename__ = f"bigint_item_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_item_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50))

        class BigIntTag(BaseClass):  # type: ignore[valid-type,misc]
            """The Tag domain object."""

            __tablename__ = f"bigint_tag_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_tag_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50), unique=True)

        # Define association table for many-to-many relationship
        bigint_item_tag_table = Table(
            f"bigint_item_tag_{worker_id}",
            BaseClass.metadata,
            Column("item_id", ForeignKey(f"bigint_item_{worker_id}.id"), primary_key=True),
            Column("tag_id", ForeignKey(f"bigint_tag_{worker_id}.id"), primary_key=True),
        )

        # Define many-to-many relationships after classes and table exist
        BigIntItem.tags = relationship(BigIntTag, secondary=bigint_item_tag_table, back_populates="items")
        BigIntTag.items = relationship(BigIntItem, secondary=bigint_item_tag_table, back_populates="tags")

        class BigIntModelWithFetchedValue(FetchedValueBaseClass):  # type: ignore[valid-type,misc]
            """Model with fetched value."""

            __tablename__ = f"bigint_model_with_fetched_value_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_model_with_fetched_value_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50))
            # Use a simple default instead of random() to avoid MSSQL compatibility issues
            val: Mapped[int] = mapped_column(FetchedValue(), server_default=text("1"))

        class BigIntFileDocument(BaseClass):  # type: ignore[valid-type,misc]
            """FileDocument with JsonB storage for cross-database compatibility."""

            __tablename__ = f"bigint_file_document_{worker_id}"
            __mapper_args__ = {"polymorphic_identity": f"bigint_file_document_{worker_id}"}

            name: Mapped[str] = mapped_column(String(length=50))
            # Use JsonB for better database compatibility instead of BLOB storage
            file_data: Mapped[Optional[dict]] = mapped_column(JsonB, nullable=True)
            files_data: Mapped[Optional[dict]] = mapped_column(JsonB, nullable=True)
            file_metadata: Mapped[Optional[dict]] = mapped_column(JsonB, nullable=True)

    # Return all models
    if base_type == "uuid":
        return {
            "base": IntegrationUUIDAuthor,  # Use Author as base since it has the metadata
            "author": IntegrationUUIDAuthor,
            "book": IntegrationUUIDBook,
            "rule": IntegrationUUIDRule,
            "secret": IntegrationUUIDSecret,
            "slug_book": IntegrationUUIDSlugBook,
            "item": IntegrationUUIDItem,
            "tag": IntegrationUUIDTag,
            "model_with_fetched_value": IntegrationUUIDModelWithFetchedValue,
            "file_document": IntegrationUUIDFileDocument,
        }
    # bigint
    return {
        "base": BigIntAuthor,  # Use Author as base since it has the metadata
        "author": BigIntAuthor,
        "book": BigIntBook,
        "rule": BigIntRule,
        "secret": BigIntSecret,
        "slug_book": BigIntSlugBook,
        "item": BigIntItem,
        "tag": BigIntTag,
        "model_with_fetched_value": BigIntModelWithFetchedValue,
        "file_document": BigIntFileDocument,
    }


class TestDataManager:
    """Manages test data seeding and cleanup for both sync and async sessions."""

    @staticmethod
    def get_seed_data(pk_type: str) -> dict[str, list[dict[str, Any]]]:
        """Get base seed data for the given PK type."""
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

    @classmethod
    def clean_and_seed_sync(cls, session: Session, models: dict[str, type], pk_type: str) -> None:
        """Clean all data and insert fresh seed data for sync session."""
        metadata = models["base"].metadata
        seed_data = cls.get_seed_data(pk_type)

        # Clean all tables in reverse dependency order
        for table in reversed(metadata.sorted_tables):
            try:
                session.execute(delete(table))
            except Exception:
                # Ignore deletion errors for non-existent data
                pass

        # Insert fresh seed data
        if "author" in models:
            session.execute(insert(models["author"]), seed_data["authors"])
        if "rule" in models:
            session.execute(insert(models["rule"]), seed_data["rules"])
        if "secret" in models:
            session.execute(insert(models["secret"]), seed_data["secrets"])

        session.flush()  # Ensure data is written but don't commit yet

    @classmethod
    async def clean_and_seed_async(cls, session: AsyncSession, models: dict[str, type], pk_type: str) -> None:
        """Clean all data and insert fresh seed data for async session."""
        metadata = models["base"].metadata
        seed_data = cls.get_seed_data(pk_type)

        # Clean all tables in reverse dependency order
        for table in reversed(metadata.sorted_tables):
            try:
                await session.execute(delete(table))
            except Exception:
                # Ignore deletion errors for non-existent data
                pass

        # Insert fresh seed data
        if "author" in models:
            await session.execute(insert(models["author"]), seed_data["authors"])
        if "rule" in models:
            await session.execute(insert(models["rule"]), seed_data["rules"])
        if "secret" in models:
            await session.execute(insert(models["secret"]), seed_data["secrets"])

        await session.flush()  # Ensure data is written but don't commit yet


class SchemaManager:
    """Manages schema creation and destruction for test databases."""

    _created_schemas: dict[str, bool] = {}

    @classmethod
    def ensure_schema_sync(cls, engine: Engine, metadata: MetaData, schema_key: str) -> None:
        """Ensure schema exists for sync engine."""
        if schema_key not in cls._created_schemas:
            metadata.create_all(engine, checkfirst=True)
            cls._created_schemas[schema_key] = True

    @classmethod
    async def ensure_schema_async(cls, engine: AsyncEngine, metadata: MetaData, schema_key: str) -> None:
        """Ensure schema exists for async engine."""
        if schema_key not in cls._created_schemas:
            async with engine.begin() as conn:
                await conn.run_sync(metadata.create_all, checkfirst=True)
            cls._created_schemas[schema_key] = True


# ============================================================================
# Model Registry and Caching System
# ============================================================================

# Module-level caches for model classes
_uuid_model_cache: dict[str, dict[str, type]] = {}
_bigint_model_cache: dict[str, dict[str, type]] = {}


class RepositoryModelRegistry:
    """Registry for cached repository test models with worker isolation."""

    @classmethod
    def get_uuid_models(cls, worker_id: str) -> dict[str, type]:
        """Get all UUID-based models for a worker."""
        cache_key = f"uuid_{worker_id}"
        if cache_key not in _uuid_model_cache:
            # Create models using the patched base classes
            _uuid_model_cache[cache_key] = create_dynamic_models("uuid", worker_id)

        return _uuid_model_cache[cache_key]

    @classmethod
    def get_bigint_models(cls, worker_id: str) -> dict[str, type]:
        """Get all BigInt-based models for a worker."""
        cache_key = f"bigint_{worker_id}"
        if cache_key not in _bigint_model_cache:
            # Create models using the patched base classes
            _bigint_model_cache[cache_key] = create_dynamic_models("bigint", worker_id)

        return _bigint_model_cache[cache_key]


# ============================================================================
# DBA Fixtures - Session Scoped DDL Management
# ============================================================================


@pytest.fixture(scope="session")
def uuid_models_dba(request: "FixtureRequest") -> "dict[str, type]":
    """Session-scoped UUID models for DDL operations."""
    worker_id = get_worker_id(request)
    return RepositoryModelRegistry.get_uuid_models(worker_id)


@pytest.fixture(scope="session")
def bigint_models_dba(request: "FixtureRequest") -> dict[str, type]:
    """Session-scoped BigInt models for DDL operations."""
    worker_id = get_worker_id(request)
    return RepositoryModelRegistry.get_bigint_models(worker_id)


@pytest.fixture(scope="session")
def uuid_schema_sync(engine: Engine, uuid_models_dba: dict[str, type], request: "FixtureRequest") -> None:
    """Ensure UUID schema exists for sync engine."""
    if getattr(engine.dialect, "name", "") != "mock":
        worker_id = get_worker_id(request)
        schema_key = f"uuid_sync_{engine.dialect.name}_{worker_id}"
        SchemaManager.ensure_schema_sync(engine, uuid_models_dba["base"].metadata, schema_key)


@pytest.fixture(scope="session")
def bigint_schema_sync(engine: Engine, bigint_models_dba: dict[str, type], request: "FixtureRequest") -> None:
    """Ensure BigInt schema exists for sync engine."""
    # Skip for engines that don't support BigInt PKs well
    if engine.dialect.name.startswith(("spanner", "cockroach", "mock")):
        pytest.skip(f"{engine.dialect.name} doesn't support bigint PKs well")

    worker_id = get_worker_id(request)
    schema_key = f"bigint_sync_{engine.dialect.name}_{worker_id}"
    SchemaManager.ensure_schema_sync(engine, bigint_models_dba["base"].metadata, schema_key)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def uuid_schema_async(
    async_engine: AsyncEngine, uuid_models_dba: dict[str, type], request: "FixtureRequest"
) -> None:
    """Ensure UUID schema exists for async engine."""
    if getattr(async_engine.dialect, "name", "") != "mock":
        worker_id = get_worker_id(request)
        schema_key = f"uuid_async_{async_engine.dialect.name}_{worker_id}"
        await SchemaManager.ensure_schema_async(async_engine, uuid_models_dba["base"].metadata, schema_key)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def bigint_schema_async(
    async_engine: AsyncEngine, bigint_models_dba: dict[str, type], request: "FixtureRequest"
) -> None:
    """Ensure BigInt schema exists for async engine."""
    # Skip for engines that don't support BigInt PKs well
    if async_engine.dialect.name.startswith(("spanner", "cockroach", "mock")):
        pytest.skip(f"{async_engine.dialect.name} doesn't support bigint PKs well")

    worker_id = get_worker_id(request)
    schema_key = f"bigint_async_{async_engine.dialect.name}_{worker_id}"
    await SchemaManager.ensure_schema_async(async_engine, bigint_models_dba["base"].metadata, schema_key)


# ============================================================================
# Per-Test Fixtures - Function Scoped DML Management with Transaction Isolation
# ============================================================================


def supports_savepoints(engine: "Union[Engine, AsyncEngine]") -> bool:
    """Check if the database engine supports savepoints reliably."""
    dialect_name = engine.dialect.name.lower()
    # SQLite and DuckDB don't support nested savepoints reliably
    # Spanner doesn't support savepoints in our test scenario
    return dialect_name not in ("sqlite", "duckdb", "spanner")


@pytest.fixture
def uuid_test_session_sync(
    engine: Engine,
    uuid_models_dba: dict[str, type],
    uuid_schema_sync: None,
    request: "FixtureRequest",
) -> Generator[tuple[Session, dict[str, type]], None, None]:
    """Per-test sync session with UUID data isolation using transactions."""
    if getattr(engine.dialect, "name", "") == "mock":
        # Mock engine handling
        from unittest.mock import create_autospec

        session_mock = create_autospec(Session, instance=True)
        session_mock.bind = engine
        yield session_mock, uuid_models_dba
        return

    # Real database session with transaction isolation
    connection = engine.connect()
    transaction = connection.begin()

    try:
        # Create session bound to this connection
        session = Session(bind=connection, expire_on_commit=False)

        savepoint = None
        if supports_savepoints(engine):
            # Create savepoint for test isolation (PostgreSQL, MySQL, etc.)
            savepoint = connection.begin_nested()

        try:
            # Just yield clean session - no automatic seeding

            yield session, uuid_models_dba

        finally:
            # Cleanup in proper order
            try:
                session.rollback()
            except Exception:
                pass

            try:
                session.close()
            except Exception:
                pass

            if savepoint and savepoint.is_active:
                try:
                    savepoint.rollback()
                except Exception:
                    pass

    finally:
        # Rollback the main transaction and close connection
        try:
            if transaction.is_active:
                transaction.rollback()
        except Exception:
            pass

        try:
            connection.close()
        except Exception:
            pass


@pytest.fixture
def bigint_test_session_sync(
    engine: Engine,
    bigint_models_dba: dict[str, type],
    bigint_schema_sync: None,
    request: "FixtureRequest",
) -> Generator[tuple[Session, dict[str, type]], None, None]:
    """Per-test sync session with BigInt data isolation using transactions."""
    if getattr(engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engines don't support BigInt operations")

    # Real database session with transaction isolation
    connection = engine.connect()
    transaction = connection.begin()

    try:
        # Create session bound to this connection
        session = Session(bind=connection, expire_on_commit=False)

        savepoint = None
        if supports_savepoints(engine):
            # Create savepoint for test isolation (PostgreSQL, MySQL, etc.)
            savepoint = connection.begin_nested()

        try:
            # Just yield clean session - no automatic seeding

            yield session, bigint_models_dba

        finally:
            # Cleanup in proper order
            try:
                session.rollback()
            except Exception:
                pass

            try:
                session.close()
            except Exception:
                pass

            if savepoint and savepoint.is_active:
                try:
                    savepoint.rollback()
                except Exception:
                    pass

    finally:
        # Rollback the main transaction and close connection
        try:
            if transaction.is_active:
                transaction.rollback()
        except Exception:
            pass

        try:
            connection.close()
        except Exception:
            pass


@pytest_asyncio.fixture(loop_scope="function")
async def uuid_test_session_async(
    async_engine: AsyncEngine,
    uuid_models_dba: dict[str, type],
    uuid_schema_async: None,
    request: "FixtureRequest",
) -> AsyncGenerator[tuple[AsyncSession, dict[str, type]], None]:
    """Per-test async session with UUID data isolation using transactions."""
    if getattr(async_engine.dialect, "name", "") == "mock":
        # Mock engine handling
        from unittest.mock import create_autospec

        session_mock = create_autospec(AsyncSession, instance=True)
        session_mock.bind = async_engine
        yield session_mock, uuid_models_dba
        return

    # Real database session with transaction isolation
    connection = await async_engine.connect()
    transaction = await connection.begin()

    try:
        # Create session bound to this connection
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
        session = session_factory()

        savepoint = None
        if supports_savepoints(async_engine):
            # Create savepoint for test isolation (PostgreSQL, MySQL, etc.)
            savepoint = await connection.begin_nested()

        try:
            # Just yield clean session - no automatic seeding

            yield session, uuid_models_dba

        finally:
            # Cleanup in proper order
            try:
                await session.rollback()
            except Exception:
                pass

            try:
                await session.close()
            except Exception:
                pass

            if savepoint and savepoint.is_active:
                try:
                    await savepoint.rollback()
                except Exception:
                    pass

    finally:
        # Rollback the main transaction and close connection
        try:
            if transaction.is_active:
                await transaction.rollback()
        except Exception:
            pass

        try:
            await connection.close()
        except Exception:
            pass


@pytest_asyncio.fixture(loop_scope="function")
async def bigint_test_session_async(
    async_engine: AsyncEngine,
    bigint_models_dba: dict[str, type],
    bigint_schema_async: None,
    request: "FixtureRequest",
) -> AsyncGenerator[tuple[AsyncSession, dict[str, type]], None]:
    """Per-test async session with BigInt data isolation using transactions."""
    if getattr(async_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engines don't support BigInt operations")

    # Real database session with transaction isolation
    connection = await async_engine.connect()
    transaction = await connection.begin()

    try:
        # Create session bound to this connection
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(bind=connection, expire_on_commit=False)
        session = session_factory()

        savepoint = None
        if supports_savepoints(async_engine):
            # Create savepoint for test isolation (PostgreSQL, MySQL, etc.)
            savepoint = await connection.begin_nested()

        try:
            # Just yield clean session - no automatic seeding

            yield session, bigint_models_dba

        finally:
            # Cleanup in proper order
            try:
                await session.rollback()
            except Exception:
                pass

            try:
                await session.close()
            except Exception:
                pass

            if savepoint and savepoint.is_active:
                try:
                    await savepoint.rollback()
                except Exception:
                    pass

    finally:
        # Rollback the main transaction and close connection
        try:
            if transaction.is_active:
                await transaction.rollback()
        except Exception:
            pass

        try:
            await connection.close()
        except Exception:
            pass


# ============================================================================
# Unified Fixtures for Test Consumption
# ============================================================================


@pytest.fixture(params=["uuid", "bigint"])
def repository_pk_type(request: "FixtureRequest") -> str:
    """Determine which primary key type to use for repository tests."""
    pk_type = str(request.param)

    # Skip BigInt tests for engines that don't support them well
    if pk_type == "bigint":
        fixture_names = request.fixturenames
        if any("cockroach" in name or "spanner" in name for name in fixture_names):
            pytest.skip(f"BigInt primary keys not supported for {pk_type}")

    return pk_type


@pytest.fixture
def test_session_sync(
    repository_pk_type: str,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
    bigint_test_session_sync: tuple[Session, dict[str, type]],
) -> tuple[Session, dict[str, type]]:
    """Get the appropriate session and models for sync tests based on PK type."""
    if repository_pk_type == "uuid":
        return uuid_test_session_sync
    return bigint_test_session_sync


@pytest_asyncio.fixture(loop_scope="function")
async def test_session_async(
    repository_pk_type: str,
    uuid_test_session_async: tuple[AsyncSession, dict[str, type]],
    bigint_test_session_async: tuple[AsyncSession, dict[str, type]],
) -> tuple[AsyncSession, dict[str, type]]:
    """Get the appropriate session and models for async tests based on PK type."""
    if repository_pk_type == "uuid":
        return uuid_test_session_async
    return bigint_test_session_async


# ============================================================================
# Legacy Compatibility Fixtures
# ============================================================================


# Keep these for backward compatibility during migration
@pytest.fixture(scope="session")
def uuid_models(request: "FixtureRequest") -> dict[str, type]:
    """Get all UUID models for the current worker."""
    worker_id = get_worker_id(request)
    return RepositoryModelRegistry.get_uuid_models(worker_id)


@pytest.fixture(scope="session")
def bigint_models(request: "FixtureRequest") -> dict[str, type]:
    """Get all BigInt models for the current worker."""
    worker_id = get_worker_id(request)
    return RepositoryModelRegistry.get_bigint_models(worker_id)


# Individual model fixtures for backward compatibility
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


# ============================================================================
# Data Seeding Helpers
# ============================================================================


async def seed_test_data_async(session: AsyncSession, models: "dict[str, type]", pk_type: str) -> None:
    """Simple helper to seed test data when needed - call this in tests that need data."""
    seed_data = TestDataManager.get_seed_data(pk_type)

    # Insert fresh seed data
    if "author" in models:
        await session.execute(insert(models["author"]), seed_data["authors"])
    if "rule" in models:
        await session.execute(insert(models["rule"]), seed_data["rules"])
    if "secret" in models:
        await session.execute(insert(models["secret"]), seed_data["secrets"])
    await session.flush()  # Ensure data is written but don't commit yet


def seed_test_data_sync(session: Session, models: "dict[str, type]", pk_type: str) -> None:
    """Simple helper to seed test data when needed - call this in tests that need data."""
    seed_data = TestDataManager.get_seed_data(pk_type)

    # Insert fresh seed data
    if "author" in models:
        session.execute(insert(models["author"]), seed_data["authors"])
    if "rule" in models:
        session.execute(insert(models["rule"]), seed_data["rules"])
    if "secret" in models:
        session.execute(insert(models["secret"]), seed_data["secrets"])
    session.flush()  # Ensure data is written but don't commit yet


@pytest_asyncio.fixture(loop_scope="function")
async def seeded_test_session_async(
    test_session_async: "tuple[AsyncSession, dict[str, type]]", repository_pk_type: str
) -> "tuple[AsyncSession, dict[str, type]]":
    """Auto-seeded async session for tests that need data."""
    session, models = test_session_async
    await seed_test_data_async(session, models, repository_pk_type)
    return session, models


@pytest.fixture
def seeded_test_session_sync(
    test_session_sync: "tuple[Session, dict[str, type]]", repository_pk_type: str
) -> "tuple[Session, dict[str, type]]":
    """Auto-seeded sync session for tests that need data."""
    session, models = test_session_sync
    seed_test_data_sync(session, models, repository_pk_type)
    return session, models

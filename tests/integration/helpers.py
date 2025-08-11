from __future__ import annotations

import asyncio
import datetime
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union, cast

import pytest
from sqlalchemy import Engine, MetaData, NullPool, create_engine, exc, insert, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.orm import DeclarativeBase

from advanced_alchemy.exceptions import RepositoryError

# Note: cleanup utilities are implemented within this module below.

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Sequence

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


__all__ = (
    "AsyncCockroachDBCleaner",
    "AsyncDatabaseCleaner",
    "AsyncDuckDBCleaner",
    "AsyncMSSQLCleaner",
    "AsyncMySQLCleaner",
    "AsyncOracleCleaner",
    "AsyncPostgreSQLCleaner",
    "AsyncSQLiteCleaner",
    "AsyncSpannerCleaner",
    "CleanupError",
    "CleanupStats",
    "CockroachDBCleaner",
    "DatabaseCleaner",
    "DuckDBCleaner",
    "MSSQLCleaner",
    "MySQLCleaner",
    "OracleCleaner",
    "PostgreSQLCleaner",
    "SQLiteCleaner",
    "SpannerCleaner",
    "SyncDatabaseCleaner",
    "async_clean_tables",
    "clean_tables",
    "cleanup_database",
)

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    """Statistics from database cleanup operation.

    Attributes:
        tables_cleaned: Number of tables that were cleaned
        duration_seconds: Total time taken for cleanup
        strategy_used: The cleanup strategy that was applied
        fallback_used: Whether fallback strategy was used
        errors_encountered: Number of errors encountered during cleanup
    """

    tables_cleaned: int = 0
    duration_seconds: float = 0.0
    strategy_used: str = ""
    fallback_used: bool = False
    errors_encountered: int = 0


class CleanupError(RepositoryError):
    """Error occurred during database cleanup.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class DatabaseCleaner(ABC):
    """Abstract base class for database cleanup strategies.

    Each database engine has unique requirements for efficient data cleanup.
    This class defines the interface that all concrete cleaners must implement.

    Args:
        connection: Database connection to use for cleanup
        exclude_tables: Tables to exclude from cleanup
        include_only: Only clean these tables (if specified)
        verify_cleanup: Whether to verify tables are actually clean
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    """

    def __init__(
        self,
        connection: Union[Connection, AsyncConnection],
        exclude_tables: Optional[Sequence[str]] = None,
        include_only: Optional[Sequence[str]] = None,
        verify_cleanup: bool = True,
        max_retries: int = 3,
        retry_delay: float = 0.1,
    ) -> None:
        self.connection = connection
        self.exclude_tables = set(exclude_tables or [])
        self.include_only = set(include_only or []) if include_only else None
        self.verify_cleanup = verify_cleanup
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.stats = CleanupStats()

    @property
    @abstractmethod
    def dialect_name(self) -> str:
        """The SQLAlchemy dialect name this cleaner handles."""

    @abstractmethod
    def cleanup(self) -> CleanupStats:
        """Perform database cleanup and return statistics.

        Returns:
            CleanupStats: Statistics about the cleanup operation

        Raises:
            CleanupError: If cleanup fails after all retry attempts
        """

    @abstractmethod
    def get_table_list(self) -> Sequence[str]:
        """Get list of tables to clean, respecting include/exclude filters.

        Returns:
            Sequence[str]: List of table names to clean

        Raises:
            CleanupError: If unable to retrieve table list
        """

    @abstractmethod
    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """Resolve foreign key dependencies for proper cleanup order.

        Args:
            tables: List of table names to order

        Returns:
            Sequence[str]: Tables ordered by dependencies (leaves first)

        Raises:
            CleanupError: If unable to resolve dependencies
        """


class SyncDatabaseCleaner(DatabaseCleaner):
    """Synchronous database cleaner base class."""

    def __init__(
        self,
        connection: Connection,
        exclude_tables: Optional[Sequence[str]] = None,
        include_only: Optional[Sequence[str]] = None,
        verify_cleanup: bool = True,
        max_retries: int = 3,
        retry_delay: float = 0.1,
    ) -> None:
        super().__init__(connection, exclude_tables, include_only, verify_cleanup, max_retries, retry_delay)
        # Narrow the connection attribute to the concrete sync type for mypy
        self.connection: Connection = connection


class AsyncDatabaseCleaner(DatabaseCleaner):
    """Asynchronous database cleaner base class."""

    def __init__(
        self,
        connection: AsyncConnection,
        exclude_tables: Optional[Sequence[str]] = None,
        include_only: Optional[Sequence[str]] = None,
        verify_cleanup: bool = True,
        max_retries: int = 3,
        retry_delay: float = 0.1,
    ) -> None:
        super().__init__(connection, exclude_tables, include_only, verify_cleanup, max_retries, retry_delay)
        # Narrow the connection attribute to the concrete async type for mypy
        self.connection: AsyncConnection = connection

    async def cleanup(self) -> CleanupStats:  # type: ignore[override]
        """Perform async database cleanup and return statistics.

        Returns:
            CleanupStats: Statistics about the cleanup operation

        Raises:
            CleanupError: If cleanup fails after all retry attempts
        """
        return await self._perform_cleanup()

    @abstractmethod
    async def _perform_cleanup(self) -> CleanupStats:
        """Internal method to perform the actual cleanup."""

    @abstractmethod
    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of tables to clean asynchronously.

        Returns:
            Sequence[str]: List of table names to clean

        Raises:
            CleanupError: If unable to retrieve table list
        """

    @abstractmethod
    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """Resolve foreign key dependencies asynchronously.

        Args:
            tables: List of table names to order

        Returns:
            Sequence[str]: Tables ordered by dependencies (leaves first)

        Raises:
            CleanupError: If unable to resolve dependencies
        """


class PostgreSQLCleaner(SyncDatabaseCleaner):
    """PostgreSQL/CockroachDB synchronous cleaner using TRUNCATE CASCADE with sequence reset."""

    @property
    def dialect_name(self) -> str:
        return "postgresql"

    def cleanup(self) -> CleanupStats:
        """Clean PostgreSQL database using TRUNCATE CASCADE with sequence reset."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE CASCADE with sequence reset"

        try:
            tables = self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            # Resolve dependencies for proper order
            ordered_tables = self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            # Perform cleanup with retry logic
            for attempt in range(self.max_retries + 1):
                try:
                    self._perform_truncate_cascade(ordered_tables)
                    self._reset_sequences()
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"PostgreSQL cleanup failed after {self.max_retries} attempts: {e}")
                        self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"PostgreSQL cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        time.sleep(self.retry_delay * (2**attempt))  # Exponential backoff

            if self.verify_cleanup:
                self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"PostgreSQL cleanup failed: {e}")
            raise CleanupError(f"postgresql cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    def get_table_list(self) -> Sequence[str]:
        """Get list of PostgreSQL tables to clean."""
        try:
            inspector = inspect(self.connection)
            all_tables = inspector.get_table_names()

            # Apply filters
            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """Resolve PostgreSQL foreign key dependencies using topological sort."""
        try:
            # For PostgreSQL, TRUNCATE CASCADE handles dependencies automatically
            # But we still want to order by dependencies for better error handling
            inspector = inspect(self.connection)
            dependency_graph: dict[str, list[str]] = {}

            for table in tables:
                foreign_keys = inspector.get_foreign_keys(table)
                dependencies = [
                    fk["referred_table"]
                    for fk in foreign_keys
                    if fk["referred_table"] in tables and fk["referred_table"] != table
                ]
                dependency_graph[table] = dependencies

            # Topological sort to handle dependencies
            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    def _perform_truncate_cascade(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE CASCADE on PostgreSQL tables."""
        if not tables:
            return

        # Use TRUNCATE CASCADE to handle all dependencies at once
        table_list = ", ".join(f'"{table}"' for table in tables)
        # CockroachDB doesn't support RESTART IDENTITY
        if "cockroach" in str(self.connection.engine.url).lower():
            sql = f"TRUNCATE TABLE {table_list} CASCADE"
        else:
            sql = f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"

        logger.debug(f"Executing: {sql}")
        self.connection.execute(text(sql))
        self.connection.commit()

    def _reset_sequences(self) -> None:
        """Reset PostgreSQL sequences to start from 1."""
        # Skip sequence reset for CockroachDB as it doesn't support ALTER SEQUENCE ... RESTART
        if "cockroach" in str(self.connection.engine.url).lower():
            return

        try:
            # Get all sequences and reset them
            result = self.connection.execute(
                text("""
                SELECT schemaname, sequencename
                FROM pg_sequences
                WHERE schemaname = 'public'
            """)
            )

            for row in result:
                seq_name = f'"{row[0]}"."{row[1]}"'
                self.connection.execute(text(f"ALTER SEQUENCE {seq_name} RESTART WITH 1"))

            self.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to reset sequences: {e}")

    def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE statements if TRUNCATE fails."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        # Delete in reverse dependency order
        for table in reversed(tables):
            try:
                self.connection.execute(text(f'DELETE FROM "{table}"'))
                self.connection.commit()
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1
                # Rollback the failed transaction to prevent "current transaction is aborted" errors
                try:
                    self.connection.rollback()
                except Exception:
                    pass  # Ignore rollback errors

    def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are actually empty."""
        for table in tables:
            try:
                result = self.connection.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort to resolve dependency order."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        # Calculate in-degrees
        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        # Queue nodes with no dependencies
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            # Reduce in-degree for neighbors
            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class AsyncPostgreSQLCleaner(AsyncDatabaseCleaner):
    """PostgreSQL/CockroachDB asynchronous cleaner using TRUNCATE CASCADE with sequence reset."""

    @property
    def dialect_name(self) -> str:
        return "postgresql"

    async def _perform_cleanup(self) -> CleanupStats:
        """Clean PostgreSQL database asynchronously using TRUNCATE CASCADE."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE CASCADE with sequence reset"

        try:
            tables = await self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            # Resolve dependencies for proper order
            ordered_tables = await self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            # Perform cleanup with retry logic
            for attempt in range(self.max_retries + 1):
                try:
                    await self._perform_truncate_cascade(ordered_tables)
                    await self._reset_sequences()
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"Async PostgreSQL cleanup failed after {self.max_retries} attempts: {e}")
                        await self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"Async PostgreSQL cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        await asyncio.sleep(self.retry_delay * (2**attempt))

            if self.verify_cleanup:
                await self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Async PostgreSQL cleanup failed: {e}")
            raise CleanupError(f"async postgresql cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of PostgreSQL tables to clean asynchronously."""
        try:
            # Use async connection to get table names
            result = await self.connection.execute(
                text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
            """)
            )
            all_tables = [row[0] for row in result]

            # Apply filters
            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """Resolve PostgreSQL foreign key dependencies asynchronously."""
        try:
            # Get foreign key information
            result = await self.connection.execute(
                text("""
                SELECT
                    tc.table_name,
                    ccu.table_name AS foreign_table_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, foreign_table = row[0], row[1]
                if table in dependency_graph and foreign_table in tables and foreign_table != table:
                    dependency_graph[table].append(foreign_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    async def _perform_truncate_cascade(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE CASCADE on PostgreSQL tables asynchronously."""
        if not tables:
            return

        table_list = ", ".join(f'"{table}"' for table in tables)
        # CockroachDB doesn't support RESTART IDENTITY
        # For async connections, check the dialect name directly
        if self.dialect_name == "cockroach":
            sql = f"TRUNCATE TABLE {table_list} CASCADE"
        else:
            sql = f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"

        logger.debug(f"Executing: {sql}")
        await self.connection.execute(text(sql))
        await self.connection.commit()

    async def _reset_sequences(self) -> None:
        """Reset PostgreSQL sequences asynchronously."""
        # Skip sequence reset for CockroachDB as it doesn't support ALTER SEQUENCE ... RESTART
        if self.dialect_name == "cockroach":
            return

        try:
            result = await self.connection.execute(
                text("""
                SELECT schemaname, sequencename
                FROM pg_sequences
                WHERE schemaname = 'public'
            """)
            )

            for row in result:
                seq_name = f'"{row[0]}"."{row[1]}"'
                await self.connection.execute(text(f"ALTER SEQUENCE {seq_name} RESTART WITH 1"))

            await self.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to reset sequences: {e}")

    async def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE statements if TRUNCATE fails."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        for table in reversed(tables):
            try:
                await self.connection.execute(text(f'DELETE FROM "{table}"'))
                await self.connection.commit()
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1
                # Rollback the failed transaction to prevent "current transaction is aborted" errors
                try:
                    await self.connection.rollback()
                except Exception:
                    pass  # Ignore rollback errors

    async def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are actually empty asynchronously."""
        for table in tables:
            try:
                # Start a new transaction for verification
                await self.connection.rollback()  # Clear any aborted transaction
                result = await self.connection.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort to resolve dependency order."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class CockroachDBCleaner(PostgreSQLCleaner):
    """CockroachDB cleaner - extends PostgreSQL cleaner with CockroachDB-specific optimizations."""

    @property
    def dialect_name(self) -> str:
        return "cockroach"


class AsyncCockroachDBCleaner(AsyncPostgreSQLCleaner):
    """Async CockroachDB cleaner - extends async PostgreSQL cleaner."""

    @property
    def dialect_name(self) -> str:
        return "cockroach"


class SQLiteCleaner(SyncDatabaseCleaner):
    """SQLite synchronous cleaner using DELETE with sqlite_sequence cleanup."""

    @property
    def dialect_name(self) -> str:
        return "sqlite"

    def cleanup(self) -> CleanupStats:
        """Clean SQLite database using DELETE with sequence cleanup."""
        start_time = time.time()
        self.stats.strategy_used = "DELETE with sequence cleanup"

        try:
            tables = self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            # SQLite doesn't support TRUNCATE, use DELETE
            self._perform_delete(ordered_tables)
            self._reset_autoincrement()

            if self.verify_cleanup:
                self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"SQLite cleanup failed: {e}")
            raise CleanupError(f"sqlite cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    def get_table_list(self) -> Sequence[str]:
        """Get list of SQLite tables to clean."""
        try:
            result = self.connection.execute(
                text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """Resolve SQLite foreign key dependencies."""
        try:
            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}

            for table in tables:
                result = self.connection.execute(text(f"PRAGMA foreign_key_list({table})"))
                for row in result:
                    foreign_table = row[2]  # referenced table
                    if foreign_table in tables and foreign_table != table:
                        dependency_graph[table].append(foreign_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    def _perform_delete(self, tables: Sequence[str]) -> None:
        """Perform DELETE operations on SQLite tables."""
        # Disable foreign key checks temporarily
        self.connection.execute(text("PRAGMA foreign_keys = OFF"))

        # Set more aggressive locking timeout for better concurrency
        self.connection.execute(text("PRAGMA busy_timeout = 30000"))  # 30 seconds

        # Try to set WAL mode, but ignore if it fails (e.g., database locked)
        try:
            self.connection.execute(text("PRAGMA journal_mode = WAL"))  # Write-Ahead Logging mode
        except Exception as e:
            logger.debug(f"Could not set WAL mode: {e}")

        try:
            # Delete in reverse dependency order
            for table in reversed(tables):
                for attempt in range(self.max_retries):
                    try:
                        # Check if we're in a transaction and commit/rollback if needed
                        if self.connection.in_transaction():
                            try:
                                self.connection.commit()
                            except Exception:
                                self.connection.rollback()

                        self.connection.execute(text(f"DELETE FROM {table}"))

                        # Commit immediately after each DELETE to release locks
                        if self.connection.in_transaction():
                            self.connection.commit()
                        break
                    except Exception as e:
                        if "database is locked" in str(e) and attempt < self.max_retries - 1:
                            logger.warning(f"Database locked on table {table}, retrying in {self.retry_delay}s...")
                            # Rollback any pending transaction
                            try:
                                if self.connection.in_transaction():
                                    self.connection.rollback()
                            except Exception:
                                pass
                            # Exponential backoff
                            time.sleep(self.retry_delay * (2**attempt))
                        else:
                            raise

        finally:
            # Re-enable foreign key checks
            self.connection.execute(text("PRAGMA foreign_keys = ON"))

    def _reset_autoincrement(self) -> None:
        """Reset SQLite autoincrement sequences."""
        try:
            # Clear sqlite_sequence table to reset autoincrement counters
            if self.connection.in_transaction():
                try:
                    self.connection.commit()
                except Exception:
                    self.connection.rollback()

            self.connection.execute(text("DELETE FROM sqlite_sequence"))
            if self.connection.in_transaction():
                self.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to reset autoincrement: {e}")

    def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are actually empty."""
        for table in tables:
            try:
                result = self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for SQLite dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class AsyncSQLiteCleaner(AsyncDatabaseCleaner):
    """SQLite asynchronous cleaner using DELETE with sequence cleanup."""

    @property
    def dialect_name(self) -> str:
        return "sqlite"

    async def _perform_cleanup(self) -> CleanupStats:
        """Clean SQLite database asynchronously."""
        start_time = time.time()
        self.stats.strategy_used = "DELETE with sequence cleanup"

        try:
            tables = await self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = await self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            await self._perform_delete(ordered_tables)
            await self._reset_autoincrement()

            if self.verify_cleanup:
                await self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Async SQLite cleanup failed: {e}")
            raise CleanupError(f"async sqlite cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of SQLite tables to clean asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """Resolve SQLite foreign key dependencies asynchronously."""
        try:
            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}

            for table in tables:
                result = await self.connection.execute(text(f"PRAGMA foreign_key_list({table})"))
                for row in result:
                    foreign_table = row[2]
                    if foreign_table in tables and foreign_table != table:
                        dependency_graph[table].append(foreign_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    async def _perform_delete(self, tables: Sequence[str]) -> None:
        """Perform DELETE operations asynchronously."""
        await self.connection.execute(text("PRAGMA foreign_keys = OFF"))

        try:
            for table in reversed(tables):
                for attempt in range(self.max_retries):
                    try:
                        await self.connection.execute(text(f"DELETE FROM {table}"))
                        break
                    except Exception as e:
                        if "database is locked" in str(e) and attempt < self.max_retries - 1:
                            logger.warning(f"Database locked on table {table}, retrying in {self.retry_delay}s...")
                            await asyncio.sleep(self.retry_delay)
                        else:
                            raise

            await self.connection.commit()
        finally:
            await self.connection.execute(text("PRAGMA foreign_keys = ON"))

    async def _reset_autoincrement(self) -> None:
        """Reset SQLite autoincrement sequences asynchronously."""
        try:
            await self.connection.execute(text("DELETE FROM sqlite_sequence"))
            await self.connection.commit()
        except Exception as e:
            logger.warning(f"Failed to reset autoincrement: {e}")

    async def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty asynchronously."""
        for table in tables:
            try:
                result = await self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class MySQLCleaner(SyncDatabaseCleaner):
    """MySQL/MariaDB synchronous cleaner using TRUNCATE with FK bypass and AUTO_INCREMENT reset."""

    @property
    def dialect_name(self) -> str:
        return "mysql"

    def cleanup(self) -> CleanupStats:
        """Clean MySQL database using TRUNCATE with foreign key bypass."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE with FK bypass and AUTO_INCREMENT reset"

        try:
            tables = self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            # MySQL cleanup with retry
            for attempt in range(self.max_retries + 1):
                try:
                    self._perform_truncate(ordered_tables)
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"MySQL cleanup failed after {self.max_retries} attempts: {e}")
                        self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"MySQL cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        time.sleep(self.retry_delay * (2**attempt))

            if self.verify_cleanup:
                self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"MySQL cleanup failed: {e}")
            raise CleanupError(f"mysql cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    def get_table_list(self) -> Sequence[str]:
        """Get list of MySQL tables to clean."""
        try:
            result = self.connection.execute(
                text("""
                SELECT TABLE_NAME FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """Resolve MySQL foreign key dependencies."""
        try:
            result = self.connection.execute(
                text("""
                SELECT
                    TABLE_NAME,
                    REFERENCED_TABLE_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                    AND REFERENCED_TABLE_NAME IS NOT NULL
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, referenced_table = row[0], row[1]
                if table in dependency_graph and referenced_table in tables and referenced_table != table:
                    dependency_graph[table].append(referenced_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    def _perform_truncate(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE operations on MySQL tables."""
        # Disable foreign key checks
        self.connection.execute(text("SET foreign_key_checks = 0"))

        try:
            for table in tables:
                self.connection.execute(text(f"TRUNCATE TABLE `{table}`"))

            self.connection.commit()
        finally:
            # Re-enable foreign key checks
            self.connection.execute(text("SET foreign_key_checks = 1"))

    def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE if TRUNCATE fails."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        self.connection.execute(text("SET foreign_key_checks = 0"))

        try:
            for table in reversed(tables):
                try:
                    self.connection.execute(text(f"DELETE FROM `{table}`"))
                    # Reset AUTO_INCREMENT manually
                    self.connection.execute(text(f"ALTER TABLE `{table}` AUTO_INCREMENT = 1"))
                except Exception as e:
                    logger.error(f"Failed to delete from {table}: {e}")
                    self.stats.errors_encountered += 1

            self.connection.commit()
        finally:
            self.connection.execute(text("SET foreign_key_checks = 1"))

    def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty."""
        for table in tables:
            try:
                result = self.connection.execute(text(f"SELECT COUNT(*) FROM `{table}`"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class AsyncMySQLCleaner(AsyncDatabaseCleaner):
    """MySQL/MariaDB asynchronous cleaner using TRUNCATE with FK bypass."""

    @property
    def dialect_name(self) -> str:
        return "mysql"

    async def _perform_cleanup(self) -> CleanupStats:
        """Clean MySQL database asynchronously."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE with FK bypass and AUTO_INCREMENT reset"

        try:
            tables = await self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = await self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            for attempt in range(self.max_retries + 1):
                try:
                    await self._perform_truncate(ordered_tables)
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"Async MySQL cleanup failed after {self.max_retries} attempts: {e}")
                        await self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"Async MySQL cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        await asyncio.sleep(self.retry_delay * (2**attempt))

            if self.verify_cleanup:
                await self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Async MySQL cleanup failed: {e}")
            raise CleanupError(f"async mysql cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of MySQL tables asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT TABLE_NAME FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """Resolve MySQL foreign key dependencies asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT
                    TABLE_NAME,
                    REFERENCED_TABLE_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                    AND REFERENCED_TABLE_NAME IS NOT NULL
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, referenced_table = row[0], row[1]
                if table in dependency_graph and referenced_table in tables and referenced_table != table:
                    dependency_graph[table].append(referenced_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    async def _perform_truncate(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE operations asynchronously."""
        await self.connection.execute(text("SET foreign_key_checks = 0"))

        try:
            for table in tables:
                await self.connection.execute(text(f"TRUNCATE TABLE `{table}`"))

            await self.connection.commit()
        finally:
            await self.connection.execute(text("SET foreign_key_checks = 1"))

    async def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE if TRUNCATE fails."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        await self.connection.execute(text("SET foreign_key_checks = 0"))

        try:
            for table in reversed(tables):
                try:
                    await self.connection.execute(text(f"DELETE FROM `{table}`"))
                    await self.connection.execute(text(f"ALTER TABLE `{table}` AUTO_INCREMENT = 1"))
                except Exception as e:
                    logger.error(f"Failed to delete from {table}: {e}")
                    self.stats.errors_encountered += 1

            await self.connection.commit()
        finally:
            await self.connection.execute(text("SET foreign_key_checks = 1"))

    async def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty asynchronously."""
        for table in tables:
            try:
                result = await self.connection.execute(text(f"SELECT COUNT(*) FROM `{table}`"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class OracleCleaner(SyncDatabaseCleaner):
    """Oracle synchronous cleaner using TRUNCATE with constraint management."""

    @property
    def dialect_name(self) -> str:
        return "oracle"

    def cleanup(self) -> CleanupStats:
        """Clean Oracle database using TRUNCATE with constraint management."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE with constraint management"

        try:
            tables = self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            for attempt in range(self.max_retries + 1):
                try:
                    self._perform_truncate(ordered_tables)
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"Oracle cleanup failed after {self.max_retries} attempts: {e}")
                        self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"Oracle cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        time.sleep(self.retry_delay * (2**attempt))

            if self.verify_cleanup:
                self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Oracle cleanup failed: {e}")
            raise CleanupError(f"oracle cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    def get_table_list(self) -> Sequence[str]:
        """Get list of Oracle tables to clean."""
        try:
            result = self.connection.execute(
                text("""
                SELECT table_name FROM user_tables
                WHERE table_name NOT LIKE 'SYS_%'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """Resolve Oracle foreign key dependencies."""
        try:
            result = self.connection.execute(
                text("""
                SELECT
                    a.table_name,
                    c.table_name as referenced_table
                FROM user_constraints a
                JOIN user_cons_columns b ON a.constraint_name = b.constraint_name
                JOIN user_constraints c ON a.r_constraint_name = c.constraint_name
                WHERE a.constraint_type = 'R'
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, referenced_table = row[0], row[1]
                if table in dependency_graph and referenced_table in tables and referenced_table != table:
                    dependency_graph[table].append(referenced_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    def _perform_truncate(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE operations on Oracle tables."""
        for table in reversed(tables):
            try:
                self.connection.execute(text(f"TRUNCATE TABLE {table}"))
            except Exception as e:
                logger.warning(f"Failed to truncate {table}: {e}")
                # Try DELETE as fallback for this table
                self.connection.execute(text(f"DELETE FROM {table}"))

        self.connection.commit()

    def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE for Oracle tables."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        for table in reversed(tables):
            try:
                self.connection.execute(text(f"DELETE FROM {table}"))
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1

        self.connection.commit()

    def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty."""
        for table in tables:
            try:
                result = self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class AsyncOracleCleaner(AsyncDatabaseCleaner):
    """Oracle asynchronous cleaner using TRUNCATE with constraint management."""

    @property
    def dialect_name(self) -> str:
        return "oracle"

    async def _perform_cleanup(self) -> CleanupStats:
        """Clean Oracle database asynchronously."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE with constraint management"

        try:
            tables = await self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = await self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            for attempt in range(self.max_retries + 1):
                try:
                    await self._perform_truncate(ordered_tables)
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"Async Oracle cleanup failed after {self.max_retries} attempts: {e}")
                        await self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"Async Oracle cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        await asyncio.sleep(self.retry_delay * (2**attempt))

            if self.verify_cleanup:
                await self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Async Oracle cleanup failed: {e}")
            raise CleanupError(f"async oracle cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of Oracle tables asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT table_name FROM user_tables
                WHERE table_name NOT LIKE 'SYS_%'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """Resolve Oracle foreign key dependencies asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT
                    a.table_name,
                    c.table_name as referenced_table
                FROM user_constraints a
                JOIN user_cons_columns b ON a.constraint_name = b.constraint_name
                JOIN user_constraints c ON a.r_constraint_name = c.constraint_name
                WHERE a.constraint_type = 'R'
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, referenced_table = row[0], row[1]
                if table in dependency_graph and referenced_table in tables and referenced_table != table:
                    dependency_graph[table].append(referenced_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    async def _perform_truncate(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE operations asynchronously."""
        for table in reversed(tables):
            try:
                await self.connection.execute(text(f"TRUNCATE TABLE {table}"))
            except Exception as e:
                logger.warning(f"Failed to truncate {table}: {e}")
                await self.connection.execute(text(f"DELETE FROM {table}"))

        await self.connection.commit()

    async def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE for Oracle tables."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        for table in reversed(tables):
            try:
                await self.connection.execute(text(f"DELETE FROM {table}"))
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1

        await self.connection.commit()

    async def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty asynchronously."""
        for table in tables:
            try:
                result = await self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class MSSQLCleaner(SyncDatabaseCleaner):
    """MS SQL Server synchronous cleaner using TRUNCATE with IDENTITY reset."""

    @property
    def dialect_name(self) -> str:
        return "mssql"

    def cleanup(self) -> CleanupStats:
        """Clean MS SQL Server database using TRUNCATE with IDENTITY reset."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE with IDENTITY reset"

        try:
            tables = self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            for attempt in range(self.max_retries + 1):
                try:
                    self._perform_truncate(ordered_tables)
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"MSSQL cleanup failed after {self.max_retries} attempts: {e}")
                        self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"MSSQL cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        time.sleep(self.retry_delay * (2**attempt))

            if self.verify_cleanup:
                self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"MSSQL cleanup failed: {e}")
            raise CleanupError(f"mssql cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    def get_table_list(self) -> Sequence[str]:
        """Get list of MS SQL Server tables to clean."""
        try:
            result = self.connection.execute(
                text("""
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = 'dbo'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """Resolve MS SQL Server foreign key dependencies."""
        try:
            result = self.connection.execute(
                text("""
                SELECT
                    fk.TABLE_NAME,
                    fk.REFERENCED_TABLE_NAME
                FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS fk
                    ON rc.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS pk
                    ON rc.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
                WHERE fk.TABLE_SCHEMA = 'dbo'
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, referenced_table = row[0], row[1]
                if table in dependency_graph and referenced_table in tables and referenced_table != table:
                    dependency_graph[table].append(referenced_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    def _perform_truncate(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE operations on MS SQL Server tables."""
        # Disable foreign key constraints
        self.connection.execute(text("EXEC sp_MSForEachTable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL'"))

        try:
            for table in reversed(tables):
                try:
                    # Try TRUNCATE first (resets IDENTITY automatically)
                    self.connection.execute(text(f"TRUNCATE TABLE [{table}]"))
                except Exception as e:
                    logger.warning(f"Failed to truncate {table}: {e}, using DELETE")
                    # Fallback to DELETE with manual IDENTITY reset
                    self.connection.execute(text(f"DELETE FROM [{table}]"))
                    self.connection.execute(text(f"DBCC CHECKIDENT('{table}', RESEED, 0)"))

            self.connection.commit()
        finally:
            # Re-enable foreign key constraints
            self.connection.execute(text("EXEC sp_MSForEachTable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL'"))

    def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE for MS SQL Server tables."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        for table in reversed(tables):
            try:
                self.connection.execute(text(f"DELETE FROM [{table}]"))
                self.connection.execute(text(f"DBCC CHECKIDENT('{table}', RESEED, 0)"))
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1

        self.connection.commit()

    def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty."""
        for table in tables:
            try:
                result = self.connection.execute(text(f"SELECT COUNT(*) FROM [{table}]"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class AsyncMSSQLCleaner(AsyncDatabaseCleaner):
    """MS SQL Server asynchronous cleaner using TRUNCATE with IDENTITY reset."""

    @property
    def dialect_name(self) -> str:
        return "mssql"

    async def _perform_cleanup(self) -> CleanupStats:
        """Clean MS SQL Server database asynchronously."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE with IDENTITY reset"

        try:
            tables = await self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = await self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            for attempt in range(self.max_retries + 1):
                try:
                    await self._perform_truncate(ordered_tables)
                    break
                except exc.SQLAlchemyError as e:
                    self.stats.errors_encountered += 1
                    if attempt == self.max_retries:
                        logger.error(f"Async MSSQL cleanup failed after {self.max_retries} attempts: {e}")
                        await self._fallback_delete(ordered_tables)
                        self.stats.fallback_used = True
                    else:
                        logger.warning(f"Async MSSQL cleanup attempt {attempt + 1} failed: {e}, retrying...")
                        await asyncio.sleep(self.retry_delay * (2**attempt))

            if self.verify_cleanup:
                await self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Async MSSQL cleanup failed: {e}")
            raise CleanupError(f"async mssql cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of MS SQL Server tables asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = 'dbo'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """Resolve MS SQL Server foreign key dependencies asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT
                    fk.TABLE_NAME,
                    fk.REFERENCED_TABLE_NAME
                FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS fk
                    ON rc.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS pk
                    ON rc.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
                WHERE fk.TABLE_SCHEMA = 'dbo'
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, referenced_table = row[0], row[1]
                if table in dependency_graph and referenced_table in tables and referenced_table != table:
                    dependency_graph[table].append(referenced_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    async def _perform_truncate(self, tables: Sequence[str]) -> None:
        """Perform TRUNCATE operations asynchronously."""
        await self.connection.execute(text("EXEC sp_MSForEachTable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL'"))

        try:
            for table in reversed(tables):
                try:
                    await self.connection.execute(text(f"TRUNCATE TABLE [{table}]"))
                except Exception as e:
                    logger.warning(f"Failed to truncate {table}: {e}, using DELETE")
                    await self.connection.execute(text(f"DELETE FROM [{table}]"))
                    await self.connection.execute(text(f"DBCC CHECKIDENT('{table}', RESEED, 0)"))

            await self.connection.commit()
        finally:
            await self.connection.execute(
                text("EXEC sp_MSForEachTable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL'")
            )

    async def _fallback_delete(self, tables: Sequence[str]) -> None:
        """Fallback to DELETE for MS SQL Server tables."""
        logger.info("Using DELETE fallback strategy")
        self.stats.strategy_used = "DELETE fallback"

        for table in reversed(tables):
            try:
                await self.connection.execute(text(f"DELETE FROM [{table}]"))
                await self.connection.execute(text(f"DBCC CHECKIDENT('{table}', RESEED, 0)"))
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1

        await self.connection.commit()

    async def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty asynchronously."""
        for table in tables:
            try:
                result = await self.connection.execute(text(f"SELECT COUNT(*) FROM [{table}]"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class DuckDBCleaner(SyncDatabaseCleaner):
    """DuckDB synchronous cleaner using simple TRUNCATE/DELETE."""

    @property
    def dialect_name(self) -> str:
        return "duckdb"

    def cleanup(self) -> CleanupStats:
        """Clean DuckDB database using simple TRUNCATE or DELETE."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE/DELETE"

        try:
            tables = self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            self._perform_cleanup_operations(ordered_tables)

            if self.verify_cleanup:
                self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"DuckDB cleanup failed: {e}")
            raise CleanupError(f"duckdb cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    def get_table_list(self) -> Sequence[str]:
        """Get list of DuckDB tables to clean."""
        try:
            result = self.connection.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """For DuckDB, return tables in original order since dependencies are simpler."""
        return list(tables)

    def _perform_cleanup_operations(self, tables: Sequence[str]) -> None:
        """Perform cleanup operations on DuckDB tables."""
        for table in tables:
            try:
                # Try TRUNCATE first
                self.connection.execute(text(f"TRUNCATE TABLE {table}"))
            except Exception as e:
                logger.warning(f"TRUNCATE failed for {table}: {e}, using DELETE")
                try:
                    self.connection.execute(text(f"DELETE FROM {table}"))
                except Exception as delete_e:
                    logger.error(f"Failed to clean table {table}: {delete_e}")
                    self.stats.errors_encountered += 1

        self.connection.commit()

    def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty."""
        for table in tables:
            try:
                result = self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")


class AsyncDuckDBCleaner(AsyncDatabaseCleaner):
    """DuckDB asynchronous cleaner using simple TRUNCATE/DELETE."""

    @property
    def dialect_name(self) -> str:
        return "duckdb"

    async def _perform_cleanup(self) -> CleanupStats:
        """Clean DuckDB database asynchronously."""
        start_time = time.time()
        self.stats.strategy_used = "TRUNCATE/DELETE"

        try:
            tables = await self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = await self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            await self._perform_cleanup_operations(ordered_tables)

            if self.verify_cleanup:
                await self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Async DuckDB cleanup failed: {e}")
            raise CleanupError(f"async duckdb cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of DuckDB tables asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """For DuckDB, return tables in original order."""
        return list(tables)

    async def _perform_cleanup_operations(self, tables: Sequence[str]) -> None:
        """Perform cleanup operations asynchronously."""
        for table in tables:
            try:
                await self.connection.execute(text(f"TRUNCATE TABLE {table}"))
            except Exception as e:
                logger.warning(f"TRUNCATE failed for {table}: {e}, using DELETE")
                try:
                    await self.connection.execute(text(f"DELETE FROM {table}"))
                except Exception as delete_e:
                    logger.error(f"Failed to clean table {table}: {delete_e}")
                    self.stats.errors_encountered += 1

        await self.connection.commit()

    async def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty asynchronously."""
        for table in tables:
            try:
                result = await self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")


class SpannerCleaner(SyncDatabaseCleaner):
    """Google Cloud Spanner synchronous cleaner using DELETE (no TRUNCATE support)."""

    @property
    def dialect_name(self) -> str:
        return "spanner"

    def cleanup(self) -> CleanupStats:
        """Clean Spanner database using DELETE statements."""
        start_time = time.time()
        self.stats.strategy_used = "DELETE (no TRUNCATE support)"

        try:
            tables = self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            self._perform_delete_operations(ordered_tables)

            if self.verify_cleanup:
                self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Spanner cleanup failed: {e}")
            raise CleanupError(f"spanner cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    def get_table_list(self) -> Sequence[str]:
        """Get list of Spanner tables to clean."""
        try:
            result = self.connection.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_catalog = '' AND table_schema = ''
                    AND table_type = 'BASE TABLE'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:
        """Resolve Spanner foreign key dependencies."""
        try:
            # Spanner foreign key information is limited, so we use a simple approach
            result = self.connection.execute(
                text("""
                SELECT
                    tc.table_name,
                    ccu.table_name AS foreign_table_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, foreign_table = row[0], row[1]
                if table in dependency_graph and foreign_table in tables and foreign_table != table:
                    dependency_graph[table].append(foreign_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    def _perform_delete_operations(self, tables: Sequence[str]) -> None:
        """Perform DELETE operations on Spanner tables."""
        # Delete in reverse dependency order
        for table in reversed(tables):
            try:
                self.connection.execute(text(f"DELETE FROM {table} WHERE TRUE"))
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1

        self.connection.commit()

    def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty."""
        for table in tables:
            try:
                result = self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


class AsyncSpannerCleaner(AsyncDatabaseCleaner):
    """Google Cloud Spanner asynchronous cleaner using DELETE statements."""

    @property
    def dialect_name(self) -> str:
        return "spanner"

    async def _perform_cleanup(self) -> CleanupStats:
        """Clean Spanner database asynchronously."""
        start_time = time.time()
        self.stats.strategy_used = "DELETE (no TRUNCATE support)"

        try:
            tables = await self.get_table_list()
            if not tables:
                logger.info("No tables to clean")
                return self.stats

            ordered_tables = await self.resolve_dependencies(tables)
            self.stats.tables_cleaned = len(ordered_tables)

            await self._perform_delete_operations(ordered_tables)

            if self.verify_cleanup:
                await self._verify_tables_empty(ordered_tables)

        except Exception as e:
            logger.error(f"Async Spanner cleanup failed: {e}")
            raise CleanupError(f"async spanner cleanup failed: {e}") from e
        finally:
            self.stats.duration_seconds = time.time() - start_time

        return self.stats

    async def get_table_list(self) -> Sequence[str]:  # type: ignore[override]
        """Get list of Spanner tables asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_catalog = '' AND table_schema = ''
                    AND table_type = 'BASE TABLE'
            """)
            )
            all_tables = [row[0] for row in result]

            if self.include_only:
                tables = [t for t in all_tables if t in self.include_only]
            else:
                tables = [t for t in all_tables if t not in self.exclude_tables]

            return tables
        except Exception as e:
            raise CleanupError(f"failed to get table list: {e}") from e

    async def resolve_dependencies(self, tables: Sequence[str]) -> Sequence[str]:  # type: ignore[override]
        """Resolve Spanner foreign key dependencies asynchronously."""
        try:
            result = await self.connection.execute(
                text("""
                SELECT
                    tc.table_name,
                    ccu.table_name AS foreign_table_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
            """)
            )

            dependency_graph: dict[str, list[str]] = {table: [] for table in tables}
            for row in result:
                table, foreign_table = row[0], row[1]
                if table in dependency_graph and foreign_table in tables and foreign_table != table:
                    dependency_graph[table].append(foreign_table)

            return self._topological_sort(dependency_graph)
        except Exception as e:
            logger.warning(f"Failed to resolve dependencies: {e}, using original order")
            return list(tables)

    async def _perform_delete_operations(self, tables: Sequence[str]) -> None:
        """Perform DELETE operations asynchronously."""
        for table in reversed(tables):
            try:
                await self.connection.execute(text(f"DELETE FROM {table} WHERE TRUE"))
            except Exception as e:
                logger.error(f"Failed to delete from {table}: {e}")
                self.stats.errors_encountered += 1

        await self.connection.commit()

    async def _verify_tables_empty(self, tables: Sequence[str]) -> None:
        """Verify that all tables are empty asynchronously."""
        for table in tables:
            try:
                result = await self.connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                if count and count > 0:
                    raise CleanupError(f"table {table} still contains {count} rows after cleanup")
            except CleanupError:
                raise
            except Exception as e:
                logger.warning(f"Failed to verify table {table} is empty: {e}")

    def _topological_sort(self, dependency_graph: dict[str, list[str]]) -> list[str]:
        """Perform topological sort for dependencies."""
        in_degree = dict.fromkeys(dependency_graph, 0)

        for node, neighbors in dependency_graph.items():
            for neighbor in neighbors:
                if neighbor in in_degree:
                    in_degree[neighbor] += 1

        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in dependency_graph[node]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return result if len(result) == len(dependency_graph) else list(dependency_graph.keys())


# Factory function to create the appropriate cleaner
def _create_cleaner(
    engine_or_connection: Union[Engine, AsyncEngine, Connection, AsyncConnection],
    exclude_tables: Optional[Sequence[str]] = None,
    include_only: Optional[Sequence[str]] = None,
    verify_cleanup: bool = True,
    max_retries: int = 3,
    retry_delay: float = 0.1,
) -> Union[DatabaseCleaner, AsyncDatabaseCleaner]:
    """Create appropriate database cleaner based on engine dialect and type.

    Args:
        engine_or_connection: Database engine or connection
        exclude_tables: Tables to exclude from cleanup
        include_only: Only clean these tables if specified
        verify_cleanup: Whether to verify tables are actually clean
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds

    Returns:
        Appropriate database cleaner instance

    Raises:
        CleanupError: If no suitable cleaner is found for the dialect
    """
    # Determine if this is async or sync
    is_async = isinstance(engine_or_connection, (AsyncEngine, AsyncConnection))

    # Get connection if we have an engine
    if isinstance(engine_or_connection, (Engine, AsyncEngine)):
        dialect_name = engine_or_connection.dialect.name
        connection = engine_or_connection  # type: ignore[assignment]
    else:
        dialect_name = engine_or_connection.dialect.name
        connection = engine_or_connection  # type: ignore[assignment]

    # Handle Spanner which reports as "spanner+spanner"
    if "spanner" in dialect_name:
        dialect_name = "spanner"

    # Handle CockroachDB which reports as postgresql
    elif dialect_name == "postgresql":
        # Check if it's actually CockroachDB by looking for server version info.
        # Some engines expose a server_version_info on the dialect that includes
        # a string with "cockroach" when connected to CockroachDB.
        try:
            if hasattr(connection, "dialect") and hasattr(connection.dialect, "server_version_info"):
                server_version = getattr(connection.dialect, "server_version_info", None)
                if server_version and "cockroach" in str(server_version).lower():
                    dialect_name = "cockroach"
        except Exception:
            # If we can't determine, assume PostgreSQL
            pass

    # Map dialect names to cleaner classes
    sync_cleaners = {
        "postgresql": PostgreSQLCleaner,
        "cockroach": CockroachDBCleaner,
        "cockroachdb": CockroachDBCleaner,  # Also accept 'cockroachdb' dialect name
        "sqlite": SQLiteCleaner,
        "mysql": MySQLCleaner,
        "oracle": OracleCleaner,
        "mssql": MSSQLCleaner,
        "duckdb": DuckDBCleaner,
        "spanner": SpannerCleaner,
    }

    async_cleaners = {
        "postgresql": AsyncPostgreSQLCleaner,
        "cockroach": AsyncCockroachDBCleaner,
        "cockroachdb": AsyncCockroachDBCleaner,  # Also accept 'cockroachdb' dialect name
        "sqlite": AsyncSQLiteCleaner,
        "mysql": AsyncMySQLCleaner,
        "oracle": AsyncOracleCleaner,
        "mssql": AsyncMSSQLCleaner,
        "duckdb": AsyncDuckDBCleaner,
        "spanner": AsyncSpannerCleaner,
    }

    cleaners = async_cleaners if is_async else sync_cleaners

    if dialect_name not in cleaners:
        supported = list(cleaners.keys())
        raise CleanupError(f"unsupported database dialect: {dialect_name}, supported: {supported}")

    cleaner_class = cleaners[dialect_name]

    # Create connection if needed
    if isinstance(connection, (Engine, AsyncEngine)):
        if is_async:
            # For async engines, we'll need to connect within an async context
            raise CleanupError("async engines must be used with async context manager")
        connection = connection.connect()  # type: ignore[union-attr,assignment]

    return cleaner_class(  # type: ignore[abstract]
        connection=connection,  # type: ignore[arg-type]
        exclude_tables=exclude_tables,
        include_only=include_only,
        verify_cleanup=verify_cleanup,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )


@contextmanager
def cleanup_database(
    engine: Engine,
    exclude_tables: Optional[Sequence[str]] = None,
    include_only: Optional[Sequence[str]] = None,
    verify_cleanup: bool = True,
    max_retries: int = 3,
    retry_delay: float = 0.1,
) -> Generator[DatabaseCleaner, None, None]:
    """Context manager for synchronous database cleanup.

    Creates and yields an appropriate database cleaner for the engine dialect.
    Automatically manages connection lifecycle.

    Args:
        engine: Synchronous SQLAlchemy engine
        exclude_tables: Tables to exclude from cleanup
        include_only: Only clean these tables if specified
        verify_cleanup: Whether to verify tables are actually clean
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds

    Yields:
        DatabaseCleaner: Configured cleaner for the database dialect

    Example:
        >>> with cleanup_database(engine) as cleaner:
        ...     stats = cleaner.cleanup()
        ...     print(f"Cleaned {stats.tables_cleaned} tables")
    """
    connection = engine.connect()
    try:
        cleaner = _create_cleaner(
            connection,
            exclude_tables=exclude_tables,
            include_only=include_only,
            verify_cleanup=verify_cleanup,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        yield cleaner  # type: ignore[misc]
    finally:
        connection.close()


@asynccontextmanager
async def cleanup_database_async(
    engine: AsyncEngine,
    exclude_tables: Optional[Sequence[str]] = None,
    include_only: Optional[Sequence[str]] = None,
    verify_cleanup: bool = True,
    max_retries: int = 3,
    retry_delay: float = 0.1,
) -> AsyncGenerator[AsyncDatabaseCleaner, None]:
    """Async context manager for asynchronous database cleanup.

    Creates and yields an appropriate async database cleaner for the engine dialect.
    Automatically manages connection lifecycle.

    Args:
        engine: Asynchronous SQLAlchemy engine
        exclude_tables: Tables to exclude from cleanup
        include_only: Only clean these tables if specified
        verify_cleanup: Whether to verify tables are actually clean
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds

    Yields:
        AsyncDatabaseCleaner: Configured async cleaner for the database dialect

    Example:
        >>> async with cleanup_database_async(async_engine) as cleaner:
        ...     stats = await cleaner.cleanup()
        ...     print(f"Cleaned {stats.tables_cleaned} tables")
    """
    connection = await engine.connect()
    try:
        cleaner = _create_cleaner(
            connection,
            exclude_tables=exclude_tables,
            include_only=include_only,
            verify_cleanup=verify_cleanup,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        yield cast(AsyncDatabaseCleaner, cleaner)
    finally:
        await connection.close()


# Simple static utility functions for easy cleanup without context managers
def clean_tables(engine: Engine, metadata: MetaData) -> None:
    """Clean all tables in the metadata using appropriate strategy for the database.

    This is a convenience function that automatically selects the right cleaner
    based on the database dialect and performs cleanup without needing a context manager.

    Args:
        engine: SQLAlchemy engine
        metadata: Metadata containing tables to clean
    """
    # For SQLite, use a new connection to avoid transaction conflicts
    if engine.dialect.name == "sqlite":
        # Create a new engine with a fresh connection for cleanup
        cleanup_engine = create_engine(
            engine.url,
            poolclass=NullPool,  # Force new connections
            pool_pre_ping=True,
            connect_args={
                "timeout": 30,  # Increase timeout for locked databases
                "check_same_thread": False,  # Allow connections from different threads
                "isolation_level": None,  # Use autocommit mode
            },
        )
        try:
            with cleanup_database(cleanup_engine) as cleaner:
                tables_to_clean = [table.name for table in metadata.sorted_tables]
                cleaner.include_only = set(tables_to_clean) if tables_to_clean else None
                cleaner.cleanup()
        finally:
            cleanup_engine.dispose()
    else:
        with cleanup_database(engine) as cleaner:
            # Get table names from metadata
            tables_to_clean = [table.name for table in metadata.sorted_tables]
            cleaner.include_only = set(tables_to_clean) if tables_to_clean else None
            cleaner.cleanup()


async def async_clean_tables(engine: AsyncEngine, metadata: MetaData) -> None:
    """Async clean all tables in the metadata using appropriate strategy.

    This is a convenience function that automatically selects the right cleaner
    based on the database dialect and performs cleanup without needing a context manager.

    Args:
        engine: Async SQLAlchemy engine
        metadata: Metadata containing tables to clean
    """
    async with cleanup_database_async(engine) as cleaner:
        # Get table names from metadata
        tables_to_clean = [table.name for table in metadata.sorted_tables]
        cleaner.include_only = set(tables_to_clean) if tables_to_clean else None
        await cleaner.cleanup()

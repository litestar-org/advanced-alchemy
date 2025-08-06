"""Comprehensive DatabaseCleaner implementation for advanced-alchemy test suite.

This module provides database-specific cleanup strategies that efficiently clean
data between tests without dropping/recreating tables, significantly improving
test performance.

Usage:
    >>> async with cleanup_database(async_engine) as cleaner:
    ...     await cleaner.cleanup()

    >>> with cleanup_database(sync_engine) as cleaner:
    ...     cleaner.cleanup()
"""
# mypy: disable-error-code="misc,arg-type"

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union, cast

from sqlalchemy import MetaData, exc, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from advanced_alchemy.exceptions import RepositoryError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Sequence

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
        self.connection = connection  # type: ignore[assignment]


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
        self.connection = connection  # type: ignore[assignment]

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
        if "cockroach" in str(self.connection.bind.url).lower() if self.connection.bind else False:  # type: ignore[union-attr]
            sql = f"TRUNCATE TABLE {table_list} CASCADE"
        else:
            sql = f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"

        logger.debug(f"Executing: {sql}")
        await self.connection.execute(text(sql))
        await self.connection.commit()

    async def _reset_sequences(self) -> None:
        """Reset PostgreSQL sequences asynchronously."""
        # Skip sequence reset for CockroachDB as it doesn't support ALTER SEQUENCE ... RESTART
        if "cockroach" in str(self.connection.bind.url).lower() if self.connection.bind else False:  # type: ignore[union-attr]
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

        try:
            # Delete in reverse dependency order
            for table in reversed(tables):
                for attempt in range(self.max_retries):
                    try:
                        self.connection.execute(text(f"DELETE FROM {table}"))
                        break
                    except Exception as e:
                        if "database is locked" in str(e) and attempt < self.max_retries - 1:
                            logger.warning(f"Database locked on table {table}, retrying in {self.retry_delay}s...")
                            time.sleep(self.retry_delay)
                        else:
                            raise

            self.connection.commit()
        finally:
            # Re-enable foreign key checks
            self.connection.execute(text("PRAGMA foreign_keys = ON"))

    def _reset_autoincrement(self) -> None:
        """Reset SQLite autoincrement sequences."""
        try:
            # Clear sqlite_sequence table to reset autoincrement counters
            self.connection.execute(text("DELETE FROM sqlite_sequence"))
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

    # Handle CockroachDB which reports as postgresql
    if dialect_name == "postgresql":
        # Check if it's actually CockroachDB by looking for specific attributes
        try:
            if hasattr(connection, "dialect") and hasattr(connection.dialect, "server_version_info"):
                server_version = getattr(connection.dialect, "server_version_info", None)
                if server_version and "cockroach" in str(server_version).lower():
                    dialect_name = "cockroach"
            elif hasattr(connection, "get_dialect") and "cockroach" in str(connection.get_dialect()).lower():
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

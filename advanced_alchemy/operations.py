"""Advanced database operations for SQLAlchemy.

This module provides high-performance database operations that extend beyond basic CRUD
functionality. It implements specialized database operations optimized for bulk data
handling and schema management.

The operations module is designed to work seamlessly with SQLAlchemy Core and ORM,
providing efficient implementations for common database operations patterns.

Features
--------
- Cross-database ON CONFLICT/ON DUPLICATE KEY UPDATE operations
- MERGE statement support for Oracle and PostgreSQL 15+


Notes:
------
This module is designed to be database-agnostic where possible, with specialized
optimizations for specific database backends where appropriate.

See Also:
---------
- :mod:`sqlalchemy.sql.expression` : SQLAlchemy Core expression language
- :mod:`sqlalchemy.orm` : SQLAlchemy ORM functionality
- :mod:`advanced_alchemy.extensions` : Additional database extensions
"""

from typing import Any, Optional, Union
from uuid import UUID

from sqlalchemy import (
    Insert,
    Table,
    bindparam,
    text,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.expression import Executable

__all__ = ("MergeStatement", "OnConflictUpsert")


class MergeStatement(Executable, ClauseElement):
    """A MERGE statement for Oracle and PostgreSQL 15+.

    This provides a high-level interface for MERGE operations that
    can handle both matched and unmatched conditions.
    """

    inherit_cache = True

    def __init__(
        self,
        table: Table,
        source: Union[ClauseElement, str],
        on_condition: ClauseElement,
        when_matched_update: "Optional[dict[str, Any]]" = None,
        when_not_matched_insert: "Optional[dict[str, Any]]" = None,
    ) -> None:
        """Initialize a MERGE statement.

        Args:
            table: Target table for the merge operation
            source: Source data (can be a subquery or table)
            on_condition: Condition for matching rows
            when_matched_update: Values to update when rows match
            when_not_matched_insert: Values to insert when rows don't match
        """
        self.table = table
        self.source = source
        self.on_condition = on_condition
        self.when_matched_update = when_matched_update or {}
        self.when_not_matched_insert = when_not_matched_insert or {}


# PostgreSQL version constant
POSTGRES_MERGE_VERSION = 15


@compiles(MergeStatement)
def compile_merge_default(_element: MergeStatement, compiler: SQLCompiler, **_kwargs: Any) -> str:
    """Default compilation - raises error for unsupported dialects."""
    dialect_name = compiler.dialect.name
    msg = f"MERGE statement not supported for dialect '{dialect_name}'"
    raise NotImplementedError(msg)


@compiles(MergeStatement, "oracle")
def compile_merge_oracle(element: MergeStatement, compiler: SQLCompiler, **kwargs: Any) -> str:
    """Compile MERGE statement for Oracle."""
    table_name = element.table.name

    if isinstance(element.source, str):
        source_str = element.source
        if source_str.upper().startswith("SELECT") and "FROM DUAL" not in source_str.upper():
            source_str = f"{source_str} FROM DUAL"
        source_clause = f"({source_str})"
    else:
        source_clause = compiler.process(element.source, **kwargs)

    merge_sql = f"MERGE INTO {table_name} tgt USING {source_clause} src ON ("
    merge_sql += compiler.process(element.on_condition, **kwargs)
    merge_sql += ")"

    if element.when_matched_update:
        merge_sql += " WHEN MATCHED THEN UPDATE SET "
        updates = []
        for column, value in element.when_matched_update.items():
            if hasattr(value, "_compiler_dispatch"):
                compiled_value = compiler.process(value, **kwargs)
            else:
                compiled_value = compiler.process(value, **kwargs)
            updates.append(f"{column} = {compiled_value}")  # pyright: ignore
        merge_sql += ", ".join(updates)  # pyright: ignore

    if element.when_not_matched_insert:
        columns = list(element.when_not_matched_insert.keys())
        values = list(element.when_not_matched_insert.values())

        merge_sql += " WHEN NOT MATCHED THEN INSERT ("
        merge_sql += ", ".join(columns)
        merge_sql += ") VALUES ("

        compiled_values = []
        for value in values:
            if hasattr(value, "_compiler_dispatch"):
                compiled_value = compiler.process(value, **kwargs)
            else:
                compiled_value = compiler.process(value, **kwargs)
            compiled_values.append(compiled_value)  # pyright: ignore
        merge_sql += ", ".join(compiled_values)  # pyright: ignore
        merge_sql += ")"

    return merge_sql


@compiles(MergeStatement, "postgresql")
def compile_merge_postgresql(element: MergeStatement, compiler: SQLCompiler, **kwargs: Any) -> str:
    """Compile MERGE statement for PostgreSQL 15+."""
    dialect = compiler.dialect
    if (
        hasattr(dialect, "server_version_info")
        and dialect.server_version_info
        and dialect.server_version_info[0] < POSTGRES_MERGE_VERSION
    ):
        msg = "MERGE statement requires PostgreSQL 15 or higher"
        raise NotImplementedError(msg)

    table_name = element.table.name

    if isinstance(element.source, str):
        source_clause = f"({element.source})"
    else:
        source_clause = compiler.process(element.source, **kwargs)

    merge_sql = f"MERGE INTO {table_name} AS tgt USING {source_clause} AS src ON ("
    merge_sql += compiler.process(element.on_condition, **kwargs)
    merge_sql += ")"

    if element.when_matched_update:
        merge_sql += " WHEN MATCHED THEN UPDATE SET "
        updates = []
        for column, value in element.when_matched_update.items():
            if hasattr(value, "_compiler_dispatch"):
                compiled_value = compiler.process(value, **kwargs)
            else:
                compiled_value = compiler.process(value, **kwargs)
            updates.append(f"{column} = {compiled_value}")  # pyright: ignore
        merge_sql += ", ".join(updates)  # pyright: ignore

    if element.when_not_matched_insert:
        columns = list(element.when_not_matched_insert.keys())
        values = list(element.when_not_matched_insert.values())

        merge_sql += " WHEN NOT MATCHED THEN INSERT ("
        merge_sql += ", ".join(columns)
        merge_sql += ") VALUES ("

        compiled_values = []
        for value in values:
            if hasattr(value, "_compiler_dispatch"):
                compiled_value = compiler.process(value, **kwargs)
            else:
                compiled_value = compiler.process(value, **kwargs)
            compiled_values.append(compiled_value)  # pyright: ignore
        merge_sql += ", ".join(compiled_values)  # pyright: ignore
        merge_sql += ")"

    return merge_sql


class OnConflictUpsert:
    """Cross-database upsert operation using dialect-specific constructs.

    This class provides a unified interface for upsert operations across
    different database backends using their native ON CONFLICT or
    ON DUPLICATE KEY UPDATE mechanisms.
    """

    @staticmethod
    def supports_native_upsert(dialect_name: str) -> bool:
        """Check if the dialect supports native upsert operations.

        Args:
            dialect_name: Name of the database dialect

        Returns:
            True if native upsert is supported, False otherwise
        """
        return dialect_name in {"postgresql", "cockroachdb", "sqlite", "mysql", "mariadb", "duckdb"}

    @staticmethod
    def create_upsert(
        table: Table,
        values: "dict[str, Any]",
        conflict_columns: "list[str]",
        update_columns: "Optional[list[str]]" = None,
        dialect_name: Optional[str] = None,
    ) -> Insert:
        """Create a dialect-specific upsert statement.

        Args:
            table: Target table for the upsert
            values: Values to insert/update
            conflict_columns: Columns that define the conflict condition
            update_columns: Columns to update on conflict (defaults to all non-conflict columns)
            dialect_name: Database dialect name (auto-detected if not provided)

        Returns:
            A SQLAlchemy Insert statement with upsert logic

        Raises:
            NotImplementedError: If the dialect doesn't support native upsert
        """
        if update_columns is None:
            # Default to updating all columns except conflict columns
            update_columns = [col for col in values if col not in conflict_columns]

        if dialect_name in {"postgresql", "cockroachdb", "sqlite", "duckdb"}:
            # Use PostgreSQL-style ON CONFLICT
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_insert_stmt = pg_insert(table).values(values)
            return pg_insert_stmt.on_conflict_do_update(
                index_elements=conflict_columns, set_={col: pg_insert_stmt.excluded[col] for col in update_columns}
            )

        if dialect_name in {"mysql", "mariadb"}:
            # Use MySQL-style ON DUPLICATE KEY UPDATE
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_insert_stmt = mysql_insert(table).values(values)
            return mysql_insert_stmt.on_duplicate_key_update(
                **{col: mysql_insert_stmt.inserted[col] for col in update_columns}
            )

        msg = f"Native upsert not supported for dialect '{dialect_name}'"
        raise NotImplementedError(msg)

    @staticmethod
    def create_merge_upsert(
        table: Table,
        values: "dict[str, Any]",
        conflict_columns: "list[str]",
        update_columns: "Optional[list[str]]" = None,
        dialect_name: Optional[str] = None,
    ) -> "tuple[MergeStatement, dict[str, Any]]":
        """Create a MERGE-based upsert for Oracle/PostgreSQL 15+.

        For Oracle databases, this method automatically generates values for primary key
        columns that have callable defaults (such as UUID generation functions). This is
        necessary because Oracle MERGE statements cannot use Python callable defaults
        directly in the INSERT clause.

        Args:
            table: Target table for the upsert
            values: Values to insert/update
            conflict_columns: Columns that define the matching condition
            update_columns: Columns to update on match (defaults to all non-conflict columns)
            dialect_name: Database dialect name (used to determine Oracle-specific syntax)

        Returns:
            A tuple of (MergeStatement, additional_params) where additional_params
            contains any generated values (like Oracle UUID primary keys)
        """
        if update_columns is None:
            update_columns = [col for col in values if col not in conflict_columns]

        source_values = ", ".join([f":{key} as {key}" for key in values])
        source = f"SELECT {source_values} FROM DUAL" if dialect_name == "oracle" else f"SELECT {source_values}"  # noqa: S608

        on_conditions = [f"tgt.{col} = src.{col}" for col in conflict_columns]
        on_condition = text(" AND ".join(on_conditions))

        when_matched_update: dict[str, Any] = {col: bindparam(col) for col in update_columns}

        insert_columns = list(values.keys())
        additional_params = {}

        if dialect_name == "oracle":
            for col in table.primary_key.columns:
                if (
                    col.name not in values
                    and hasattr(col, "default")
                    and col.default is not None
                    and (hasattr(col.default, "arg") and callable(col.default.arg))  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType,reportAttributeAccessIssue]
                ):
                    try:
                        if hasattr(col.default, "arg"):
                            try:
                                default_value = col.default.arg()  # pyright: ignore[reportAttributeAccessIssue]
                            except TypeError:
                                default_value = col.default.arg(None)  # pyright: ignore[reportAttributeAccessIssue]

                            # Convert UUID to hex format for Oracle compatibility

                            if isinstance(default_value, UUID):
                                default_value = default_value.hex

                            additional_params[col.name] = default_value
                            insert_columns.append(col.name)
                    except (TypeError, AttributeError, ValueError):
                        continue

            if additional_params:
                additional_selects = [f":{col_name} as {col_name}" for col_name in additional_params]  # pyright: ignore[reportUnknownVariableType]
                if source.endswith(" FROM DUAL"):
                    base_source = source[: -len(" FROM DUAL")]
                    source = f"{base_source}, {', '.join(additional_selects)} FROM DUAL"
                else:
                    source = f"{source}, {', '.join(additional_selects)}"

        when_not_matched_insert: dict[str, Any] = {col: bindparam(col) for col in insert_columns}

        merge_stmt = MergeStatement(
            table=table,
            source=source,
            on_condition=on_condition,
            when_matched_update=when_matched_update,
            when_not_matched_insert=when_not_matched_insert,
        )

        return merge_stmt, additional_params  # pyright: ignore[reportUnknownVariableType]

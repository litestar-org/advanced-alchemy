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

Security
--------
This module constructs SQL statements using database identifiers (table and column names)
that MUST come from trusted sources only. All identifiers should originate from:

- SQLAlchemy model metadata (e.g., Model.__table__)
- Hardcoded strings in application code
- Validated configuration files

Never pass user input directly as table names, column names, or other SQL identifiers.
Data values are properly parameterized using bindparam() to prevent SQL injection.

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

import re
from typing import TYPE_CHECKING, Any, Optional, Union, cast
from uuid import UUID

from sqlalchemy import Insert, Table, bindparam, literal_column, select, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.expression import Executable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.sql.compiler import SQLCompiler
    from sqlalchemy.sql.elements import ColumnElement

__all__ = ("MergeStatement", "OnConflictUpsert", "validate_identifier")

# Pattern for valid SQL identifiers (conservative - alphanumeric and underscore only)
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_identifier(name: str, identifier_type: str = "identifier") -> str:
    """Validate a SQL identifier to ensure it's safe for use in SQL statements.

    This function provides validation for SQL identifiers
    (table names, column names, etc.) to ensure they contain only safe characters.
    While the operations in this module should only receive identifiers from
    trusted sources, this validation adds an extra layer of security.

    Note: SQL keywords (like 'select', 'insert', etc.) are allowed as they can
    be properly quoted/escaped by SQLAlchemy when used as identifiers.

    Args:
        name: The identifier to validate
        identifier_type: Type of identifier for error messages (e.g., "column", "table")

    Returns:
        The validated identifier

    Raises:
        ValueError: If the identifier is empty or contains invalid characters

    Examples:
        >>> validate_identifier("user_id")
        'user_id'
        >>> validate_identifier("users_table", "table")
        'users_table'
        >>> validate_identifier("select")  # SQL keywords are allowed
        'select'
        >>> validate_identifier(
        ...     "drop table users; --"
        ... )  # Raises ValueError - contains invalid characters
    """
    if not name:
        msg = f"Empty {identifier_type} name provided"
        raise ValueError(msg)

    if not _IDENTIFIER_PATTERN.match(name):
        msg = f"Invalid {identifier_type} name: '{name}'. Only alphanumeric characters and underscores are allowed."
        raise ValueError(msg)

    return name


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
        when_matched_update: Optional[dict[str, Any]] = None,
        when_not_matched_insert: Optional[dict[str, Any]] = None,
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
def compile_merge_default(element: MergeStatement, compiler: "SQLCompiler", **kwargs: Any) -> str:
    """Default compilation - raises error for unsupported dialects."""
    _ = element, kwargs  # Unused parameters
    dialect_name = compiler.dialect.name
    msg = f"MERGE statement not supported for dialect '{dialect_name}'"
    raise NotImplementedError(msg)


@compiles(MergeStatement, "oracle")
def compile_merge_oracle(element: MergeStatement, compiler: "SQLCompiler", **kwargs: Any) -> str:
    """Compile MERGE statement for Oracle."""
    table_name = element.table.name

    if isinstance(element.source, str):
        source_str = element.source
        if source_str.upper().startswith("SELECT") and "FROM DUAL" not in source_str.upper():
            source_str = f"{source_str} FROM DUAL"
        source_clause = f"({source_str})"
    else:
        compiled_source = compiler.process(element.source, **kwargs)
        source_clause = f"({compiled_source})"

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
def compile_merge_postgresql(element: MergeStatement, compiler: "SQLCompiler", **kwargs: Any) -> str:
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
        # Wrap raw string source and alias as src
        source_clause = f"({element.source}) AS src"
    else:
        # Ensure the compiled source is parenthesized and has a stable alias 'src'
        compiled_source = compiler.process(element.source, **kwargs)
        compiled_trim = compiled_source.strip()
        if compiled_trim.startswith("("):
            # Already parenthesized; check for alias after closing paren
            has_outer_alias = (
                re.search(r"\)\s+(AS\s+)?[a-zA-Z_][a-zA-Z0-9_]*\s*$", compiled_trim, re.IGNORECASE) is not None
            )
            source_clause = compiled_trim if has_outer_alias else f"{compiled_trim} AS src"
        else:
            # Not parenthesized: wrap and alias
            source_clause = f"({compiled_trim}) AS src"

    merge_sql = f"MERGE INTO {table_name} AS tgt USING {source_clause} ON ("
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
        values: dict[str, Any],
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
        dialect_name: Optional[str] = None,
        validate_identifiers: bool = False,
    ) -> Insert:
        """Create a dialect-specific upsert statement.

        Args:
            table: Target table for the upsert
            values: Values to insert/update
            conflict_columns: Columns that define the conflict condition
            update_columns: Columns to update on conflict (defaults to all non-conflict columns)
            dialect_name: Database dialect name (auto-detected if not provided)
            validate_identifiers: If True, validate column names for safety (default: False)

        Returns:
            A SQLAlchemy Insert statement with upsert logic

        Raises:
            NotImplementedError: If the dialect doesn't support native upsert
            ValueError: If validate_identifiers is True and invalid identifiers are found
        """
        if validate_identifiers:
            for col in conflict_columns:
                validate_identifier(col, "conflict column")
            if update_columns:
                for col in update_columns:
                    validate_identifier(col, "update column")
            for col in values:
                validate_identifier(col, "column")

        if update_columns is None:
            update_columns = [col for col in values if col not in conflict_columns]

        if dialect_name in {"postgresql", "sqlite", "duckdb"}:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_insert_stmt = pg_insert(table).values(values)
            return pg_insert_stmt.on_conflict_do_update(
                index_elements=conflict_columns, set_={col: pg_insert_stmt.excluded[col] for col in update_columns}
            )
        if dialect_name == "cockroachdb":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_insert_stmt = pg_insert(table).values(values)
            return pg_insert_stmt.on_conflict_do_update(
                index_elements=conflict_columns, set_={col: pg_insert_stmt.excluded[col] for col in update_columns}
            )

        if dialect_name in {"mysql", "mariadb"}:
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_insert_stmt = mysql_insert(table).values(values)
            return mysql_insert_stmt.on_duplicate_key_update(
                **{col: mysql_insert_stmt.inserted[col] for col in update_columns}
            )

        msg = f"Native upsert not supported for dialect '{dialect_name}'"
        raise NotImplementedError(msg)

    @staticmethod
    def create_merge_upsert(  # noqa: C901, PLR0915
        table: Table,
        values: dict[str, Any],
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
        dialect_name: Optional[str] = None,
        validate_identifiers: bool = False,
    ) -> tuple[MergeStatement, dict[str, Any]]:
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
            validate_identifiers: If True, validate column names for safety (default: False)

        Returns:
            A tuple of (MergeStatement, additional_params) where additional_params
            contains any generated values (like Oracle UUID primary keys)

        Raises:
            ValueError: If validate_identifiers is True and invalid identifiers are found
        """
        if validate_identifiers:
            for col in conflict_columns:
                validate_identifier(col, "conflict column")
            if update_columns:
                for col in update_columns:
                    validate_identifier(col, "update column")
            for col in values:
                validate_identifier(col, "column")

        if update_columns is None:
            update_columns = [col for col in values if col not in conflict_columns]

        additional_params: dict[str, Any] = {}
        source: Union[ClauseElement, str]
        insert_columns: list[str]
        when_not_matched_insert: dict[str, Any]

        if dialect_name == "oracle":
            labeled_columns: list[ColumnElement[Any]] = []
            for key, value in values.items():
                column = table.c[key]
                labeled_columns.append(bindparam(key, value=value, type_=column.type).label(key))

            pk_col_with_seq = None
            for pk_column in table.primary_key.columns:
                if pk_column.name in values or pk_column.default is None:
                    continue
                if callable(getattr(pk_column.default, "arg", None)):
                    try:
                        default_value = pk_column.default.arg(None)  # type: ignore[attr-defined]
                        if isinstance(default_value, UUID):
                            default_value = default_value.hex
                        additional_params[pk_column.name] = default_value
                        labeled_columns.append(
                            bindparam(pk_column.name, value=default_value, type_=pk_column.type).label(pk_column.name)
                        )
                    except (TypeError, AttributeError, ValueError):
                        continue
                elif hasattr(pk_column.default, "next_value"):
                    pk_col_with_seq = pk_column

            # Oracle requires FROM DUAL for SELECT statements without tables
            source_query = select(*labeled_columns)
            # Add FROM DUAL for Oracle
            source_query = source_query.select_from(text("DUAL"))
            source = source_query.subquery("src")
            insert_columns = [label_col.name for label_col in labeled_columns]
            when_not_matched_insert = {col_name: literal_column(f"src.{col_name}") for col_name in insert_columns}
            if pk_col_with_seq is not None:
                insert_columns.append(pk_col_with_seq.name)
                when_not_matched_insert[pk_col_with_seq.name] = cast("Any", pk_col_with_seq.default).next_value()

        elif dialect_name in {"postgresql", "cockroachdb"}:
            labeled_columns = []
            for key, value in values.items():
                column = table.c[key]
                bp = bindparam(f"src_{key}", value=value, type_=column.type)
                labeled_columns.append(bp.label(key))
            source = select(*labeled_columns).subquery("src")
            insert_columns = list(values.keys())
            when_not_matched_insert = {col: literal_column(f"src.{col}") for col in insert_columns}
        else:
            placeholders = ", ".join([f"%({key})s" for key in values])
            col_names = ", ".join(values.keys())
            source = f"(SELECT * FROM (VALUES ({placeholders})) AS src({col_names}))"  # noqa: S608
            insert_columns = list(values.keys())
            when_not_matched_insert = {col: bindparam(col) for col in insert_columns}

        on_conditions = [f"tgt.{col} = src.{col}" for col in conflict_columns]
        on_condition = text(" AND ".join(on_conditions))

        if dialect_name in {"postgresql", "cockroachdb", "oracle"}:
            when_matched_update: dict[str, Any] = {
                col: literal_column(f"src.{col}") for col in update_columns if col in values
            }
        else:
            when_matched_update = {col: bindparam(col) for col in update_columns if col in values}

        # For Oracle, we need to ensure the keys in when_not_matched_insert match the insert_columns
        if dialect_name == "oracle":
            final_insert_mapping = {}
            for col_name in insert_columns:
                if col_name in when_not_matched_insert:
                    final_insert_mapping[col_name] = when_not_matched_insert[col_name]
            when_not_matched_insert = final_insert_mapping

        merge_stmt = MergeStatement(
            table=table,
            source=source,
            on_condition=on_condition,
            when_matched_update=when_matched_update,
            when_not_matched_insert=when_not_matched_insert,
        )

        return merge_stmt, additional_params  # pyright: ignore[reportUnknownVariableType]


# Note: Oracle-specific helper removed; inline logic now handles defaults

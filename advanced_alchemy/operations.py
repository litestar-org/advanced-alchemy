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

import functools
import re
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Optional, Union, cast
from uuid import UUID

from sqlalchemy import Insert, Table, UniqueConstraint, bindparam, literal_column, select, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.expression import Executable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

    from sqlalchemy.sql.compiler import SQLCompiler
    from sqlalchemy.sql.elements import ColumnElement

UpsertKind = Literal["on_conflict", "merge", "insert_or_update", "fallback"]

__all__ = (
    "MergeStatement",
    "OnConflictUpsert",
    "UpsertKind",
    "UpsertStrategy",
    "resolve_upsert_strategy",
    "validate_identifier",
)

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

    @staticmethod
    def create_upsert_many(
        table: Table,
        values_list: list[dict[str, Any]],
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
        dialect_name: Optional[str] = None,
        validate_identifiers: bool = False,
    ) -> tuple[Insert, bool]:
        """Build a dialect-specific bulk Insert with ON CONFLICT / ON DUPLICATE KEY UPDATE.

        Compiles to a single ``INSERT ... VALUES (...), (...), ...`` per chunk so the
        round-trip cost is fixed regardless of batch size.

        Args:
            table: Target table for the upsert.
            values_list: Rows to insert/update. All rows MUST share the same keys.
            conflict_columns: Columns that define the conflict / match condition.
            update_columns: Columns to update on conflict (defaults to all
                non-conflict keys from the first row).
            dialect_name: Database dialect name; determines compile path.
            validate_identifiers: If True, validate column identifiers for safety.

        Returns:
            A tuple ``(statement, supports_returning)`` where ``supports_returning``
            is True for postgresql / cockroachdb / sqlite / duckdb and False for
            mysql / mariadb.

        Raises:
            ValueError: ``values_list`` is empty, rows have heterogeneous keys,
                or identifier validation fails.
            NotImplementedError: The dialect does not support an ON CONFLICT
                style native bulk upsert.
        """
        _validate_bulk_inputs(values_list, conflict_columns, update_columns, validate_identifiers)

        resolved_update_columns = (
            update_columns
            if update_columns is not None
            else [col for col in values_list[0] if col not in conflict_columns]
        )

        if dialect_name in {"postgresql", "sqlite", "duckdb", "cockroachdb"}:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_stmt = pg_insert(table).values(values_list)
            return (
                pg_stmt.on_conflict_do_update(
                    index_elements=conflict_columns,
                    set_={col: pg_stmt.excluded[col] for col in resolved_update_columns},
                ),
                True,
            )

        if dialect_name in {"mysql", "mariadb"}:
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_stmt = mysql_insert(table).values(values_list)
            return (
                mysql_stmt.on_duplicate_key_update(
                    **{col: mysql_stmt.inserted[col] for col in resolved_update_columns}
                ),
                False,
            )

        msg = f"Native bulk upsert not supported for dialect '{dialect_name}'"
        raise NotImplementedError(msg)

    @staticmethod
    def create_merge_many(
        table: Table,
        values_list: list[dict[str, Any]],
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
        dialect_name: Optional[str] = None,
        validate_identifiers: bool = False,
    ) -> tuple[Union[MergeStatement, list[MergeStatement]], dict[str, Any]]:
        """Build a bulk MERGE / executemany-fallback per dialect.

        Returns a single ``MergeStatement`` for dialects whose MERGE syntax supports
        a multi-row source (oracle, mssql, postgresql/cockroachdb), and a list of
        single-row ``MergeStatement`` (one per input row) for everything else.

        Args:
            table: Target table for the upsert.
            values_list: Rows to insert/update. All rows MUST share the same keys.
            conflict_columns: Columns that define the matching condition.
            update_columns: Columns to update on match (defaults to all non-conflict
                keys from the first row).
            dialect_name: Database dialect name; selects the source construction.
            validate_identifiers: If True, validate column identifiers for safety.

        Returns:
            A tuple ``(statement_or_list, additional_params)``. ``additional_params``
            carries generated values (Oracle UUID PKs, MSSQL bound row values) that
            must be passed when executing.

        Raises:
            ValueError: ``values_list`` is empty, rows have heterogeneous keys,
                or identifier validation fails.
        """
        _validate_bulk_inputs(values_list, conflict_columns, update_columns, validate_identifiers)

        resolved_update_columns = (
            update_columns
            if update_columns is not None
            else [col for col in values_list[0] if col not in conflict_columns]
        )

        if dialect_name == "oracle":
            return _build_oracle_bulk_merge(table, values_list, conflict_columns, resolved_update_columns)

        if dialect_name in {"postgresql", "cockroachdb"}:
            return _build_pg_bulk_merge(table, values_list, conflict_columns, resolved_update_columns)

        if dialect_name == "mssql":
            return _build_mssql_bulk_merge(table, values_list, conflict_columns, resolved_update_columns)

        stmts: list[MergeStatement] = []
        combined_params: dict[str, Any] = {}
        for row in values_list:
            stmt, row_params = OnConflictUpsert.create_merge_upsert(
                table=table,
                values=row,
                conflict_columns=conflict_columns,
                update_columns=update_columns,
                dialect_name=dialect_name,
                validate_identifiers=False,
            )
            stmts.append(stmt)
            combined_params.update(row_params)
        return stmts, combined_params


def _validate_bulk_inputs(
    values_list: list[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: Optional[list[str]],
    validate_identifiers_flag: bool,
) -> None:
    """Shared input guard for create_upsert_many / create_merge_many.

    Raises ValueError on empty list, heterogeneous keys, or invalid identifiers
    when validation is requested.
    """
    if not values_list:
        msg = "values_list must not be empty"
        raise ValueError(msg)
    first_keys = set(values_list[0].keys())
    for idx, row in enumerate(values_list[1:], start=1):
        if set(row.keys()) != first_keys:
            msg = f"All entries in values_list must share the same keys (row {idx} differs from row 0)"
            raise ValueError(msg)
    if validate_identifiers_flag:
        for col in conflict_columns:
            validate_identifier(col, "conflict column")
        if update_columns:
            for col in update_columns:
                validate_identifier(col, "update column")
        for col in first_keys:
            validate_identifier(col, "column")


def _collect_oracle_pk_defaults(
    table: Table,
    row: dict[str, Any],
    idx: int,
    additional_params: dict[str, Any],
) -> list["ColumnElement[Any]"]:
    """Generate PK default bindparams for one Oracle MERGE row.

    Mirrors the per-row PK-default block in create_merge_upsert but namespaces the
    bindparam names with ``row{idx}_pk_`` so each row in the bulk source has its
    own unique param name (Oracle MERGE has no implicit row identity).
    """
    pk_columns: list[ColumnElement[Any]] = []
    for pk_column in table.primary_key.columns:
        if pk_column.name in row or pk_column.default is None:
            continue
        if not callable(getattr(pk_column.default, "arg", None)):
            continue
        try:
            default_value = pk_column.default.arg(None)  # type: ignore[attr-defined]
        except (TypeError, AttributeError, ValueError):
            continue
        if isinstance(default_value, UUID):
            default_value = default_value.hex
        param_name = f"row{idx}_pk_{pk_column.name}"
        additional_params[param_name] = default_value
        pk_columns.append(bindparam(param_name, value=default_value, type_=pk_column.type).label(pk_column.name))
    return pk_columns


def _build_oracle_bulk_merge(
    table: Table,
    values_list: list[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: list[str],
) -> tuple[MergeStatement, dict[str, Any]]:
    """Construct an Oracle MERGE whose source is ``SELECT ... FROM DUAL UNION ALL ...``."""
    first_keys = list(values_list[0].keys())
    additional_params: dict[str, Any] = {}
    per_row_selects: list[Any] = []
    pk_default_names: list[str] = []

    for idx, row in enumerate(values_list):
        row_columns: list[ColumnElement[Any]] = []
        for key in first_keys:
            column = table.c[key]
            bp = bindparam(f"row{idx}_{key}", value=row[key], type_=column.type)
            row_columns.append(bp.label(key))
        pk_extras = _collect_oracle_pk_defaults(table, row, idx, additional_params)
        if idx == 0:
            pk_default_names = [col.name for col in pk_extras]
        row_columns.extend(pk_extras)
        per_row_selects.append(select(*row_columns).select_from(text("DUAL")))

    unified = per_row_selects[0] if len(per_row_selects) == 1 else per_row_selects[0].union_all(*per_row_selects[1:])
    source = unified.subquery("src")
    insert_columns = list(first_keys) + pk_default_names
    when_not_matched_insert: dict[str, Any] = {col: literal_column(f"src.{col}") for col in insert_columns}
    when_matched_update: dict[str, Any] = {
        col: literal_column(f"src.{col}") for col in update_columns if col in first_keys
    }
    on_condition = text(" AND ".join(f"tgt.{col} = src.{col}" for col in conflict_columns))
    return (
        MergeStatement(
            table=table,
            source=source,
            on_condition=on_condition,
            when_matched_update=when_matched_update,
            when_not_matched_insert=when_not_matched_insert,
        ),
        additional_params,
    )


def _build_pg_bulk_merge(
    table: Table,
    values_list: list[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: list[str],
) -> tuple[MergeStatement, dict[str, Any]]:
    """Construct a PostgreSQL/CockroachDB MERGE whose source is ``SELECT ... UNION ALL ...``."""
    first_keys = list(values_list[0].keys())
    per_row_selects: list[Any] = []
    for idx, row in enumerate(values_list):
        row_columns: list[ColumnElement[Any]] = []
        for key in first_keys:
            column = table.c[key]
            bp = bindparam(f"src_row{idx}_{key}", value=row[key], type_=column.type)
            row_columns.append(bp.label(key))
        per_row_selects.append(select(*row_columns))

    unified = per_row_selects[0] if len(per_row_selects) == 1 else per_row_selects[0].union_all(*per_row_selects[1:])
    source = unified.subquery("src")
    when_not_matched_insert: dict[str, Any] = {col: literal_column(f"src.{col}") for col in first_keys}
    when_matched_update: dict[str, Any] = {
        col: literal_column(f"src.{col}") for col in update_columns if col in first_keys
    }
    on_condition = text(" AND ".join(f"tgt.{col} = src.{col}" for col in conflict_columns))
    return (
        MergeStatement(
            table=table,
            source=source,
            on_condition=on_condition,
            when_matched_update=when_matched_update,
            when_not_matched_insert=when_not_matched_insert,
        ),
        {},
    )


def _build_mssql_bulk_merge(
    table: Table,
    values_list: list[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: list[str],
) -> tuple[MergeStatement, dict[str, Any]]:
    """Construct an MSSQL MergeStatement with a raw-string ``VALUES (...) AS src(...)`` source.

    The MSSQL @compiles body for MergeStatement is added in Ch.4; this chapter only
    fixes the shape: a raw string source so the compiler emits it verbatim.
    """
    first_keys = list(values_list[0].keys())
    additional_params: dict[str, Any] = {}
    col_names = ", ".join(first_keys)
    row_strs: list[str] = []
    for idx, row in enumerate(values_list):
        placeholders = ", ".join(f":row{idx}_{key}" for key in first_keys)
        row_strs.append(f"({placeholders})")
        for key in first_keys:
            additional_params[f"row{idx}_{key}"] = row[key]
    values_source = f"VALUES {', '.join(row_strs)} AS src({col_names})"
    when_not_matched_insert: dict[str, Any] = {col: literal_column(f"src.{col}") for col in first_keys}
    when_matched_update: dict[str, Any] = {
        col: literal_column(f"src.{col}") for col in update_columns if col in first_keys
    }
    on_condition = text(" AND ".join(f"tgt.{col} = src.{col}" for col in conflict_columns))
    return (
        MergeStatement(
            table=table,
            source=values_source,
            on_condition=on_condition,
            when_matched_update=when_matched_update,
            when_not_matched_insert=when_not_matched_insert,
        ),
        additional_params,
    )


class UpsertStrategy(NamedTuple):
    """Dispatch decision returned by :func:`resolve_upsert_strategy`.

    Tells the repository which native primitive to compile (``on_conflict`` /
    ``merge`` / ``insert_or_update``) or whether to take the existing
    SELECT-then-partition fallback. The ``conflict_columns`` field is the
    *validated* unique key (PK / UniqueConstraint / unique Index) — which
    may be a subset of the caller's ``match_fields`` (e.g. PK match where
    the caller passed extra columns).
    """

    kind: UpsertKind
    supports_returning: bool
    conflict_columns: tuple[str, ...]
    dialect_name: str


_DIALECTS_ON_CONFLICT_RETURNING: frozenset[str] = frozenset({"postgresql", "cockroachdb", "sqlite", "duckdb"})
_DIALECTS_ON_CONFLICT_NO_RETURNING: frozenset[str] = frozenset({"mysql", "mariadb"})
_DIALECTS_MERGE: frozenset[str] = frozenset({"oracle", "mssql"})
_DIALECTS_INSERT_OR_UPDATE: frozenset[str] = frozenset({"spanner"})


def _native_primitive_for_dialect(dialect_name: str) -> tuple[Optional[UpsertKind], bool]:
    """Return ``(kind, supports_returning)`` for the dialect's native upsert primitive.

    Returns ``(None, False)`` for dialects without a native primitive (fallback).
    """
    if dialect_name in _DIALECTS_ON_CONFLICT_RETURNING:
        return ("on_conflict", True)
    if dialect_name in _DIALECTS_ON_CONFLICT_NO_RETURNING:
        return ("on_conflict", False)
    if dialect_name in _DIALECTS_MERGE:
        return ("merge", True)
    if dialect_name in _DIALECTS_INSERT_OR_UPDATE:
        return ("insert_or_update", False)
    return (None, False)


def resolve_upsert_strategy(
    table: Table,
    match_fields: "Sequence[str]",
    dialect_name: str,
) -> UpsertStrategy:
    """Resolve the optimal upsert strategy for ``(table, match_fields, dialect)``.

    The result is cached for the process lifetime; ``Table`` objects are
    singletons per declarative class, so this is one decision per
    ``(model, match_fields, dialect)`` tuple.

    Resolution priority:

    1. ``match_fields`` equals or is a superset of the table's primary key →
       native primitive for the dialect, ``conflict_columns`` is the PK.
    2. A :class:`~sqlalchemy.UniqueConstraint` whose columns match exactly →
       native primitive, ``conflict_columns`` is that constraint's columns.
    3. A unique :class:`~sqlalchemy.Index` whose columns match exactly →
       native primitive, ``conflict_columns`` is that index's columns.
    4. Otherwise → ``kind="fallback"``, ``supports_returning=False``.

    Args:
        table: Target table. Used by identity for caching.
        match_fields: Columns the caller wants to match on. Order-insensitive.
        dialect_name: Database dialect name.

    Returns:
        An :class:`UpsertStrategy` describing the decision.

    Raises:
        ValueError: ``match_fields`` is empty or contains a column not present
            on the table.
    """
    if not match_fields:
        msg = "match_fields must not be empty"
        raise ValueError(msg)
    normalized = tuple(sorted(set(match_fields)))
    table_columns = set(table.c.keys())
    missing = [col for col in normalized if col not in table_columns]
    if missing:
        msg = f"match_fields {missing!r} not present in table {table.name!r}"
        raise ValueError(msg)
    return _resolve_upsert_strategy_cached(table, normalized, dialect_name)


@functools.cache
def _resolve_upsert_strategy_cached(
    table: Table,
    match_fields: tuple[str, ...],
    dialect_name: str,
) -> UpsertStrategy:
    """Cached arm of :func:`resolve_upsert_strategy`. Keyed by identity of ``table``."""
    kind, supports_returning = _native_primitive_for_dialect(dialect_name)
    if kind is None:
        return UpsertStrategy(
            kind="fallback",
            supports_returning=False,
            conflict_columns=match_fields,
            dialect_name=dialect_name,
        )

    match_set = set(match_fields)
    pk_cols = tuple(col.name for col in table.primary_key.columns)
    if pk_cols and set(pk_cols).issubset(match_set):
        return UpsertStrategy(
            kind=kind,
            supports_returning=supports_returning,
            conflict_columns=pk_cols,
            dialect_name=dialect_name,
        )

    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            uc_cols = tuple(col.name for col in constraint.columns)
            if uc_cols and set(uc_cols) == match_set:
                return UpsertStrategy(
                    kind=kind,
                    supports_returning=supports_returning,
                    conflict_columns=uc_cols,
                    dialect_name=dialect_name,
                )

    for idx in table.indexes:
        if not idx.unique:
            continue
        idx_cols = tuple(col.name for col in idx.columns)
        if idx_cols and set(idx_cols) == match_set:
            return UpsertStrategy(
                kind=kind,
                supports_returning=supports_returning,
                conflict_columns=idx_cols,
                dialect_name=dialect_name,
            )

    return UpsertStrategy(
        kind="fallback",
        supports_returning=False,
        conflict_columns=match_fields,
        dialect_name=dialect_name,
    )

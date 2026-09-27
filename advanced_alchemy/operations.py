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
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Optional, Union, cast
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import Boolean, Insert, Select, Table, UniqueConstraint, bindparam, insert, select, text
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.expression import Executable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable, Sequence

    from sqlalchemy.sql.compiler import SQLCompiler

UpsertKind = Literal["on_conflict", "merge", "insert_or_update", "fallback"]

__all__ = (
    "MergeStatement",
    "OnConflictUpsert",
    "UpsertKind",
    "UpsertStrategy",
    "resolve_upsert_strategy",
    "validate_identifier",
)

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


class _MergeSourceColumn(ColumnElement[Any]):
    """Dialect-quoted reference to a column on the MERGE ``src`` alias."""

    inherit_cache = True

    def __init__(self, column_name: str, column_type: Any) -> None:
        self.column_name = column_name
        self.type = column_type


@compiles(_MergeSourceColumn)
def _compile_merge_source_column(  # pyright: ignore[reportUnusedFunction]
    element: _MergeSourceColumn, compiler: "SQLCompiler", **kwargs: Any
) -> str:
    _ = kwargs
    return f"src.{compiler.preparer.quote(element.column_name)}"


class _MergeMatchCondition(ColumnElement[bool]):
    """Dialect-quoted equality predicates for MERGE target/source keys."""

    inherit_cache = True
    type = Boolean()

    def __init__(self, match_columns: "Sequence[str]") -> None:
        self.match_columns = tuple(match_columns)


@compiles(_MergeMatchCondition)
def _compile_merge_match_condition(  # pyright: ignore[reportUnusedFunction]
    element: _MergeMatchCondition, compiler: "SQLCompiler", **kwargs: Any
) -> str:
    _ = kwargs
    quote = compiler.preparer.quote
    return " AND ".join(f"tgt.{quote(column)} = src.{quote(column)}" for column in element.match_columns)


def _merge_source_column(table: Table, column_key: str) -> _MergeSourceColumn:
    column = table.c[column_key]
    return _MergeSourceColumn(column.name, column.type)


def _column_names(table: Table, column_keys: "Iterable[str]") -> tuple[str, ...]:
    """Translate ``Column.key`` values to database column names for SQL rendering."""
    return tuple(table.c[column_key].name for column_key in column_keys)


POSTGRES_MERGE_VERSION = 15


@compiles(MergeStatement)
def compile_merge_default(element: MergeStatement, compiler: "SQLCompiler", **kwargs: Any) -> str:
    """Default compilation - raises error for unsupported dialects."""
    _ = element, kwargs
    dialect_name = compiler.dialect.name
    msg = f"MERGE statement not supported for dialect '{dialect_name}'"
    raise NotImplementedError(msg)


@compiles(MergeStatement, "oracle")
def compile_merge_oracle(element: MergeStatement, compiler: "SQLCompiler", **kwargs: Any) -> str:
    """Compile MERGE statement for Oracle."""
    quote = compiler.preparer.quote
    table_name = compiler.preparer.format_table(element.table)

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
        updates: list[str] = [
            f"tgt.{quote(column)} = {compiler.process(value, **kwargs)}"
            for column, value in element.when_matched_update.items()
        ]
        merge_sql += ", ".join(updates)

    if element.when_not_matched_insert:
        columns = list(element.when_not_matched_insert.keys())
        values = list(element.when_not_matched_insert.values())

        merge_sql += " WHEN NOT MATCHED THEN INSERT ("
        merge_sql += ", ".join(quote(column) for column in columns)
        merge_sql += ") VALUES ("

        compiled_values: list[str] = [compiler.process(value, **kwargs) for value in values]
        merge_sql += ", ".join(compiled_values)
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

    quote = compiler.preparer.quote
    table_name = compiler.preparer.format_table(element.table)

    if isinstance(element.source, str):
        source_clause = f"({element.source}) AS src"
    else:
        compiled_source = compiler.process(element.source, **kwargs)
        compiled_trim = compiled_source.strip()
        if compiled_trim.startswith("("):
            has_outer_alias = (
                re.search(r"\)\s+(AS\s+)?[a-zA-Z_][a-zA-Z0-9_]*\s*$", compiled_trim, re.IGNORECASE) is not None
            )
            source_clause = compiled_trim if has_outer_alias else f"{compiled_trim} AS src"
        else:
            source_clause = f"({compiled_trim}) AS src"

    merge_sql = f"MERGE INTO {table_name} AS tgt USING {source_clause} ON ("
    merge_sql += compiler.process(element.on_condition, **kwargs)
    merge_sql += ")"

    if element.when_matched_update:
        merge_sql += " WHEN MATCHED THEN UPDATE SET "
        updates: list[str] = [
            f"{quote(column)} = {compiler.process(value, **kwargs)}"
            for column, value in element.when_matched_update.items()
        ]
        merge_sql += ", ".join(updates)

    if element.when_not_matched_insert:
        columns = list(element.when_not_matched_insert.keys())
        values = list(element.when_not_matched_insert.values())

        merge_sql += " WHEN NOT MATCHED THEN INSERT ("
        merge_sql += ", ".join(quote(column) for column in columns)
        merge_sql += ") VALUES ("

        compiled_values: list[str] = [compiler.process(value, **kwargs) for value in values]
        merge_sql += ", ".join(compiled_values)
        merge_sql += ")"

    return merge_sql


@compiles(MergeStatement, "mssql")
def compile_merge_mssql(element: MergeStatement, compiler: "SQLCompiler", **kwargs: Any) -> str:
    """Compile MERGE for SQL Server.

    Emits T-SQL form:

        MERGE INTO {table} AS tgt
        USING (VALUES (...), (...)) AS src(col1, col2)
        ON tgt.col = src.col [AND ...]
        WHEN MATCHED THEN UPDATE SET tgt.col = src.col [, ...]
        WHEN NOT MATCHED THEN INSERT (col1, ...) VALUES (src.col1, ...)
        ;

    The trailing semicolon is required for T-SQL MERGE. The repository hydrates
    with one exact-key re-SELECT; emitting ``OUTPUT inserted.*`` here would
    transfer the same rows twice. All identifiers are quoted via
    ``compiler.preparer`` so reserved words like ``key`` survive.
    """
    quote = compiler.preparer.quote
    table_name = compiler.preparer.format_table(element.table)

    if isinstance(element.source, str):
        source_clause = f"({element.source})"
    else:
        compiled_source = compiler.process(element.source, **kwargs)
        compiled_trim = compiled_source.strip()
        source_clause = compiled_trim if compiled_trim.startswith("(") else f"({compiled_trim})"

    merge_sql = f"MERGE INTO {table_name} AS tgt USING {source_clause} ON ("
    merge_sql += compiler.process(element.on_condition, **kwargs)
    merge_sql += ")"

    if element.when_matched_update:
        merge_sql += " WHEN MATCHED THEN UPDATE SET "
        updates: list[str] = [
            f"tgt.{quote(column)} = {compiler.process(value, **kwargs)}"
            for column, value in element.when_matched_update.items()
        ]
        merge_sql += ", ".join(updates)

    if element.when_not_matched_insert:
        columns = list(element.when_not_matched_insert.keys())
        values = list(element.when_not_matched_insert.values())

        merge_sql += " WHEN NOT MATCHED THEN INSERT ("
        merge_sql += ", ".join(quote(col) for col in columns)
        merge_sql += ") VALUES ("

        compiled_values: list[str] = [compiler.process(value, **kwargs) for value in values]
        merge_sql += ", ".join(compiled_values)
        merge_sql += ")"

    merge_sql += ";"
    return merge_sql


class OnConflictUpsert:
    """Cross-database upsert operation using dialect-specific constructs.

    This class provides a unified interface for upsert operations across
    different database backends using their native ON CONFLICT,
    ON DUPLICATE KEY UPDATE, MERGE, or INSERT OR UPDATE mechanisms.
    """

    @staticmethod
    def supports_native_upsert(dialect_name: str) -> bool:
        """Check if the dialect supports the single-row ``create_upsert`` API.

        This flag is scoped to the per-row ``INSERT ... ON CONFLICT`` /
        ``ON DUPLICATE KEY UPDATE`` dialects that
        :meth:`OnConflictUpsert.create_upsert` can compile directly. The
        bulk ``MERGE`` (mssql, oracle) and ``INSERT OR UPDATE`` (spanner)
        primitives are dispatched separately by
        :meth:`Repository.upsert_many` via :func:`resolve_upsert_strategy`
        and are intentionally **not** reported here.

        Args:
            dialect_name: Name of the database dialect

        Returns:
            ``True`` for postgresql / cockroachdb / sqlite / mysql /
            mariadb / duckdb; ``False`` otherwise.
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
            A SQLAlchemy ``Insert`` for the ON-CONFLICT dialects (postgresql /
            cockroachdb / sqlite / duckdb / mysql / mariadb). MSSQL, Oracle,
            and Spanner are handled by the bulk ``MERGE`` / ``INSERT OR UPDATE``
            path in :func:`OnConflictUpsert.create_merge_many` and
            :func:`OnConflictUpsert.create_insert_or_update_many`, accessed through
            :func:`resolve_upsert_strategy` from the repository layer.

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

        update_columns = _resolve_update_columns(table, values, conflict_columns, update_columns)

        if dialect_name in {"postgresql", "sqlite", "duckdb", "cockroachdb"}:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_insert_stmt = pg_insert(table).values(values)
            index_elements = [table.c[col] for col in conflict_columns]
            if not update_columns:
                return pg_insert_stmt.on_conflict_do_nothing(index_elements=index_elements)
            return pg_insert_stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_={col: pg_insert_stmt.excluded[col] for col in update_columns},
            )

        if dialect_name in {"mysql", "mariadb"}:
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_insert_stmt = mysql_insert(table).values(values)
            mysql_updates = (
                {col: mysql_insert_stmt.inserted[col] for col in update_columns}
                if update_columns
                else {conflict_columns[0]: mysql_insert_stmt.inserted[conflict_columns[0]]}
            )
            return mysql_insert_stmt.on_duplicate_key_update(**mysql_updates)

        msg = f"Native upsert not supported for dialect '{dialect_name}'"
        raise NotImplementedError(msg)

    @staticmethod
    def create_insert_or_update_many(table: Table, rows: "Sequence[dict[str, Any]]") -> Insert:
        """Create a Spanner ``INSERT OR UPDATE`` using SQLAlchemy's Insert.

        A regular :class:`~sqlalchemy.sql.dml.Insert` retains result-column
        metadata, allowing callers to add ``returning(model_type)``. The
        Spanner dialect compiles that combination to ``THEN RETURN``.

        Args:
            table: Target table for the upsert.
            rows: Homogeneous rows to insert or update.

        Returns:
            A multi-values insert prefixed with Spanner's ``OR UPDATE`` token.

        Raises:
            ValueError: ``rows`` is empty or rows have heterogeneous keys.
        """
        _validate_bulk_inputs(rows, (), None, False)
        prepared_rows = _apply_pk_defaults(table, rows)
        return insert(table).prefix_with("OR UPDATE").values(prepared_rows)

    @staticmethod
    def create_merge_upsert(  # noqa: C901
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
        directly in the INSERT clause. Since Oracle requires ``FROM DUAL`` for ``SELECT``
        statements without tables, the Oracle source subquery selects from ``DUAL``.

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

        update_columns = _resolve_update_columns(table, values, conflict_columns, update_columns)

        additional_params: dict[str, Any] = {}
        source: Union[ClauseElement, str]
        when_not_matched_insert: dict[str, Any]

        if dialect_name == "oracle":
            labeled_columns: list[ColumnElement[Any]] = []
            for key, value in values.items():
                column = table.c[key]
                labeled_columns.append(bindparam(key, value=value, type_=column.type).label(column.name))
            when_not_matched_insert = {table.c[key].name: _merge_source_column(table, key) for key in values}

            for pk_column in table.primary_key.columns:
                if pk_column.key in values or pk_column.default is None:
                    continue
                arg = getattr(pk_column.default, "arg", None)
                if callable(arg):
                    default_value = resolve_column_default(arg)
                    if isinstance(default_value, UUID):
                        default_value = default_value.hex
                    additional_params[pk_column.name] = default_value
                    labeled_columns.append(
                        bindparam(pk_column.name, value=default_value, type_=pk_column.type).label(pk_column.name)
                    )
                    when_not_matched_insert[pk_column.name] = _MergeSourceColumn(pk_column.name, pk_column.type)
                elif hasattr(pk_column.default, "next_value"):
                    when_not_matched_insert[pk_column.name] = cast("Any", pk_column.default).next_value()

            source = select(*labeled_columns).select_from(text("DUAL")).subquery("src")

        elif dialect_name in {"postgresql", "cockroachdb"}:
            labeled_columns = []
            for key, value in values.items():
                column = table.c[key]
                bp = bindparam(f"src_{key}", value=value, type_=column.type)
                labeled_columns.append(bp.label(column.name))
            source = select(*labeled_columns).subquery("src")
            when_not_matched_insert = {table.c[key].name: _merge_source_column(table, key) for key in values}
        else:
            placeholders = ", ".join([f"%({key})s" for key in values])
            col_names = ", ".join(_column_names(table, values))
            source = f"(SELECT * FROM (VALUES ({placeholders})) AS src({col_names}))"  # noqa: S608
            when_not_matched_insert = {table.c[key].name: bindparam(key) for key in values}

        on_condition = _MergeMatchCondition(_column_names(table, conflict_columns))

        if dialect_name in {"postgresql", "cockroachdb", "oracle"}:
            when_matched_update: dict[str, Any] = {
                table.c[col].name: _merge_source_column(table, col) for col in update_columns if col in values
            }
        else:
            when_matched_update = {table.c[col].name: bindparam(col) for col in update_columns if col in values}

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
        rows: "Sequence[dict[str, Any]]",
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
        dialect_name: Optional[str] = None,
        validate_identifiers: bool = False,
        model_type: Optional[type[Any]] = None,
    ) -> Insert:
        """Build a dialect-specific bulk Insert with ON CONFLICT / ON DUPLICATE KEY UPDATE.

        Compiles to a single ``INSERT ... VALUES (...), (...), ...`` per chunk so the
        round-trip cost is fixed regardless of batch size.

        Args:
            table: Target table for the upsert.
            rows: Rows to insert/update. All rows MUST share the same keys.
            conflict_columns: Columns that define the conflict / match condition.
            update_columns: Columns to update on conflict (defaults to all
                non-conflict keys from the first row).
            dialect_name: Database dialect name; determines compile path.
            validate_identifiers: If True, validate column identifiers for safety.
            model_type: Optional ORM model target used for ORM-aware RETURNING.

        Returns:
            A SQLAlchemy ``Insert`` statement configured for bulk upsert.

        Raises:
            ValueError: ``rows`` is empty, rows have heterogeneous keys,
                or identifier validation fails.
            NotImplementedError: The dialect does not support an ON CONFLICT
                style native bulk upsert.
        """
        _validate_bulk_inputs(rows, conflict_columns, update_columns, validate_identifiers)

        resolved_update_columns = _resolve_update_columns(
            table,
            rows[0],
            conflict_columns,
            update_columns,
        )
        insert_target: Union[Table, type[Any]] = model_type if model_type is not None else table

        if dialect_name in {"postgresql", "sqlite", "duckdb", "cockroachdb"}:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_stmt = pg_insert(insert_target).values(list(rows))
            index_elements = [table.c[col] for col in conflict_columns]
            if not resolved_update_columns:
                return pg_stmt.on_conflict_do_nothing(index_elements=index_elements)
            return pg_stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_={col: pg_stmt.excluded[col] for col in resolved_update_columns},
            )

        if dialect_name in {"mysql", "mariadb"}:
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            mysql_stmt = mysql_insert(insert_target).values(list(rows))
            mysql_updates = (
                {col: mysql_stmt.inserted[col] for col in resolved_update_columns}
                if resolved_update_columns
                else {conflict_columns[0]: mysql_stmt.inserted[conflict_columns[0]]}
            )
            return mysql_stmt.on_duplicate_key_update(**mysql_updates)

        msg = f"Native bulk upsert not supported for dialect '{dialect_name}'"
        raise NotImplementedError(msg)

    @staticmethod
    def create_merge_many(
        table: Table,
        rows: "Sequence[dict[str, Any]]",
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
        dialect_name: Optional[str] = None,
        validate_identifiers: bool = False,
    ) -> MergeStatement:
        """Build a multi-row ``MergeStatement`` for dialects with native MERGE support.

        Args:
            table: Target table for the upsert.
            rows: Rows to insert/update. All rows MUST share the same keys.
            conflict_columns: Columns that define the matching condition.
            update_columns: Columns to update on match (defaults to all non-conflict
                keys from the first row).
            dialect_name: Database dialect name; selects the source construction.
            validate_identifiers: If True, validate column identifiers for safety.

        Returns:
            A single :class:`MergeStatement` binding all input rows.

        Raises:
            ValueError: ``rows`` is empty, rows have heterogeneous keys,
                or identifier validation fails.
            NotImplementedError: The dialect does not support bulk MERGE compilation.
        """
        _validate_bulk_inputs(rows, conflict_columns, update_columns, validate_identifiers)
        prepared_rows = _apply_pk_defaults(table, rows)
        column_keys = list(prepared_rows[0].keys())

        resolved_update_columns = _resolve_update_columns(
            table,
            column_keys,
            conflict_columns,
            update_columns,
        )

        if dialect_name == "oracle":
            source = _build_union_merge_source(table, prepared_rows, column_keys, use_dual=True)
        elif dialect_name in {"postgresql", "cockroachdb"}:
            source = _build_union_merge_source(table, prepared_rows, column_keys, use_dual=False)
        elif dialect_name == "mssql":
            source = _build_values_merge_source(table, prepared_rows, column_keys)
        else:
            msg = f"Native bulk MERGE not supported for dialect '{dialect_name}'"
            raise NotImplementedError(msg)

        return _build_merge_statement(table, source, column_keys, conflict_columns, resolved_update_columns)


def _resolve_update_columns(
    table: Table,
    available_columns: "Iterable[str]",
    conflict_columns: "Sequence[str]",
    update_columns: Optional["Sequence[str]"],
) -> list[str]:
    """Return update columns without keys that identify the target row.

    Updating a primary key during an upsert is unsafe when a different unique
    key is used as the conflict target, and Oracle rejects updates to columns
    referenced by the MERGE ``ON`` clause. Apply the same rule to every
    dialect so the operation has portable semantics.
    """
    protected_columns = set(conflict_columns)
    for column in table.primary_key.columns:
        protected_columns.add(column.key)
        protected_columns.add(column.name)
    candidate_columns = list(update_columns) if update_columns is not None else list(available_columns)
    return [column for column in candidate_columns if column not in protected_columns]


def resolve_column_default(arg: Any) -> Any:
    """Invoke a SQLAlchemy ``ColumnDefault.arg`` callable, tolerating both signatures.

    SQLAlchemy accepts both context-taking defaults (``lambda ctx: …``) and
    zero-arg defaults (``lambda: …``, ``uuid7``, ``datetime.utcnow``). The
    context-taking shape is attempted first with ``None``; a signature
    mismatch retries the zero-arg shape. Errors raised inside the default
    itself — including a context-sensitive default that dereferences the
    ``None`` context — propagate so callers can route the operation through
    the ORM flush, where a real execution context is available.
    """
    try:
        return arg(None)
    except TypeError:
        return arg()


def _apply_pk_defaults(
    table: Table,
    rows: "Sequence[dict[str, Any]]",
) -> list[dict[str, Any]]:
    """Invoke Python-callable PK defaults for any rows missing those columns.

    Callers that construct values dicts without primary keys expect Python
    ``default=uuid7`` factories to populate before statement compilation when
    bypassing the ORM flush. Columns without a Python callable default
    (autoincrement / IDENTITY / Sequence) are left untouched so the database
    supplies them.
    """
    if not rows:
        return list(rows)
    first_keys = set(rows[0].keys())
    pk_defaults: list[tuple[str, Any]] = []
    for pk_col in table.primary_key.columns:
        if pk_col.name in first_keys:
            continue
        default = pk_col.default
        arg = getattr(default, "arg", None) if default is not None else None
        if callable(arg):
            pk_defaults.append((pk_col.name, arg))
    if not pk_defaults:
        return list(rows)
    augmented: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        for col_name, arg in pk_defaults:
            new_row[col_name] = resolve_column_default(arg)
        augmented.append(new_row)
    return augmented


def _validate_bulk_inputs(
    rows: "Sequence[dict[str, Any]]",
    conflict_columns: "Sequence[str]",
    update_columns: Optional["Sequence[str]"],
    validate_identifiers_flag: bool,
) -> None:
    """Validate non-empty homogeneous rows and optional SQL identifier safety."""
    if not rows:
        msg = "rows must not be empty"
        raise ValueError(msg)
    first_keys = set(rows[0].keys())
    for idx, row in enumerate(rows[1:], start=1):
        if set(row.keys()) != first_keys:
            msg = f"All entries in rows must share the same keys (row {idx} differs from row 0)"
            raise ValueError(msg)
    if validate_identifiers_flag:
        for col in conflict_columns:
            validate_identifier(col, "conflict column")
        if update_columns:
            for col in update_columns:
                validate_identifier(col, "update column")
        for col in first_keys:
            validate_identifier(col, "column")


def _build_union_merge_source(
    table: Table,
    rows: "Sequence[dict[str, Any]]",
    column_keys: "Sequence[str]",
    *,
    use_dual: bool,
) -> ClauseElement:
    """Construct a ``SELECT ... [FROM DUAL] UNION ALL ...`` subquery aliased as ``src``."""
    param_prefix = "row" if use_dual else "src_row"
    per_row_selects: list[Select[Any]] = []

    for idx, row in enumerate(rows):
        row_columns: list[ColumnElement[Any]] = [
            bindparam(f"{param_prefix}{idx}_{key}", value=row[key], type_=table.c[key].type).label(table.c[key].name)
            for key in column_keys
        ]
        row_select = select(*row_columns)
        if use_dual:
            row_select = row_select.select_from(text("DUAL"))
        per_row_selects.append(row_select)

    unified = per_row_selects[0] if len(per_row_selects) == 1 else per_row_selects[0].union_all(*per_row_selects[1:])
    return unified.subquery("src")


def _build_values_merge_source(
    table: Table,
    rows: "Sequence[dict[str, Any]]",
    column_keys: "Sequence[str]",
) -> ClauseElement:
    """Construct an MSSQL ``(VALUES (...)) AS src(...)`` clause with bound parameters.

    Using ``text()`` with explicit :class:`~sqlalchemy.sql.expression.BindParameter`
    children lets the MSSQL compiler translate the ``:row0_*`` markers to
    ``?`` placeholders that pyodbc understands. Column identifiers are
    bracket-quoted (``[name]``) so reserved T-SQL keywords survive.
    """
    quoted_cols = ["[" + table.c[key].name.replace("]", "]]") + "]" for key in column_keys]
    col_names = ", ".join(quoted_cols)
    bp_objects: list[Any] = []
    row_fragments: list[str] = []
    for idx, row in enumerate(rows):
        placeholders: list[str] = []
        for col_key in column_keys:
            bp_name = f"row{idx}_{col_key}"
            bp_objects.append(bindparam(bp_name, value=row[col_key], type_=table.c[col_key].type))
            placeholders.append(f":{bp_name}")
        row_fragments.append(f"({', '.join(placeholders)})")
    return text(f"(VALUES {', '.join(row_fragments)}) AS src({col_names})").bindparams(*bp_objects)


def _build_merge_statement(
    table: Table,
    source: ClauseElement,
    column_keys: "Sequence[str]",
    conflict_columns: "Sequence[str]",
    update_columns: "Sequence[str]",
) -> MergeStatement:
    """Assemble a :class:`MergeStatement` from a multi-row source clause."""
    key_set = set(column_keys)
    when_not_matched_insert: dict[str, Any] = {
        table.c[key].name: _merge_source_column(table, key) for key in column_keys
    }
    when_matched_update: dict[str, Any] = {
        table.c[col].name: _merge_source_column(table, col) for col in update_columns if col in key_set
    }
    on_condition = _MergeMatchCondition(_column_names(table, conflict_columns))
    return MergeStatement(
        table=table,
        source=source,
        on_condition=on_condition,
        when_matched_update=when_matched_update,
        when_not_matched_insert=when_not_matched_insert,
    )


class UpsertStrategy(NamedTuple):
    """Dispatch decision returned by :func:`resolve_upsert_strategy`.

    Tells the repository which native primitive to compile (``on_conflict`` /
    ``merge`` / ``insert_or_update``) or whether to take the existing
    SELECT-then-partition fallback. The ``conflict_columns`` field is the
    *validated* unique key (PK / UniqueConstraint / unique Index) and has
    exactly the same columns as the caller's ``match_fields``.
    """

    kind: UpsertKind
    supports_returning: bool
    conflict_columns: tuple[str, ...]
    dialect_name: str


_DIALECTS_ON_CONFLICT_RETURNING: frozenset[str] = frozenset({"postgresql", "cockroachdb", "sqlite", "duckdb"})
_DIALECTS_ON_CONFLICT_NO_RETURNING: frozenset[str] = frozenset({"mysql", "mariadb"})
_DIALECTS_MERGE: frozenset[str] = frozenset({"oracle", "mssql"})
_DIALECTS_INSERT_OR_UPDATE: frozenset[str] = frozenset({"spanner", "spanner+spanner"})
_UPSERT_STRATEGY_CACHE: "WeakKeyDictionary[Table, dict[tuple[Any, ...], UpsertStrategy]]" = WeakKeyDictionary()


def _parse_dialect(dialect: Union[str, Dialect]) -> tuple[str, Optional[bool]]:
    """Extract ``(dialect_name, insert_returning)`` from a dialect name or ``Dialect`` instance."""
    if isinstance(dialect, str):
        return dialect, None
    return dialect.name, bool(dialect.insert_returning)


def _native_primitive_for_dialect(
    dialect_name: str, insert_returning: Optional[bool] = None
) -> tuple[Optional[UpsertKind], bool]:
    """Return ``(kind, supports_returning)`` for the dialect's native upsert primitive.

    Returns ``(None, False)`` for dialects without a native primitive (fallback).
    """
    if dialect_name in _DIALECTS_ON_CONFLICT_RETURNING:
        return ("on_conflict", True if insert_returning is None else insert_returning)
    if dialect_name in _DIALECTS_ON_CONFLICT_NO_RETURNING:
        return ("on_conflict", False)
    if dialect_name in _DIALECTS_MERGE:
        return ("merge", False)
    if dialect_name in _DIALECTS_INSERT_OR_UPDATE:
        return ("insert_or_update", True if insert_returning is None else insert_returning)
    return (None, False)


def _get_native_unique_index_columns(index: Any) -> tuple[str, ...]:
    """Return simple unique-index columns, excluding filtered/expressional forms."""
    if not index.unique:
        return ()
    if any(index.dialect_options[dialect].get("where") is not None for dialect in ("postgresql", "sqlite", "mssql")):
        return ()
    index_columns = tuple(index.columns)
    if len(index_columns) != len(index.expressions) or any(
        expression is not column for expression, column in zip(index.expressions, index_columns)
    ):
        return ()
    return tuple(col.key for col in index_columns)


def _mysql_unique_target_is_ambiguous(table: Table, primary_key_columns: tuple[str, ...]) -> bool:
    """Return whether MySQL could update through an unintended unique key."""
    unique_keys: set[frozenset[str]] = set()
    if primary_key_columns:
        unique_keys.add(frozenset(primary_key_columns))
    unique_keys.update(
        frozenset(col.key for col in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    unique_keys.update(
        frozenset(index_columns)
        for index in table.indexes
        if (index_columns := _get_native_unique_index_columns(index))
    )
    return len(unique_keys) > 1


def resolve_upsert_strategy(
    table: Table,
    match_fields: "Sequence[str]",
    dialect: Union[str, Dialect],
) -> UpsertStrategy:
    """Resolve the optimal upsert strategy for ``(table, match_fields, dialect)``.

    The result is cached for the process lifetime; ``Table`` objects are
    singletons per declarative class, so this is one decision per
    ``(model, match_fields, dialect)`` tuple.

    Resolution priority:

    1. ``match_fields`` equals the table's primary key →
       native primitive for the dialect, ``conflict_columns`` is the PK.
    2. A :class:`~sqlalchemy.UniqueConstraint` whose columns match exactly →
       native primitive where the backend can target it, ``conflict_columns``
       is that constraint's columns.
    3. A unique :class:`~sqlalchemy.Index` whose columns match exactly →
       native primitive where the backend can target it, ``conflict_columns``
       is that index's columns. Spanner ``INSERT OR UPDATE`` only matches the
       primary key, and ambiguous MySQL/MariaDB unique targets fall back.
    4. Otherwise → ``kind="fallback"``, ``supports_returning=False``. This
       includes ``match_fields`` entries that do not resolve to table columns
       (mapped attributes whose name differs from the column key, synonyms,
       hybrids) — the ORM fallback resolves those via ``getattr``.

    Args:
        table: Target table. Used by identity for caching.
        match_fields: Columns the caller wants to match on. Order-insensitive.
        dialect: Database dialect or dialect name. Passing the runtime dialect
            allows the resolver to honor its actual RETURNING capability.

    Returns:
        An :class:`UpsertStrategy` describing the decision.

    Raises:
        ValueError: ``match_fields`` is empty.
    """
    if not match_fields:
        msg = "match_fields must not be empty"
        raise ValueError(msg)
    normalized = tuple(sorted(set(match_fields)))
    resolved_dialect_name, insert_returning = _parse_dialect(dialect)
    table_columns = set(table.c.keys())
    if any(column_name not in table_columns for column_name in normalized):
        return UpsertStrategy(
            kind="fallback",
            supports_returning=False,
            conflict_columns=normalized,
            dialect_name=resolved_dialect_name,
        )
    table_cache = _UPSERT_STRATEGY_CACHE.setdefault(table, {})
    cache_key = (normalized, resolved_dialect_name, insert_returning)
    strategy = table_cache.get(cache_key)
    if strategy is None:
        strategy = _resolve_upsert_strategy(table, normalized, resolved_dialect_name, insert_returning)
        table_cache[cache_key] = strategy
    return strategy


def _resolve_upsert_strategy(
    table: Table,
    match_fields: tuple[str, ...],
    dialect_name: str,
    insert_returning: Optional[bool],
) -> UpsertStrategy:
    """Resolution logic behind :func:`resolve_upsert_strategy`; results are memoized per table."""
    kind, supports_returning = _native_primitive_for_dialect(dialect_name, insert_returning)
    match_set = set(match_fields)
    primary_key_columns = tuple(column.key for column in table.primary_key.columns)
    native_conflict_columns: Optional[tuple[str, ...]] = None
    if kind is not None and primary_key_columns and set(primary_key_columns) == match_set:
        native_conflict_columns = primary_key_columns
    elif kind is not None and kind != "insert_or_update":
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                if constraint.deferrable:
                    continue
                unique_constraint_columns = tuple(column.key for column in constraint.columns)
                if unique_constraint_columns and set(unique_constraint_columns) == match_set:
                    native_conflict_columns = unique_constraint_columns
                    break

        if native_conflict_columns is None:
            for index in table.indexes:
                unique_index_columns = _get_native_unique_index_columns(index)
                if unique_index_columns and set(unique_index_columns) == match_set:
                    native_conflict_columns = unique_index_columns
                    break

    mysql_target_is_ambiguous = dialect_name in {"mysql", "mariadb"} and _mysql_unique_target_is_ambiguous(
        table, primary_key_columns
    )
    if kind is not None and native_conflict_columns is not None and not mysql_target_is_ambiguous:
        return UpsertStrategy(
            kind=kind,
            supports_returning=supports_returning,
            conflict_columns=native_conflict_columns,
            dialect_name=dialect_name,
        )
    return UpsertStrategy(
        kind="fallback",
        supports_returning=False,
        conflict_columns=match_fields,
        dialect_name=dialect_name,
    )

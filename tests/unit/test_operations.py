"""Tests for advanced_alchemy.operations module."""

from typing import Any

import pytest
from sqlalchemy import Column, Index, Integer, MetaData, String, Table, UniqueConstraint

from advanced_alchemy.operations import MergeStatement, OnConflictUpsert, validate_identifier


@pytest.fixture
def sample_table() -> Table:
    """Create a sample table for testing."""
    metadata = MetaData()
    return Table(
        "test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("key", String(50), nullable=False),
        Column("namespace", String(50), nullable=False),
        Column("value", String(255)),
    )


class TestOnConflictUpsert:
    """Test OnConflictUpsert operations."""

    def test_supports_native_upsert(self) -> None:
        """Test dialect support detection."""
        # Supported dialects
        assert OnConflictUpsert.supports_native_upsert("postgresql") is True
        assert OnConflictUpsert.supports_native_upsert("cockroachdb") is True
        assert OnConflictUpsert.supports_native_upsert("sqlite") is True
        assert OnConflictUpsert.supports_native_upsert("mysql") is True
        assert OnConflictUpsert.supports_native_upsert("mariadb") is True
        assert OnConflictUpsert.supports_native_upsert("duckdb") is True
        assert OnConflictUpsert.supports_native_upsert("mssql") is True
        assert OnConflictUpsert.supports_native_upsert("spanner") is True

        # Unsupported dialects
        assert OnConflictUpsert.supports_native_upsert("oracle") is False
        assert OnConflictUpsert.supports_native_upsert("unknown") is False

    def test_create_upsert_mssql_delegates_to_merge_statement(self, sample_table: Table) -> None:
        values = {"key": "k1", "namespace": "ns", "value": "v1"}
        stmt = OnConflictUpsert.create_upsert(
            table=sample_table,
            values=values,
            conflict_columns=["key", "namespace"],
            dialect_name="mssql",
        )
        assert isinstance(stmt, MergeStatement)

    def test_create_upsert_spanner_returns_spanner_upsert(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import SpannerUpsert

        values = {"key": "k1", "namespace": "ns", "value": "v1"}
        stmt = OnConflictUpsert.create_upsert(
            table=sample_table,
            values=values,
            conflict_columns=["key", "namespace"],
            dialect_name="spanner",
        )
        assert isinstance(stmt, SpannerUpsert)
        assert len(stmt.values_list) == 1

    def test_create_postgresql_upsert(self, sample_table: Table) -> None:
        """Test PostgreSQL ON CONFLICT upsert generation."""
        values = {"key": "test_key", "namespace": "test_ns", "value": "test_value"}
        conflict_columns = ["key", "namespace"]

        upsert_stmt = OnConflictUpsert.create_upsert(
            table=sample_table,
            values=values,
            conflict_columns=conflict_columns,
            dialect_name="postgresql",
        )

        # Should return a PostgreSQL insert statement with ON CONFLICT
        # This is primarily testing that the method doesn't raise an exception
        # and returns the expected type
        assert upsert_stmt is not None
        assert hasattr(upsert_stmt, "on_conflict_do_update")

    def test_create_mysql_upsert(self, sample_table: Table) -> None:
        """Test MySQL ON DUPLICATE KEY UPDATE upsert generation."""
        values = {"key": "test_key", "namespace": "test_ns", "value": "test_value"}
        conflict_columns = ["key", "namespace"]

        upsert_stmt = OnConflictUpsert.create_upsert(
            table=sample_table,
            values=values,
            conflict_columns=conflict_columns,
            dialect_name="mysql",
        )

        # Should return a MySQL insert statement with ON DUPLICATE KEY UPDATE
        assert upsert_stmt is not None
        assert hasattr(upsert_stmt, "on_duplicate_key_update")

    def test_create_duckdb_upsert(self, sample_table: Table) -> None:
        """Test DuckDB ON CONFLICT upsert generation."""
        values = {"key": "test_key", "namespace": "test_ns", "value": "test_value"}
        conflict_columns = ["key", "namespace"]

        upsert_stmt = OnConflictUpsert.create_upsert(
            table=sample_table,
            values=values,
            conflict_columns=conflict_columns,
            dialect_name="duckdb",
        )

        # Should return a PostgreSQL-style insert statement with ON CONFLICT (DuckDB uses PostgreSQL syntax)
        assert upsert_stmt is not None
        assert hasattr(upsert_stmt, "on_conflict_do_update")

    def test_create_upsert_unsupported_dialect(self, sample_table: Table) -> None:
        """Test that unsupported dialects raise NotImplementedError."""
        values = {"key": "test_key", "namespace": "test_ns", "value": "test_value"}
        conflict_columns = ["key", "namespace"]

        with pytest.raises(NotImplementedError, match="Native upsert not supported for dialect 'oracle'"):
            OnConflictUpsert.create_upsert(
                table=sample_table,
                values=values,
                conflict_columns=conflict_columns,
                dialect_name="oracle",
            )

    def test_create_merge_upsert(self, sample_table: Table) -> None:
        """Test MERGE-based upsert generation."""
        values = {"key": "test_key", "namespace": "test_ns", "value": "test_value"}
        conflict_columns = ["key", "namespace"]

        # Test default (non-Oracle) MERGE
        merge_stmt, additional_params = OnConflictUpsert.create_merge_upsert(
            table=sample_table,
            values=values,
            conflict_columns=conflict_columns,
        )

        assert isinstance(merge_stmt, MergeStatement)
        assert merge_stmt.table == sample_table
        # Default dialect (None) uses PostgreSQL format with %(key)s notation
        assert "%(key)s" in str(merge_stmt.source) or ":key" in str(
            merge_stmt.source
        )  # Check for parameter placeholder
        assert "FROM DUAL" not in str(merge_stmt.source)  # Should not have FROM DUAL by default
        assert additional_params == {}  # No additional params for non-Oracle

        # Test Oracle-specific MERGE
        oracle_merge_stmt, oracle_additional_params = OnConflictUpsert.create_merge_upsert(
            table=sample_table,
            values=values,
            conflict_columns=conflict_columns,
            dialect_name="oracle",
        )

        assert isinstance(oracle_merge_stmt, MergeStatement)
        assert oracle_merge_stmt.table == sample_table
        assert ":key" in str(oracle_merge_stmt.source)  # Check for parameter placeholder
        assert "FROM DUAL" in str(oracle_merge_stmt.source)  # Oracle should have FROM DUAL
        # Additional params should be empty for tables without UUID primary keys
        assert isinstance(oracle_additional_params, dict)
        assert "SELECT" in str(merge_stmt.source)


class TestMergeStatement:
    """Test MergeStatement compilation."""

    def test_merge_statement_creation(self, sample_table: Table) -> None:
        """Test basic MergeStatement creation."""
        from sqlalchemy import bindparam, text

        source = "SELECT 'key1' as key, 'ns1' as namespace, 'value1' as value"
        on_condition = text("tgt.key = src.key AND tgt.namespace = src.namespace")
        when_matched_update: dict[str, Any] = {"value": bindparam("value")}
        when_not_matched_insert: dict[str, Any] = {
            "key": bindparam("key"),
            "namespace": bindparam("namespace"),
            "value": bindparam("value"),
        }

        merge_stmt = MergeStatement(
            table=sample_table,
            source=source,
            on_condition=on_condition,
            when_matched_update=when_matched_update,
            when_not_matched_insert=when_not_matched_insert,
        )

        assert merge_stmt.table == sample_table
        assert merge_stmt.source == source
        assert merge_stmt.on_condition == on_condition
        assert merge_stmt.when_matched_update == when_matched_update
        assert merge_stmt.when_not_matched_insert == when_not_matched_insert

    def test_compile_merge_default_raises_error(self, sample_table: Table) -> None:
        """Test that default compiler raises NotImplementedError."""
        from sqlalchemy import text

        from advanced_alchemy.operations import compile_merge_default

        merge_stmt = MergeStatement(
            table=sample_table,
            source="SELECT 1",
            on_condition=text("1=1"),
        )

        # Create a mock compiler for an unsupported dialect
        class MockDialect:
            name = "unsupported"

        class MockCompiler:
            dialect = MockDialect()

        compiler = MockCompiler()

        with pytest.raises(NotImplementedError, match="MERGE statement not supported for dialect 'unsupported'"):
            compile_merge_default(merge_stmt, compiler)  # type: ignore[arg-type]  # pyright: ignore


class TestSpannerUpsert:
    """Tests for the Spanner INSERT_OR_UPDATE DML construct added in Ch.5."""

    def test_spanner_upsert_construction(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import SpannerUpsert

        upsert = SpannerUpsert(
            table=sample_table,
            values_list=[
                {"key": "k1", "namespace": "ns", "value": "v1"},
                {"key": "k2", "namespace": "ns", "value": "v2"},
            ],
        )
        assert upsert.table is sample_table
        assert len(upsert.values_list) == 2
        assert upsert.columns == ("key", "namespace", "value")

    def test_spanner_upsert_empty_values_raises(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import SpannerUpsert

        with pytest.raises(ValueError, match="values_list must not be empty"):
            SpannerUpsert(table=sample_table, values_list=[])

    def test_spanner_upsert_heterogeneous_keys_raises(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import SpannerUpsert

        with pytest.raises(ValueError, match="same keys"):
            SpannerUpsert(
                table=sample_table,
                values_list=[
                    {"key": "k1", "namespace": "ns", "value": "v1"},
                    {"key": "k2", "namespace": "ns"},
                ],
            )

    def test_spanner_upsert_compile_emits_insert_or_update(self, sample_table: Table) -> None:
        from sqlalchemy.engine.default import DefaultDialect

        from advanced_alchemy.operations import SpannerUpsert

        class _MockSpannerDialect(DefaultDialect):
            name = "spanner"

        upsert = SpannerUpsert(
            table=sample_table,
            values_list=[
                {"key": "k1", "namespace": "ns", "value": "v1"},
                {"key": "k2", "namespace": "ns", "value": "v2"},
            ],
        )
        compiled = str(upsert.compile(dialect=_MockSpannerDialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        upper = compiled.upper()
        assert "INSERT OR UPDATE INTO TEST_TABLE" in upper
        assert "(KEY, NAMESPACE, VALUE)" in upper
        assert upper.count("VALUES") == 1
        assert compiled.count("(") == 3

    def test_spanner_upsert_compile_default_dialect_raises(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import SpannerUpsert, compile_spanner_upsert_default

        upsert = SpannerUpsert(
            table=sample_table,
            values_list=[{"key": "k1", "namespace": "ns", "value": "v1"}],
        )

        class _MockDialect:
            name = "postgresql"

        class _MockCompiler:
            dialect = _MockDialect()

        with pytest.raises(NotImplementedError, match="SpannerUpsert"):
            compile_spanner_upsert_default(upsert, _MockCompiler())  # type: ignore[arg-type]


class TestMSSQLMergeCompile:
    """Tests for the MSSQL MergeStatement compile path added in Ch.4."""

    def test_mssql_compile_emits_using_values_source_and_output_inserted(self, sample_table: Table) -> None:
        from sqlalchemy.dialects import mssql

        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
        ]
        stmt, _ = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="mssql",
        )
        compiled = str(stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        upper = compiled.upper()
        assert "MERGE INTO TEST_TABLE AS TGT" in upper
        assert "USING (VALUES" in upper
        assert "AS SRC(" in upper
        assert "WHEN MATCHED THEN UPDATE SET" in upper
        assert "WHEN NOT MATCHED THEN INSERT" in upper
        assert "OUTPUT INSERTED.*" in upper
        assert compiled.rstrip().endswith(";")

    def test_mssql_compile_trailing_semicolon_is_mandatory(self, sample_table: Table) -> None:
        from sqlalchemy.dialects import mssql

        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        stmt, _ = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="mssql",
        )
        compiled = str(stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        assert compiled.rstrip().endswith(";")

    def test_mssql_compile_on_clause_uses_conflict_columns(self, sample_table: Table) -> None:
        from sqlalchemy.dialects import mssql

        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        stmt, _ = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="mssql",
        )
        compiled = str(stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        upper = compiled.upper()
        assert "TGT.[KEY] = SRC.[KEY]" in upper
        assert "TGT.[NAMESPACE] = SRC.[NAMESPACE]" in upper


class TestIdentifierValidation:
    """Test identifier validation security feature."""

    def test_valid_identifiers(self) -> None:
        """Test that valid identifiers pass validation."""
        assert validate_identifier("user_id") == "user_id"
        assert validate_identifier("users_table", "table") == "users_table"
        assert validate_identifier("created_at", "column") == "created_at"
        assert validate_identifier("_private_field") == "_private_field"
        assert validate_identifier("table123") == "table123"

    def test_empty_identifier(self) -> None:
        """Test that empty identifiers are rejected."""
        with pytest.raises(ValueError, match="Empty identifier name"):
            validate_identifier("")

    def test_invalid_characters(self) -> None:
        """Test that identifiers with invalid characters are rejected."""
        invalid_names = [
            "user-id",  # hyphen
            "user.id",  # dot
            "user id",  # space
            "123user",  # starts with number
            "user;",  # semicolon
            "user'",  # quote
            "user`",  # backtick
            "drop table users; --",  # SQL injection attempt
        ]

        for name in invalid_names:
            with pytest.raises(ValueError, match=r"Invalid.*Only alphanumeric"):
                validate_identifier(name)

    def test_sql_keywords_allowed(self) -> None:
        """Test that SQL keywords are allowed as identifiers."""
        # SQL keywords should be allowed since they can be quoted in SQL
        keywords = ["select", "SELECT", "insert", "UPDATE", "delete", "DROP", "create", "ALTER", "truncate"]

        for keyword in keywords:
            # Should not raise an error
            assert validate_identifier(keyword) == keyword
            assert validate_identifier(keyword.lower()) == keyword.lower()
            assert validate_identifier(keyword.upper()) == keyword.upper()

    def test_identifier_type_in_error(self) -> None:
        """Test that identifier type appears in error messages."""
        with pytest.raises(ValueError, match="Empty column name"):
            validate_identifier("", "column")

        with pytest.raises(ValueError, match="Invalid table name"):
            validate_identifier("123invalid", "table")

    def test_upsert_with_validation(self, sample_table: Table) -> None:
        """Test that create_upsert validates identifiers when requested."""
        values = {"key": "test_key", "namespace": "test_ns", "value": "test_value"}

        # Should work with validation enabled for valid identifiers
        upsert_stmt = OnConflictUpsert.create_upsert(
            table=sample_table,
            values=values,
            conflict_columns=["key", "namespace"],
            update_columns=["value"],
            dialect_name="postgresql",
            validate_identifiers=True,
        )
        assert upsert_stmt is not None

    def test_merge_with_validation(self, sample_table: Table) -> None:
        """Test that create_merge_upsert validates identifiers when requested."""
        values = {"key": "test_key", "namespace": "test_ns", "value": "test_value"}

        # Should work with validation enabled for valid identifiers
        merge_stmt, _ = OnConflictUpsert.create_merge_upsert(
            table=sample_table,
            values=values,
            conflict_columns=["key", "namespace"],
            update_columns=["value"],
            dialect_name="oracle",
            validate_identifiers=True,
        )
        assert merge_stmt is not None


class TestStoreIntegration:
    """Test that the store can use the new operations."""

    def test_store_imports_operations(self) -> None:
        """Test that store successfully imports new operations."""
        from advanced_alchemy.extensions.litestar.store import SQLAlchemyStore
        from advanced_alchemy.operations import MergeStatement, OnConflictUpsert

        # This test passes if no import errors occur
        assert OnConflictUpsert is not None
        assert MergeStatement is not None
        assert SQLAlchemyStore is not None


class TestCreateUpsertMany:
    """Tests for the bulk-aware OnConflictUpsert.create_upsert_many facade (Ch.1)."""

    def test_empty_values_list_raises(self, sample_table: Table) -> None:
        with pytest.raises(ValueError, match="values_list must not be empty"):
            OnConflictUpsert.create_upsert_many(
                table=sample_table,
                values_list=[],
                conflict_columns=["key", "namespace"],
                dialect_name="postgresql",
            )

    def test_heterogeneous_keys_raises(self, sample_table: Table) -> None:
        values_list = [
            {"key": "a", "namespace": "ns", "value": "v1"},
            {"key": "b", "namespace": "ns"},
        ]
        with pytest.raises(ValueError, match="same keys"):
            OnConflictUpsert.create_upsert_many(
                table=sample_table,
                values_list=values_list,
                conflict_columns=["key", "namespace"],
                dialect_name="postgresql",
            )

    def test_postgresql_compiles_to_single_insert_with_multiple_values(self, sample_table: Table) -> None:
        from sqlalchemy.dialects import postgresql

        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
            {"key": "k3", "namespace": "ns", "value": "v3"},
        ]
        stmt, supports_returning = OnConflictUpsert.create_upsert_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="postgresql",
        )
        compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        assert supports_returning is True
        assert "INSERT INTO" in compiled.upper()
        assert "ON CONFLICT" in compiled.upper()
        assert compiled.upper().count("VALUES") == 1
        assert compiled.count("(") >= 3

    def test_cockroachdb_returns_supports_returning_true(self, sample_table: Table) -> None:
        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        _, supports_returning = OnConflictUpsert.create_upsert_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="cockroachdb",
        )
        assert supports_returning is True

    def test_sqlite_compiles_and_returns_supports_returning_true(self, sample_table: Table) -> None:
        from sqlalchemy.dialects import sqlite

        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
        ]
        stmt, supports_returning = OnConflictUpsert.create_upsert_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="sqlite",
        )
        compiled = str(stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        assert supports_returning is True
        assert "ON CONFLICT" in compiled.upper()

    def test_duckdb_compiles(self, sample_table: Table) -> None:
        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        stmt, supports_returning = OnConflictUpsert.create_upsert_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="duckdb",
        )
        assert stmt is not None
        assert supports_returning is True

    def test_mysql_returns_supports_returning_false(self, sample_table: Table) -> None:
        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
        ]
        stmt, supports_returning = OnConflictUpsert.create_upsert_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="mysql",
        )
        assert supports_returning is False
        assert hasattr(stmt, "on_duplicate_key_update")

    def test_mariadb_returns_supports_returning_false(self, sample_table: Table) -> None:
        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        _, supports_returning = OnConflictUpsert.create_upsert_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="mariadb",
        )
        assert supports_returning is False

    def test_unsupported_dialect_raises(self, sample_table: Table) -> None:
        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        with pytest.raises(NotImplementedError, match="oracle"):
            OnConflictUpsert.create_upsert_many(
                table=sample_table,
                values_list=values_list,
                conflict_columns=["key", "namespace"],
                dialect_name="oracle",
            )

    def test_single_row_equivalence_to_create_upsert(self, sample_table: Table) -> None:
        from sqlalchemy.dialects import postgresql

        row = {"key": "k1", "namespace": "ns", "value": "v1"}
        single = OnConflictUpsert.create_upsert(
            table=sample_table,
            values=row,
            conflict_columns=["key", "namespace"],
            dialect_name="postgresql",
        )
        bulk_stmt, _ = OnConflictUpsert.create_upsert_many(
            table=sample_table,
            values_list=[row],
            conflict_columns=["key", "namespace"],
            dialect_name="postgresql",
        )
        single_sql = str(single.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        bulk_sql = str(bulk_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
        assert single_sql.split(" RETURNING ", maxsplit=1)[0] == bulk_sql.split(" RETURNING ", maxsplit=1)[0]

    def test_validate_identifiers_rejects_bad_column_in_bulk(self, sample_table: Table) -> None:
        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        with pytest.raises(ValueError, match="Invalid"):
            OnConflictUpsert.create_upsert_many(
                table=sample_table,
                values_list=values_list,
                conflict_columns=["key; --"],
                dialect_name="postgresql",
                validate_identifiers=True,
            )


class TestCreateMergeMany:
    """Tests for the bulk-aware OnConflictUpsert.create_merge_many facade (Ch.1)."""

    def test_empty_values_list_raises(self, sample_table: Table) -> None:
        with pytest.raises(ValueError, match="values_list must not be empty"):
            OnConflictUpsert.create_merge_many(
                table=sample_table,
                values_list=[],
                conflict_columns=["key", "namespace"],
                dialect_name="oracle",
            )

    def test_heterogeneous_keys_raises(self, sample_table: Table) -> None:
        values_list = [
            {"key": "a", "namespace": "ns", "value": "v1"},
            {"key": "b", "namespace": "ns"},
        ]
        with pytest.raises(ValueError, match="same keys"):
            OnConflictUpsert.create_merge_many(
                table=sample_table,
                values_list=values_list,
                conflict_columns=["key", "namespace"],
                dialect_name="oracle",
            )

    def test_oracle_returns_single_merge_with_union_all_source(self, sample_table: Table) -> None:
        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
            {"key": "k3", "namespace": "ns", "value": "v3"},
        ]
        result, additional_params = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="oracle",
        )
        assert isinstance(result, MergeStatement)
        source_repr = str(result.source)
        assert "UNION ALL" in source_repr.upper()
        assert "FROM DUAL" in source_repr.upper()
        assert isinstance(additional_params, dict)

    def test_postgresql_returns_single_merge_with_union_all_source(self, sample_table: Table) -> None:
        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
        ]
        result, _ = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="postgresql",
        )
        assert isinstance(result, MergeStatement)
        source_repr = str(result.source)
        assert "UNION ALL" in source_repr.upper()
        assert "FROM DUAL" not in source_repr.upper()

    def test_mssql_returns_merge_with_values_source_clause(self, sample_table: Table) -> None:
        from sqlalchemy.dialects import mssql

        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
        ]
        result, _ = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="mssql",
        )
        assert isinstance(result, MergeStatement)
        compiled_source = str(result.source.compile(dialect=mssql.dialect()))  # type: ignore[union-attr,no-untyped-call]
        assert "VALUES" in compiled_source.upper()
        assert "AS SRC" in compiled_source.upper()

    def test_other_dialect_returns_list_of_per_row_merge_statements(self, sample_table: Table) -> None:
        values_list = [
            {"key": "k1", "namespace": "ns", "value": "v1"},
            {"key": "k2", "namespace": "ns", "value": "v2"},
            {"key": "k3", "namespace": "ns", "value": "v3"},
        ]
        result, _ = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=values_list,
            conflict_columns=["key", "namespace"],
            dialect_name="mysql",
        )
        assert isinstance(result, list)
        assert len(result) == 3
        for item in result:
            assert isinstance(item, MergeStatement)

    def test_validate_identifiers_propagates_to_bulk_merge(self, sample_table: Table) -> None:
        values_list = [{"key": "k1", "namespace": "ns", "value": "v1"}]
        with pytest.raises(ValueError, match="Invalid"):
            OnConflictUpsert.create_merge_many(
                table=sample_table,
                values_list=values_list,
                conflict_columns=["bad-col"],
                dialect_name="oracle",
                validate_identifiers=True,
            )

    def test_single_row_oracle_equivalence_keys(self, sample_table: Table) -> None:
        row = {"key": "k1", "namespace": "ns", "value": "v1"}
        single_stmt, single_params = OnConflictUpsert.create_merge_upsert(
            table=sample_table,
            values=row,
            conflict_columns=["key", "namespace"],
            dialect_name="oracle",
        )
        bulk_result, bulk_params = OnConflictUpsert.create_merge_many(
            table=sample_table,
            values_list=[row],
            conflict_columns=["key", "namespace"],
            dialect_name="oracle",
        )
        assert isinstance(bulk_result, MergeStatement)
        assert set(bulk_result.when_not_matched_insert.keys()) == set(single_stmt.when_not_matched_insert.keys())
        assert set(bulk_result.when_matched_update.keys()) == set(single_stmt.when_matched_update.keys())
        assert isinstance(bulk_params, dict)
        assert isinstance(single_params, dict)


@pytest.fixture
def composite_pk_table() -> Table:
    """Table with composite PK + UniqueConstraint + unique Index for resolver tests."""
    metadata = MetaData()
    return Table(
        "users_v2",
        metadata,
        Column("tenant_id", Integer, primary_key=True),
        Column("user_id", Integer, primary_key=True),
        Column("email", String(255), nullable=False),
        Column("external_ref", String(64), nullable=False),
        Column("display_name", String(120)),
        UniqueConstraint("email", name="uq_users_email"),
        Index("ux_users_external_ref", "external_ref", unique=True),
        Index("ix_users_display_name", "display_name", unique=False),
    )


class TestResolveUpsertStrategy:
    """Tests for the dispatch resolver introduced in Ch.2."""

    def test_pk_exact_match_on_conflict_dialect(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(sample_table, ("id",), "postgresql")
        assert strategy.kind == "on_conflict"
        assert strategy.supports_returning is True
        assert strategy.conflict_columns == ("id",)
        assert strategy.dialect_name == "postgresql"

    def test_pk_superset_match_uses_pk_cols(self, composite_pk_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(composite_pk_table, ("tenant_id", "user_id", "email"), "postgresql")
        assert strategy.kind == "on_conflict"
        assert set(strategy.conflict_columns) == {"tenant_id", "user_id"}

    def test_composite_pk_exact_match(self, composite_pk_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(composite_pk_table, ("tenant_id", "user_id"), "postgresql")
        assert strategy.kind == "on_conflict"
        assert set(strategy.conflict_columns) == {"tenant_id", "user_id"}

    def test_unique_constraint_match(self, composite_pk_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(composite_pk_table, ("email",), "postgresql")
        assert strategy.kind == "on_conflict"
        assert strategy.conflict_columns == ("email",)

    def test_unique_index_match(self, composite_pk_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(composite_pk_table, ("external_ref",), "postgresql")
        assert strategy.kind == "on_conflict"
        assert strategy.conflict_columns == ("external_ref",)

    def test_non_unique_field_falls_back(self, composite_pk_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(composite_pk_table, ("display_name",), "postgresql")
        assert strategy.kind == "fallback"
        assert strategy.supports_returning is False

    def test_non_existent_column_raises_value_error(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        with pytest.raises(ValueError, match="not present in table"):
            resolve_upsert_strategy(sample_table, ("missing_col",), "postgresql")

    def test_empty_match_fields_raises(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        with pytest.raises(ValueError, match="must not be empty"):
            resolve_upsert_strategy(sample_table, (), "postgresql")

    def test_match_fields_order_independent_cache(self, composite_pk_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        first = resolve_upsert_strategy(composite_pk_table, ("tenant_id", "user_id"), "postgresql")
        second = resolve_upsert_strategy(composite_pk_table, ("user_id", "tenant_id"), "postgresql")
        assert first == second

    def test_cache_returns_same_instance(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        first = resolve_upsert_strategy(sample_table, ("id",), "postgresql")
        second = resolve_upsert_strategy(sample_table, ("id",), "postgresql")
        assert first is second

    @pytest.mark.parametrize(
        ("dialect", "expected_kind", "expected_returning"),
        [
            ("postgresql", "on_conflict", True),
            ("cockroachdb", "on_conflict", True),
            ("sqlite", "on_conflict", True),
            ("duckdb", "on_conflict", True),
            ("mysql", "on_conflict", False),
            ("mariadb", "on_conflict", False),
            ("oracle", "merge", True),
            ("mssql", "merge", True),
            ("spanner", "insert_or_update", False),
        ],
    )
    def test_dialect_to_kind_mapping(
        self,
        sample_table: Table,
        dialect: str,
        expected_kind: str,
        expected_returning: bool,
    ) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(sample_table, ("id",), dialect)
        assert strategy.kind == expected_kind
        assert strategy.supports_returning is expected_returning
        assert strategy.dialect_name == dialect

    def test_unknown_dialect_falls_back(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import resolve_upsert_strategy

        strategy = resolve_upsert_strategy(sample_table, ("id",), "snowflake")
        assert strategy.kind == "fallback"
        assert strategy.supports_returning is False

    def test_upsert_strategy_is_named_tuple_like(self, sample_table: Table) -> None:
        from advanced_alchemy.operations import UpsertStrategy, resolve_upsert_strategy

        strategy = resolve_upsert_strategy(sample_table, ("id",), "postgresql")
        assert isinstance(strategy, UpsertStrategy)
        assert hasattr(strategy, "kind")
        assert hasattr(strategy, "supports_returning")
        assert hasattr(strategy, "conflict_columns")
        assert hasattr(strategy, "dialect_name")

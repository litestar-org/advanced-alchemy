"""Tests for advanced_alchemy.operations module."""

from typing import Any

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table

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

        # Unsupported dialects
        assert OnConflictUpsert.supports_native_upsert("oracle") is False
        assert OnConflictUpsert.supports_native_upsert("mssql") is False
        assert OnConflictUpsert.supports_native_upsert("unknown") is False

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

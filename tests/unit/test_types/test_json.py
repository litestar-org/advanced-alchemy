"""Unit tests for advanced_alchemy.types.json.ORA_JSONB dialect dispatch."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import JSON, CheckConstraint, Column, MetaData, Table, create_mock_engine, literal_column, select
from sqlalchemy.dialects import oracle
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql import operators

from advanced_alchemy.types.json import ORA_JSONB, JsonB


@pytest.mark.parametrize(
    ("supports_native_type", "server_version", "use_blob", "expects_native"),
    [
        (False, (23,), False, False),
        (True, (19,), False, False),
        (True, (21,), False, True),
        (True, (23,), False, True),
        (True, (23,), True, False),
        (True, None, False, False),
    ],
)
def test_oracle_json_storage(
    monkeypatch: pytest.MonkeyPatch,
    supports_native_type: bool,
    server_version: tuple[int, ...] | None,
    use_blob: bool,
    expects_native: bool,
) -> None:
    if supports_native_type:
        monkeypatch.setattr(oracle, "JSON", JSON, raising=False)
    else:
        monkeypatch.delattr(oracle, "JSON", raising=False)

    dialect = create_mock_engine("oracle+oracledb://", lambda *_args, **_kwargs: None).dialect
    dialect.server_version_info = server_version
    column_type = ORA_JSONB(use_blob=True) if use_blob else JsonB
    table = Table("documents", MetaData(), Column("payload", column_type))
    ddl = str(CreateTable(table).compile(dialect=dialect)).upper()
    query = str(select(table.c.payload).compile(dialect=dialect)).upper()

    assert ("PAYLOAD JSON" if expects_native else "PAYLOAD BLOB") in ddl
    assert ("PAYLOAD IS JSON (STRICT)" in ddl) is not expects_native
    assert ("JSON_SERIALIZE(DOCUMENTS.PAYLOAD RETURNING BLOB)" in query) is expects_native


def test_set_table_adds_is_json_check_constraint() -> None:
    """Attaching the type to a table must not depend on SQLAlchemy's private util helpers.

    ``ORA_JSONB._set_table`` runs when a column using the type is added to a table. SQLAlchemy 2.1
    removed ``util.portable_instancemethod``, which an earlier version of it relied on.
    """
    table = Table("json_doc", MetaData(), Column("data", ORA_JSONB()))
    constraints = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert [c.name for c in constraints] == ["data_is_json"]


def test_set_table_via_variant_adds_is_json_check_constraint() -> None:
    """The ``JsonB`` variant type also attaches its Oracle check constraint to the table."""
    table = Table("json_doc", MetaData(), Column("data", JsonB))
    names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert names == ["data_is_json"]


def test_set_table_check_constraint_only_created_for_oracle() -> None:
    """The check constraint's create rule is applied per dialect when DDL is compiled."""
    table = Table("json_doc", MetaData(), Column("data", ORA_JSONB()))
    constraint = next(c for c in table.constraints if isinstance(c, CheckConstraint))
    oracle = MagicMock()
    oracle.dialect.name = "oracle"
    oracle.dialect.server_version_info = (19, 0)
    postgres = MagicMock()
    postgres.dialect.name = "postgresql"
    rule = constraint._create_rule
    assert rule is not None
    assert rule(oracle) is True
    assert rule(postgres) is False


def test_ora_jsonb_coerce_compared_value_initializes_impl() -> None:
    """Calling super().__init__ ensures self.impl is an instance rather than the class."""
    ora_type = ORA_JSONB(oracle_strict=False, name="payload_is_json")
    assert ora_type.oracle_strict is False
    assert ora_type.name == "payload_is_json"
    coerced = ora_type.coerce_compared_value(operators.eq, literal_column("'a'"))
    assert coerced is not None


@pytest.mark.parametrize("column_type", [ORA_JSONB(), JsonB])
@pytest.mark.parametrize("value", [{"a": [1, 1.25]}, "123", '{"a": 1}', None])
def test_oracle_json_runs_each_codec_once(monkeypatch: pytest.MonkeyPatch, column_type: Any, value: Any) -> None:
    dialect = create_mock_engine("oracle+oracledb://", lambda *_args, **_kwargs: None).dialect
    dialect.server_version_info = (23,)
    serializer = MagicMock(side_effect=lambda value: json.dumps(value, ensure_ascii=False))
    deserializer = MagicMock(side_effect=json.loads)
    monkeypatch.setattr(dialect, "_json_serializer", serializer, raising=False)
    monkeypatch.setattr(dialect, "_json_deserializer", deserializer, raising=False)
    impl = column_type.dialect_impl(dialect)
    bind = impl.bind_processor(dialect)
    result = impl.result_processor(dialect, None)
    assert bind is not None
    assert result is not None

    encoded = bind(value)
    assert encoded == (None if value is None else json.dumps(value).encode())
    assert result(encoded) == value
    if value is None:
        serializer.assert_not_called()
        deserializer.assert_not_called()
    else:
        serializer.assert_called_once_with(value)
        deserializer.assert_called_once_with(encoded.decode())


def test_ora_jsonb_blob_option_participates_in_cache_key() -> None:
    assert ORA_JSONB(use_blob=True)._static_cache_key != ORA_JSONB()._static_cache_key


def test_ora_jsonb_repr_preserves_migration_options() -> None:
    assert repr(ORA_JSONB(use_blob=True, oracle_strict=False)) == "ORA_JSONB(use_blob=True, oracle_strict=False)"

"""Unit tests for the dialect-aware ``Vector`` type."""

import array
import importlib
import subprocess
import sys
import textwrap
from typing import Optional

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, insert, select
from sqlalchemy.dialects import oracle as oracle_dialect_mod
from sqlalchemy.dialects import postgresql as postgresql_dialect_mod
from sqlalchemy.dialects import sqlite as sqlite_dialect_mod
from sqlalchemy.types import JSON

from advanced_alchemy.types import Vector


def test_vector_is_publicly_exported() -> None:
    """``Vector`` is part of the public ``advanced_alchemy.types`` API."""
    import advanced_alchemy.types as aa_types

    assert "Vector" in aa_types.__all__
    assert aa_types.Vector is Vector


def test_vector_import_does_not_load_optional_backends() -> None:
    """Importing ``advanced_alchemy.types`` must not import ``pgvector`` or ``oracledb``."""
    script = textwrap.dedent(
        """
        import sys
        import advanced_alchemy.types  # noqa: F401

        assert "pgvector" not in sys.modules, "pgvector loaded eagerly: " + repr(sorted(sys.modules))
        assert "oracledb" not in sys.modules, "oracledb loaded eagerly: " + repr(sorted(sys.modules))
        """,
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_vector_constructor_records_dim_and_storage_format() -> None:
    vec = Vector(1536)
    assert vec.dim == 1536
    assert vec.storage_format == "FLOAT32"

    vec64 = Vector(8, storage_format="FLOAT64")
    assert vec64.dim == 8
    assert vec64.storage_format == "FLOAT64"


def test_vector_default_impl_is_json() -> None:
    """The cross-dialect fallback ``impl`` is JSON so unknown dialects round-trip lists."""
    assert Vector.impl is JSON
    assert Vector.cache_ok is True


def test_vector_sqlite_falls_back_to_json() -> None:
    """On dialects without a native vector type, ``Vector`` resolves to JSON."""
    dialect = sqlite_dialect_mod.dialect()
    resolved = Vector(3).dialect_impl(dialect)
    assert isinstance(resolved.impl, JSON)


def test_vector_postgresql_uses_pgvector_when_available() -> None:
    """On PostgreSQL/CockroachDB, ``Vector`` selects the ``pgvector`` impl."""
    pytest.importorskip("pgvector.sqlalchemy")
    from pgvector.sqlalchemy import Vector as PgVector

    dialect = postgresql_dialect_mod.dialect()
    resolved = Vector(1536).dialect_impl(dialect)
    assert isinstance(resolved.impl, PgVector)
    assert resolved.impl.dim == 1536


def test_vector_postgresql_without_pgvector_falls_back_to_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """If ``pgvector`` cannot be imported, PostgreSQL emits the JSON fallback."""
    real_import = importlib.import_module

    def fake_import(name: str, *args: object, **kwargs: object):
        if name.startswith("pgvector"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setitem(sys.modules, "pgvector", None)
    monkeypatch.setitem(sys.modules, "pgvector.sqlalchemy", None)

    dialect = postgresql_dialect_mod.dialect()
    resolved = Vector(4).dialect_impl(dialect)
    assert isinstance(resolved.impl, JSON)


def test_vector_oracle_uses_native_vector_type() -> None:
    """On Oracle, ``Vector`` selects ``oracle.VECTOR`` with the requested storage format."""
    from sqlalchemy.dialects.oracle import VECTOR, VectorStorageFormat

    dialect = oracle_dialect_mod.dialect()
    resolved = Vector(1024, storage_format="FLOAT64").dialect_impl(dialect)
    assert isinstance(resolved.impl, VECTOR)
    assert resolved.impl.dim == 1024
    assert resolved.impl.storage_format is VectorStorageFormat.FLOAT64


def test_vector_oracle_ddl_compiles_with_dim_and_format() -> None:
    """DDL for ``Vector`` on Oracle includes the dimension and storage format."""
    dialect = oracle_dialect_mod.dialect()
    column = Column("embedding", Vector(8, storage_format="FLOAT32"))
    ddl = str(column.type.compile(dialect=dialect))
    assert "VECTOR" in ddl
    assert "8" in ddl
    assert "FLOAT32" in ddl


def test_vector_process_result_value_normalizes_array_array() -> None:
    """Oracle's ``array.array`` result is normalized to ``list[float]``."""
    vec = Vector(3)
    raw = array.array("f", [1.0, 2.0, 3.0])
    assert vec.process_result_value(raw, oracle_dialect_mod.dialect()) == [1.0, 2.0, 3.0]


def test_vector_process_result_value_normalizes_tolist_result() -> None:
    """Anything that exposes ``.tolist()`` (numpy arrays, pgvector results) is normalized."""

    class FakeNumpy:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def tolist(self) -> list[float]:
            return list(self._values)

    vec = Vector(2)
    assert vec.process_result_value(FakeNumpy([0.5, 0.25]), postgresql_dialect_mod.dialect()) == [0.5, 0.25]


def test_vector_process_result_value_preserves_none() -> None:
    """``None`` survives the result normalization step unchanged."""
    assert Vector(4).process_result_value(None, sqlite_dialect_mod.dialect()) is None


def test_vector_process_result_value_returns_list_for_plain_iterable() -> None:
    """JSON fallback returns a plain ``list`` (or anything iterable) and stays a ``list``."""
    vec = Vector(3)
    assert vec.process_result_value([1.0, 2.0, 3.0], sqlite_dialect_mod.dialect()) == [1.0, 2.0, 3.0]


def test_vector_sqlite_round_trip_via_json_fallback() -> None:
    """End-to-end: insert a vector on SQLite and round-trip it back as ``list[float]``."""
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "vectors",
        metadata,
        Column("id", primary_key=True, type_=__import__("sqlalchemy").Integer),
        Column("embedding", Vector(3)),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(table).values(id=1, embedding=[0.1, 0.2, 0.3]))
        row: Optional[tuple] = conn.execute(select(table.c.embedding).where(table.c.id == 1)).first()
    assert row is not None
    assert row[0] == [0.1, 0.2, 0.3]

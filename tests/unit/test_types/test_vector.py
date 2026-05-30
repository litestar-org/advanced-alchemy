"""Unit tests for the dialect-aware ``Vector`` type."""

import array
import importlib
import subprocess
import sys
import textwrap
from typing import Any, Optional, cast

import pytest
from sqlalchemy import Column, Integer, Table, create_engine, insert, select
from sqlalchemy.dialects import oracle as oracle_dialect_mod
from sqlalchemy.dialects import postgresql as postgresql_dialect_mod
from sqlalchemy.dialects import sqlite as sqlite_dialect_mod
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
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
    dialect = sqlite_dialect_mod.dialect()  # type: ignore[no-untyped-call,unused-ignore]
    resolved = Vector(3).dialect_impl(dialect)
    assert isinstance(resolved.impl, JSON)


def test_vector_postgresql_uses_pgvector_when_available() -> None:
    """On PostgreSQL/CockroachDB, ``Vector`` selects the ``pgvector`` impl."""
    pytest.importorskip("pgvector.sqlalchemy")
    from pgvector.sqlalchemy import Vector as PgVector  # pyright: ignore[reportMissingTypeStubs]

    dialect = postgresql_dialect_mod.dialect()  # type: ignore[no-untyped-call,unused-ignore]
    resolved = Vector(1536).dialect_impl(dialect)
    assert isinstance(resolved.impl, PgVector)
    assert resolved.impl.dim == 1536


def test_vector_postgresql_without_pgvector_falls_back_to_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """If ``pgvector`` cannot be imported, PostgreSQL emits the JSON fallback."""
    real_import = importlib.import_module

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("pgvector"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setitem(sys.modules, "pgvector", None)
    monkeypatch.setitem(sys.modules, "pgvector.sqlalchemy", None)

    dialect = postgresql_dialect_mod.dialect()  # type: ignore[no-untyped-call,unused-ignore]
    resolved = Vector(4).dialect_impl(dialect)
    assert isinstance(resolved.impl, JSON)


def test_vector_oracle_uses_native_vector_type() -> None:
    """On Oracle, ``Vector`` selects ``oracle.VECTOR`` with the requested storage format."""
    from sqlalchemy.dialects.oracle import VECTOR, VectorStorageFormat

    dialect = oracle_dialect_mod.dialect()  # type: ignore[no-untyped-call,unused-ignore]
    resolved = Vector(1024, storage_format="FLOAT64").dialect_impl(dialect)
    assert isinstance(resolved.impl, VECTOR)
    assert resolved.impl.dim == 1024
    assert resolved.impl.storage_format is VectorStorageFormat.FLOAT64


def test_vector_oracle_ddl_compiles_with_dim_and_format() -> None:
    """DDL for ``Vector`` on Oracle includes the dimension and storage format."""

    class _Base(DeclarativeBase):
        pass

    class _OracleVectorModel(_Base):
        __tablename__ = "oracle_vector_model"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        embedding: Mapped[list[float]] = mapped_column(Vector(8, storage_format="FLOAT32"))

    dialect = oracle_dialect_mod.dialect()  # type: ignore[no-untyped-call,unused-ignore]
    ddl = str(_OracleVectorModel.__table__.c.embedding.type.compile(dialect=dialect))  # type: ignore[no-untyped-call,unused-ignore]
    assert "VECTOR" in ddl
    assert "8" in ddl
    assert "FLOAT32" in ddl


def test_vector_process_result_value_normalizes_array_array() -> None:
    """Oracle's ``array.array`` result is normalized to ``list[float]``."""
    vec = Vector(3)
    raw = array.array("f", [1.0, 2.0, 3.0])
    assert vec.process_result_value(raw, oracle_dialect_mod.dialect()) == [1.0, 2.0, 3.0]  # type: ignore[no-untyped-call,unused-ignore]


def test_vector_process_result_value_normalizes_tolist_result() -> None:
    """Anything that exposes ``.tolist()`` (numpy arrays, pgvector results) is normalized."""

    class FakeNumpy:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def tolist(self) -> list[float]:
            return list(self._values)

    vec = Vector(2)
    assert vec.process_result_value(FakeNumpy([0.5, 0.25]), postgresql_dialect_mod.dialect()) == [0.5, 0.25]  # type: ignore[no-untyped-call,unused-ignore]


def test_vector_process_result_value_preserves_none() -> None:
    """``None`` survives the result normalization step unchanged."""
    assert Vector(4).process_result_value(None, sqlite_dialect_mod.dialect()) is None  # type: ignore[no-untyped-call,unused-ignore]


def test_vector_process_result_value_returns_list_for_plain_iterable() -> None:
    """JSON fallback returns a plain ``list`` (or anything iterable) and stays a ``list``."""
    vec = Vector(3)
    assert vec.process_result_value([1.0, 2.0, 3.0], sqlite_dialect_mod.dialect()) == [1.0, 2.0, 3.0]  # type: ignore[no-untyped-call,unused-ignore]


def test_vector_distance_methods_exist_on_column() -> None:
    """``Vector`` columns expose pgvector-compatible distance comparator methods."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    assert hasattr(column, "cosine_distance")
    assert hasattr(column, "l2_distance")
    assert hasattr(column, "max_inner_product")


def test_vector_cosine_distance_postgresql_emits_operator() -> None:
    """Cosine distance compiles to the pgvector ``<=>`` operator on PostgreSQL."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    statement = column.cosine_distance([1.0, 2.0, 3.0])
    sql = str(statement.compile(dialect=postgresql_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]
    assert "<=>" in sql


def test_vector_l2_distance_postgresql_emits_operator() -> None:
    """L2 distance compiles to the pgvector ``<->`` operator on PostgreSQL."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    statement = column.l2_distance([1.0, 2.0, 3.0])
    sql = str(statement.compile(dialect=postgresql_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]
    assert "<->" in sql


def test_vector_max_inner_product_postgresql_emits_operator() -> None:
    """Negative inner product compiles to the pgvector ``<#>`` operator on PostgreSQL."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    statement = column.max_inner_product([1.0, 2.0, 3.0])
    sql = str(statement.compile(dialect=postgresql_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]
    assert "<#>" in sql


def test_vector_cosine_distance_oracle_emits_vector_distance() -> None:
    """Cosine distance compiles to ``VECTOR_DISTANCE(..., COSINE)`` on Oracle 23ai."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    statement = column.cosine_distance([1.0, 2.0, 3.0])
    sql = str(statement.compile(dialect=oracle_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]
    assert "VECTOR_DISTANCE" in sql
    assert "COSINE" in sql


def test_vector_l2_distance_oracle_uses_euclidean_metric() -> None:
    """L2 distance maps to the Oracle ``EUCLIDEAN`` metric."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    statement = column.l2_distance([1.0, 2.0, 3.0])
    sql = str(statement.compile(dialect=oracle_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]
    assert "VECTOR_DISTANCE" in sql
    assert "EUCLIDEAN" in sql


def test_vector_max_inner_product_oracle_uses_dot_metric() -> None:
    """Negative inner product maps to the Oracle ``DOT`` metric."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    statement = column.max_inner_product([1.0, 2.0, 3.0])
    sql = str(statement.compile(dialect=oracle_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]
    assert "VECTOR_DISTANCE" in sql
    assert "DOT" in sql


def test_vector_distance_unsupported_dialect_raises() -> None:
    """Distance operations require a native vector backend; JSON fallback raises clearly."""
    column: Column[list[float]] = Column("embedding", Vector(3))
    statement = column.cosine_distance([1.0, 2.0, 3.0])
    with pytest.raises(NotImplementedError):
        str(statement.compile(dialect=sqlite_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]


def test_vector_distance_usable_in_order_by_on_postgresql() -> None:
    """Distance expressions work as ``ORDER BY`` keys for nearest-neighbour search."""

    class _Base(DeclarativeBase):
        pass

    class _PgVectorModel(_Base):
        __tablename__ = "pg_vector_order_by_model"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        embedding: Mapped[list[float]] = mapped_column(Vector(3))

    statement = select(_PgVectorModel).order_by(_PgVectorModel.embedding.cosine_distance([1.0, 2.0, 3.0]))
    sql = str(statement.compile(dialect=postgresql_dialect_mod.dialect()))  # type: ignore[no-untyped-call,unused-ignore]
    assert "ORDER BY" in sql
    assert "<=>" in sql


def test_vector_sqlite_round_trip_via_json_fallback() -> None:
    """End-to-end: insert a vector on SQLite and round-trip it back as ``list[float]``."""

    class _Base(DeclarativeBase):
        pass

    class _SqliteVectorModel(_Base):
        __tablename__ = "vector_round_trip_model"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        embedding: Mapped[list[float]] = mapped_column(Vector(3))

    engine = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    table = cast(Table, _SqliteVectorModel.__table__)
    with engine.begin() as conn:
        conn.execute(insert(table).values(id=1, embedding=[0.1, 0.2, 0.3]))
        row: Optional[Any] = conn.execute(select(table.c.embedding).where(table.c.id == 1)).first()
    assert row is not None
    assert row[0] == [0.1, 0.2, 0.3]

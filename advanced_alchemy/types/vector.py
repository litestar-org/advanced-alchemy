"""Dialect-aware ``Vector`` column type.

Provides a single user-facing :class:`Vector` class that resolves to the most
appropriate backend representation per dialect:

- Oracle 23ai → ``sqlalchemy.dialects.oracle.VECTOR(dim, storage_format)``
- PostgreSQL / CockroachDB → ``pgvector.sqlalchemy.Vector(dim)`` when
  ``pgvector`` is importable, otherwise the cross-dialect JSON fallback.
- All other dialects → ``sqlalchemy.types.JSON`` round-trip as a JSON array.

The pattern mirrors :class:`advanced_alchemy.types.guid.GUID`: one
``TypeDecorator`` with a single constructor, and ``load_dialect_impl`` selects
the backend impl at DDL/compile time. Backend libraries are imported lazily
inside ``load_dialect_impl`` so ``from advanced_alchemy.types import Vector``
never requires ``pgvector`` or ``oracledb`` to be installed.
"""

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Float, literal
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.sql.compiler import SQLCompiler

__all__ = ("Vector",)

_PGVECTOR_OPERATORS = {"cosine": "<=>", "l2": "<->", "inner_product": "<#>"}
_ORACLE_METRICS = {"cosine": "COSINE", "l2": "EUCLIDEAN", "inner_product": "DOT"}


class Vector(TypeDecorator[list[float]]):
    """Dialect-aware fixed-dimension vector column.

    Args:
        dim: The vector dimension. Required by every supported backend.
        storage_format: Oracle 23ai storage format name (matched against
            :class:`sqlalchemy.dialects.oracle.VectorStorageFormat`).
            Defaults to ``"FLOAT32"``. Ignored on non-Oracle backends.
    """

    impl = JSON
    cache_ok = True

    @property
    def python_type(self) -> type[list[float]]:
        return list

    def __init__(self, dim: int, *, storage_format: str = "FLOAT32") -> None:
        super().__init__()
        self.dim = dim
        self.storage_format = storage_format

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "oracle":
            from sqlalchemy.dialects.oracle import VECTOR, VectorStorageFormat

            fmt = VectorStorageFormat[self.storage_format]
            return dialect.type_descriptor(VECTOR(dim=self.dim, storage_format=fmt))  # type: ignore[no-untyped-call]
        if dialect.name in {"postgresql", "cockroachdb"}:
            try:
                from pgvector.sqlalchemy import Vector as PgVector  # pyright: ignore[reportMissingTypeStubs]
            except ImportError:
                return dialect.type_descriptor(JSON())
            return dialect.type_descriptor(PgVector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value: Any, dialect: Dialect) -> Optional[list[float]]:
        if value is None:
            return None
        if hasattr(value, "tolist"):
            return list(value.tolist())
        return list(value)

    class Comparator(TypeDecorator.Comparator[list[float]]):
        """Dialect-aware vector distance operators for similarity search.

        Method names and semantics mirror ``pgvector``'s SQLAlchemy comparator so
        existing pgvector-based queries can swap to :class:`Vector` unchanged.
        """

        def _distance(self, other: "Sequence[float]", metric: str) -> "_VectorDistance":
            operand = literal(list(other), type_=self.type)
            return _VectorDistance(self.expr, operand, metric)

        def cosine_distance(self, other: "Sequence[float]") -> "_VectorDistance":
            return self._distance(other, "cosine")

        def l2_distance(self, other: "Sequence[float]") -> "_VectorDistance":
            return self._distance(other, "l2")

        def max_inner_product(self, other: "Sequence[float]") -> "_VectorDistance":
            return self._distance(other, "inner_product")

    comparator_factory = Comparator  # pyright: ignore[reportIncompatibleMethodOverride,reportAssignmentType]


class _VectorDistance(ColumnElement[float]):
    """Dialect-deferred vector distance expression.

    The SQL is chosen at compile time so the same expression compiles to native
    operators on each backend:

    - PostgreSQL / CockroachDB → ``<=>`` / ``<->`` / ``<#>`` (pgvector)
    - Oracle 23ai → ``VECTOR_DISTANCE(col, :vec, COSINE | EUCLIDEAN | DOT)``
    - other dialects → :exc:`NotImplementedError` (no native vector backend)
    """

    inherit_cache = False

    def __init__(self, left: "ColumnElement[Any]", right: "ColumnElement[Any]", metric: str) -> None:
        self.left = left
        self.right = right
        self.metric = metric
        self.type = Float()


@compiles(_VectorDistance)
def compile_vector_distance(element: _VectorDistance, compiler: "SQLCompiler", **kw: Any) -> str:
    msg = (
        "Vector distance operations require a native vector backend "
        "(PostgreSQL with pgvector, or Oracle 23ai). The current dialect stores "
        "vectors as JSON and has no distance operator."
    )
    raise NotImplementedError(msg)


@compiles(_VectorDistance, "postgresql")
@compiles(_VectorDistance, "cockroachdb")
def compile_vector_distance_pgvector(element: _VectorDistance, compiler: "SQLCompiler", **kw: Any) -> str:
    operator = _PGVECTOR_OPERATORS[element.metric]
    return f"({compiler.process(element.left, **kw)} {operator} {compiler.process(element.right, **kw)})"


@compiles(_VectorDistance, "oracle")
def compile_vector_distance_oracle(element: _VectorDistance, compiler: "SQLCompiler", **kw: Any) -> str:
    metric = _ORACLE_METRICS[element.metric]
    return f"VECTOR_DISTANCE({compiler.process(element.left, **kw)}, {compiler.process(element.right, **kw)}, {metric})"

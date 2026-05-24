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

from typing import Any, Optional

from sqlalchemy.engine import Dialect
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

__all__ = ("Vector",)


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

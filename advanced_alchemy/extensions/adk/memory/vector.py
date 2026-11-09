"""Optional pgvector-backed ADK memory mixin."""

from typing import Optional

from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column

from advanced_alchemy.extensions.adk.models import ADKMemoryModelMixin

try:
    from pgvector.sqlalchemy import Vector  # pyright: ignore[reportMissingTypeStubs]
except ImportError as e:
    from advanced_alchemy.exceptions import MissingDependencyError

    package = "pgvector"
    raise MissingDependencyError(package) from e


@declarative_mixin
class ADKVectorMemoryModelMixin(ADKMemoryModelMixin):
    """Mixin for Google ADK memory storage with an optional pgvector embedding."""

    __abstract__ = True

    @declared_attr
    def embedding(cls) -> Mapped[Optional[list[float]]]:
        return mapped_column(Vector(1536), nullable=True)


__all__ = ("ADKVectorMemoryModelMixin",)

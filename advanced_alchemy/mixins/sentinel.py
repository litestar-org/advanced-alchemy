from __future__ import annotations

from sqlalchemy.orm import Mapped, declared_attr, orm_insert_sentinel


class SentinelMixin:
    """Mixin to add a sentinel column for SQLAlchemy models."""

    @declared_attr
    def _sentinel(cls) -> Mapped[int]:
        return orm_insert_sentinel(name="sa_orm_sentinel")

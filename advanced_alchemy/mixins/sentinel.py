from typing import Any

from sqlalchemy import Integer, insert_sentinel
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def _create_sentinel_column(_cls: Any) -> Mapped[int]:
    return mapped_column(
        Integer,
        name="sa_orm_sentinel",
        insert_default=insert_sentinel().default,
        _omit_from_statements=True,
        insert_sentinel=True,
        use_existing_column=True,
        nullable=True,
        sort_order=3001,
    )


_create_sentinel_column.__annotations__.clear()


class SentinelMixin:
    """Mixin to add a sentinel column for SQLAlchemy models."""

    __abstract__ = True

    _sentinel = declared_attr(_create_sentinel_column)

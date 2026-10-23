"""Soft-delete model mixin."""

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.types.datetime import DateTimeUTC

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

__all__ = ("SoftDeleteMixin",)


class SoftDeleteMixin:
    """Mixin adding a nullable ``deleted_at`` timestamp and ``is_deleted`` hybrid property."""

    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTimeUTC(timezone=True),
        default=None,
        nullable=True,
        index=True,
        sort_order=3004,
    )
    """Date/time of soft deletion, or ``None`` when active."""

    @hybrid_property
    def is_deleted(self) -> bool:
        """Return ``True`` when the record has a non-null ``deleted_at`` timestamp."""
        return self.deleted_at is not None

    @is_deleted.inplace.expression
    @classmethod
    def _is_deleted_expression(cls) -> "ColumnElement[bool]":
        """Return a SQL expression evaluating whether ``deleted_at IS NOT NULL``."""
        return cls.deleted_at.is_not(None)

    def mark_deleted(self, deleted_at: Optional[datetime.datetime] = None) -> None:
        """Set ``deleted_at`` to ``deleted_at`` or the current UTC timestamp."""
        self.deleted_at = deleted_at if deleted_at is not None else datetime.datetime.now(datetime.timezone.utc)

    def restore(self) -> None:
        """Clear ``deleted_at`` back to ``None``."""
        self.deleted_at = None

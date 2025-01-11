from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import mapped_column
from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr
from sqlalchemy.types import DateTime


@declarative_mixin
class SoftDeleteMixin:
    """Mixin class that adds soft delete functionality to SQLAlchemy models.

    Adds two columns:
    - deleted_at: Timestamp when the record was deleted
    """

    @declared_attr
    def deleted_at(cls) -> Mapped[datetime | None]:
        """Timestamp when the record was soft deleted"""
        return mapped_column(
            DateTime(timezone=True),
            default=None,
            nullable=True,
            index=True,
        )

    def set_deleted_at(self, timestamp: datetime | None = None) -> None:
        """Mark the record as soft deleted.

        Args:
            timestamp: Optional timestamp to use for the deletion. If not provided,
                    the current UTC timestamp will be used.
        """
        self.deleted_at = timestamp or datetime.now(timezone.utc)

    def restore(self) -> None:
        self.deleted_at = None

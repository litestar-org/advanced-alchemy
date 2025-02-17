import datetime

from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column, validates

from advanced_alchemy.types import DateTimeUTC


@declarative_mixin
class AuditColumns:
    """Created/Updated At Fields Mixin."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    """Date/time of instance creation."""
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    """Date/time of instance last update."""

    @validates("created_at", "updated_at")
    def validate_tz_info(self, _: str, value: datetime.datetime) -> datetime.datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value

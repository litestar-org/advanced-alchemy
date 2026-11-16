import datetime as dt

from sqlalchemy.orm import Mapped, mapped_column, validates

from advanced_alchemy.types import DateTimeUTC


class AuditColumns:
    """Created/Updated At Fields Mixin."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        sort_order=3002,
    )
    """Date/time of instance creation."""
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
        sort_order=3003,
    )
    """Date/time of instance last update."""

    @validates("created_at", "updated_at")
    def validate_tz_info(self, _: str, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value

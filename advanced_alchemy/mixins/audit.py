import datetime

from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column, validates

from advanced_alchemy.types import DateTimeUTC


@declarative_mixin
class AuditColumns:
    """Created/Updated At Fields Mixin."""

    __abstract__ = True

    @declared_attr
    def created_at(cls) -> Mapped[datetime.datetime]:
        """Date/time of instance creation.

        Returns:
            Date/time of instance creation.
        """
        return mapped_column(
            DateTimeUTC(timezone=True),
            default=lambda: datetime.datetime.now(datetime.timezone.utc),
        )

    @declared_attr
    def updated_at(cls) -> Mapped[datetime.datetime]:
        """Date/time of instance last update.

        Returns:
            Date/time of instance last update.
        """
        return mapped_column(
            DateTimeUTC(timezone=True),
            default=lambda: datetime.datetime.now(datetime.timezone.utc),
            onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
        )

    @validates("created_at", "updated_at")
    def validate_tz_info(self, _: str, value: datetime.datetime) -> datetime.datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value

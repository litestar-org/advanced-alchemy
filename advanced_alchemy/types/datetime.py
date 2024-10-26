from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Type

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

__all__ = ("DateTimeUTC",)


class DateTimeUTC(TypeDecorator[datetime.datetime]):
    """Timezone Aware DateTime.

    Ensure UTC is stored in the database and that TZ aware dates are returned for all dialects.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @property
    def python_type(self) -> Type[datetime.datetime]:
        return datetime.datetime

    def process_bind_param(self, value: datetime.datetime | None, dialect: Dialect) -> datetime.datetime | None:
        if value is None:
            return value
        if not value.tzinfo:
            msg = "tzinfo is required"
            raise TypeError(msg)
        return value.astimezone(datetime.timezone.utc)

    def process_result_value(self, value: datetime.datetime | None, dialect: Dialect) -> datetime.datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value

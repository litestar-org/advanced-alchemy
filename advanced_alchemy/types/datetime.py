import datetime
from typing import Optional, cast

from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

__all__ = ("DateTimeUTC",)

_MAX_MYSQL_DATETIME_FSP = 6


class DateTimeUTC(TypeDecorator[datetime.datetime]):
    """Timezone Aware DateTime.

    Ensure UTC is stored in the database and that TZ aware dates are returned for all dialects.

    Args:
        fsp: Optional MySQL fractional seconds precision. Use ``DateTimeUTC(fsp=6)``
            when matching schemas that require MySQL ``DATETIME(6)`` columns.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def __init__(self, timezone: bool = True, fsp: Optional[int] = None) -> None:
        if fsp is not None and (not isinstance(fsp, int) or not 0 <= fsp <= _MAX_MYSQL_DATETIME_FSP):  # pyright: ignore[reportUnnecessaryIsInstance]
            msg = "fsp must be an integer between 0 and 6"
            raise ValueError(msg)
        self.timezone = timezone
        self.fsp = fsp
        super().__init__()

    @property
    def python_type(self) -> type[datetime.datetime]:
        return datetime.datetime

    def load_dialect_impl(self, dialect: Dialect) -> DateTime:
        if self.fsp is not None and dialect.name in {"mysql", "mariadb"}:
            return cast("DateTime", dialect.type_descriptor(mysql.DATETIME(fsp=self.fsp)))
        return cast("DateTime", dialect.type_descriptor(DateTime(timezone=self.timezone)))

    def process_bind_param(self, value: Optional[datetime.datetime], dialect: Dialect) -> Optional[datetime.datetime]:
        if value is None:
            return value
        if not value.tzinfo:
            msg = "tzinfo is required"
            raise TypeError(msg)
        return value.astimezone(datetime.timezone.utc)

    def process_result_value(self, value: Optional[datetime.datetime], dialect: Dialect) -> Optional[datetime.datetime]:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value

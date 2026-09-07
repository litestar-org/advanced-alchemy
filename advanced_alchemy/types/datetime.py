import datetime
from typing import Any, Optional

from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql, oracle
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

__all__ = ("DateTimeUTC",)


class DateTimeUTC(TypeDecorator[datetime.datetime]):
    """Timezone Aware DateTime.

    Ensure UTC is stored in the database and that TZ aware dates are returned for all dialects.

    Args:
        fsp: Optional fractional seconds precision. When omitted the DDL is unchanged, which on
            MySQL and Oracle means whole-second resolution. Pass a precision to compile a type
            that retains sub-second values, which matters for expiry and lease comparisons.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def __init__(self, timezone: bool = True, fsp: Optional[int] = None) -> None:
        super().__init__(timezone=timezone)
        self.timezone = timezone
        self.fsp = fsp

    @property
    def python_type(self) -> type[datetime.datetime]:
        return datetime.datetime

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if self.fsp is None:
            return dialect.type_descriptor(DateTime(timezone=True))
        if dialect.name in {"mysql", "mariadb"}:
            return dialect.type_descriptor(mysql.DATETIME(timezone=True, fsp=self.fsp))
        if dialect.name == "oracle":
            return dialect.type_descriptor(oracle.TIMESTAMP(timezone=True))
        return dialect.type_descriptor(DateTime(timezone=True))

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

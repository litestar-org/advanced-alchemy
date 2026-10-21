import datetime
from typing import Any, Optional

from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql, oracle
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

__all__ = ("DateTimeUTC",)


class DateTimeUTC(TypeDecorator[datetime.datetime]):
    """Timezone Aware DateTime.

    Ensure UTC is stored in the database and that TZ aware dates are returned for all dialects.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def __init__(self, *args: Any, timezone: bool = True, fsp: int = 6, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.timezone = timezone
        self.fsp = fsp

    @property
    def python_type(self) -> type[datetime.datetime]:
        return datetime.datetime

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name in {"mysql", "mariadb"}:
            return dialect.type_descriptor(mysql.DATETIME(timezone=self.timezone, fsp=self.fsp))
        if dialect.name == "oracle":
            return dialect.type_descriptor(oracle.TIMESTAMP(timezone=self.timezone))
        return dialect.type_descriptor(DateTime(timezone=self.timezone))

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

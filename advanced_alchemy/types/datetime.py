import datetime as dt
from typing import Any, Optional

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

__all__ = ("DateTimeUTC",)


class DateTimeUTC(TypeDecorator[dt.datetime]):
    """Timezone Aware DateTime.

    Ensure UTC is stored in the database and that TZ aware dates are returned for all dialects.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @property
    def python_type(self) -> type[dt.datetime]:
        return dt.datetime

    def __init__(
        self,
        *args: Any,
        fsp: Optional[int] = None,
        precision: Optional[int] = None,
        timezone: bool = True,
        **kwargs: Any,
    ) -> None:
        self.fsp = fsp if fsp is not None else precision
        self.timezone = timezone
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if self.fsp is not None:
            if dialect.name in {"mysql", "mariadb"}:
                from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME

                return dialect.type_descriptor(MYSQL_DATETIME(fsp=self.fsp, timezone=self.timezone))
            if dialect.name == "oracle":
                from sqlalchemy.dialects.oracle import TIMESTAMP as ORA_TIMESTAMP

                return dialect.type_descriptor(ORA_TIMESTAMP(timezone=self.timezone))
        return dialect.type_descriptor(DateTime(timezone=self.timezone))

    def process_bind_param(self, value: Optional[dt.datetime], dialect: Dialect) -> Optional[dt.datetime]:
        if value is None:
            return value
        if not value.tzinfo:
            msg = "tzinfo is required"
            raise TypeError(msg)
        return value.astimezone(dt.timezone.utc)

    def process_result_value(self, value: Optional[dt.datetime], dialect: Dialect) -> Optional[dt.datetime]:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value

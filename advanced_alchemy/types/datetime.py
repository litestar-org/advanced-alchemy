import datetime as dt
import warnings
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
        if fsp is not None and precision is not None and fsp != precision:
            msg = "Cannot specify both 'fsp' and 'precision' with different values"
            raise ValueError(msg)
        self.fsp = fsp if fsp is not None else precision
        self.timezone = timezone
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name in {"mysql", "mariadb", "oracle"}:
            if self.fsp is None:
                warnings.warn(
                    "DateTimeUTC() without an explicit 'fsp' compiles to a whole-second type on "
                    "MySQL/MariaDB ('DATETIME') and Oracle ('DATE'), which truncates fractional seconds. "
                    "Pass 'fsp=6' to preserve microsecond precision, or 'fsp=0' to explicitly keep "
                    "whole-second precision and silence this warning. In v2.0, 'fsp=6' will become the default.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            elif self.fsp > 0:
                if dialect.name in {"mysql", "mariadb"}:
                    from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME

                    return dialect.type_descriptor(MYSQL_DATETIME(fsp=self.fsp, timezone=self.timezone))
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

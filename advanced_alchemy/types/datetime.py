import datetime as dt
import warnings
from typing import Any, Optional

from sqlalchemy import DateTime
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME
from sqlalchemy.dialects.oracle import TIMESTAMP as ORA_TIMESTAMP
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

__all__ = ("DateTimeUTC",)

_MAX_MYSQL_DATETIME_FSP = 6


class DateTimeUTC(TypeDecorator[dt.datetime]):
    """Timezone Aware DateTime.

    Ensure UTC is stored in the database and that TZ aware dates are returned for all dialects.

    Note:
        On MySQL/MariaDB and Oracle, omitting ``fsp`` currently compiles to a whole-second column
        type (``DATETIME`` on MySQL/MariaDB and ``DATE`` on Oracle) and emits a
        :class:`DeprecationWarning`. Pass ``fsp=6`` to preserve microsecond precision, or
        ``fsp=0`` to explicitly retain whole-second precision. In v2.0, ``fsp=6`` will become
        the default.
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
        """Initialize the DateTimeUTC type.

        Args:
            *args: Positional arguments forwarded to :class:`sqlalchemy.types.TypeDecorator`.
            fsp: Fractional seconds precision (`0` to `6`) for MySQL/MariaDB and Oracle.
                Defaults to ``None`` in v1.x (emitting a :class:`DeprecationWarning` on
                MySQL/MariaDB and Oracle) and will default to ``6`` in v2.0.
            precision: Alias for ``fsp``.
            timezone: Whether the underlying column type is timezone-aware.
            **kwargs: Keyword arguments forwarded to :class:`sqlalchemy.types.TypeDecorator`.
        """
        if fsp is not None and precision is not None and fsp != precision:
            msg = "Cannot specify both 'fsp' and 'precision' with different values"
            raise ValueError(msg)
        resolved_fsp = fsp if fsp is not None else precision
        if resolved_fsp is not None and (
            not isinstance(resolved_fsp, int)  # pyright: ignore[reportUnnecessaryIsInstance]
            or isinstance(resolved_fsp, bool)
            or not 0 <= resolved_fsp <= _MAX_MYSQL_DATETIME_FSP
        ):
            msg = "fsp must be an integer between 0 and 6"
            raise ValueError(msg)
        self.fsp = resolved_fsp
        self.timezone = timezone
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        """Resolve the dialect-specific type descriptor.

        Args:
            dialect: Target SQLAlchemy dialect.

        Returns:
            Dialect-specific type descriptor.
        """
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
                    return dialect.type_descriptor(MYSQL_DATETIME(fsp=self.fsp, timezone=self.timezone))
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

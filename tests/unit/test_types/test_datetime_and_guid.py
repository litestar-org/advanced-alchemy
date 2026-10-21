"""Unit tests for DateTimeUTC and GUID dialect behavior."""

from base64 import b64encode
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy import TIMESTAMP, DateTime
from sqlalchemy.dialects import mysql, oracle, postgresql, sqlite
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME
from sqlalchemy.dialects.oracle import RAW as ORA_RAW
from sqlalchemy.engine import Dialect
from sqlalchemy.types import CHAR

from advanced_alchemy.types import GUID, DateTimeUTC


def test_datetime_utc_mysql_mariadb_uses_fsp() -> None:
    """DateTimeUTC emits mysql.DATETIME(fsp=6) on MySQL and MariaDB."""
    mysql_dialect = mysql.dialect()
    impl = DateTimeUTC().load_dialect_impl(mysql_dialect)
    assert isinstance(impl, MYSQL_DATETIME)
    assert impl.fsp == 6
    assert impl.timezone is True

    mariadb_dialect = MagicMock(spec=Dialect)
    mariadb_dialect.name = "mariadb"
    mariadb_dialect.type_descriptor.side_effect = lambda t: t
    mariadb_impl = DateTimeUTC(fsp=3, timezone=False).load_dialect_impl(mariadb_dialect)
    assert isinstance(mariadb_impl, MYSQL_DATETIME)
    assert mariadb_impl.fsp == 3
    assert mariadb_impl.timezone is False


def test_datetime_utc_oracle_uses_timestamp_with_timezone() -> None:
    """DateTimeUTC emits oracle.TIMESTAMP(timezone=...) on Oracle instead of DATE."""
    oracle_dialect = oracle.dialect()  # type: ignore[no-untyped-call]
    impl = DateTimeUTC().load_dialect_impl(oracle_dialect)
    assert isinstance(impl, TIMESTAMP)
    assert impl.timezone is True

    compiled = oracle_dialect.type_compiler_instance.process(impl)
    assert compiled == "TIMESTAMP WITH TIME ZONE"


def test_datetime_utc_other_dialects_use_generic_datetime() -> None:
    """DateTimeUTC falls back to generic DateTime(timezone=...) on other dialects."""
    pg_dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    impl = DateTimeUTC().load_dialect_impl(pg_dialect)
    assert isinstance(impl, DateTime)
    assert impl.timezone is True


def test_guid_oracle_respects_binary_flag() -> None:
    """GUID on Oracle uses RAW(16) when binary=True and CHAR(32) when binary=False."""
    oracle_dialect = oracle.dialect()  # type: ignore[no-untyped-call]
    raw_impl = GUID(binary=True).load_dialect_impl(oracle_dialect)
    char_impl = GUID(binary=False).load_dialect_impl(oracle_dialect)
    assert isinstance(raw_impl, ORA_RAW)
    assert isinstance(char_impl, CHAR)

    sample = uuid4()
    assert GUID(binary=True).process_bind_param(sample, oracle_dialect) == sample.bytes
    assert GUID(binary=False).process_bind_param(sample, oracle_dialect) == sample.hex
    assert GUID(binary=True).process_result_value(sample.bytes, oracle_dialect) == sample
    assert GUID(binary=False).process_result_value(sample.hex, oracle_dialect) == sample
    assert GUID(binary=False).process_result_value(sample.bytes, oracle_dialect) == sample


def test_guid_spanner_dialect_names() -> None:
    """GUID supports both 'spanner' and 'spanner+spanner' dialect names."""
    sample = uuid4()
    encoded = b64encode(sample.bytes).decode("ascii")
    for dialect_name in ("spanner", "spanner+spanner"):
        dialect = MagicMock(spec=Dialect)
        dialect.name = dialect_name
        assert GUID().process_bind_param(sample, dialect) == sample.bytes
        assert GUID().process_result_value(encoded, dialect) == sample


def test_guid_sqlite_round_trip_binary_and_hex() -> None:
    """GUID round-trips both binary and hex strings on SQLite."""
    sqlite_dialect = sqlite.dialect()
    sample = uuid4()
    assert GUID(binary=True).process_bind_param(sample, sqlite_dialect) == sample.bytes
    assert GUID(binary=False).process_bind_param(sample, sqlite_dialect) == sample.hex
    assert GUID(binary=True).process_result_value(sample.bytes, sqlite_dialect) == sample
    assert GUID(binary=False).process_result_value(sample.hex, sqlite_dialect) == sample

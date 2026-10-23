"""Unit tests for GUID dialect behavior."""

from base64 import b64encode
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.dialects import oracle, sqlite
from sqlalchemy.dialects.oracle import RAW as ORA_RAW
from sqlalchemy.engine import Dialect
from sqlalchemy.types import CHAR

from advanced_alchemy.types import GUID


def _oracle_dialect() -> Dialect:
    """Create an Oracle dialect instance for unit testing."""
    factory: Any = oracle.dialect
    return cast("Dialect", factory())


def test_guid_oracle_respects_binary_flag() -> None:
    """GUID on Oracle uses RAW(16) when binary=True and CHAR(32) when binary=False."""
    oracle_dialect = _oracle_dialect()
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

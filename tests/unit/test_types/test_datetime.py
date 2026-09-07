import pytest
from sqlalchemy.dialects import mysql, oracle, postgresql, sqlite
from sqlalchemy.engine import Dialect

from advanced_alchemy.types import DateTimeUTC


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        (mysql.dialect(), "DATETIME"),
        (oracle.dialect(), "DATE"),
        (postgresql.dialect(), "TIMESTAMP WITH TIME ZONE"),
        (sqlite.dialect(), "DATETIME"),
    ],
)
def test_default_ddl_is_unchanged(dialect: Dialect, expected: str) -> None:
    """Omitting fsp must keep the DDL emitted before fractional precision was available."""
    assert DateTimeUTC().compile(dialect=dialect) == expected


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        (mysql.dialect(), "DATETIME(6)"),
        (oracle.dialect(), "TIMESTAMP WITH TIME ZONE"),
    ],
)
def test_fsp_retains_fractional_seconds(dialect: Dialect, expected: str) -> None:
    """The dialects that truncate to whole seconds compile to a sub-second type when fsp is set."""
    assert DateTimeUTC(fsp=6).compile(dialect=dialect) == expected


@pytest.mark.parametrize("dialect", [postgresql.dialect(), sqlite.dialect()])
def test_fsp_leaves_other_dialects_alone(dialect: Dialect) -> None:
    """Dialects that already keep microseconds are not rewritten."""
    assert DateTimeUTC(fsp=6).compile(dialect=dialect) == DateTimeUTC().compile(dialect=dialect)


def test_fsp_participates_in_the_cache_key() -> None:
    """cache_ok is True, so two precisions must not share a compiled statement."""
    assert DateTimeUTC()._static_cache_key != DateTimeUTC(fsp=6)._static_cache_key


def test_timezone_argument_is_still_accepted() -> None:
    """AuditColumns constructs DateTimeUTC(timezone=True), which must keep working."""
    assert DateTimeUTC(timezone=True).compile(dialect=postgresql.dialect()) == "TIMESTAMP WITH TIME ZONE"

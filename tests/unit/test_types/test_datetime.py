from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.dialects import mysql, oracle, postgresql, sqlite

from advanced_alchemy.types import DateTimeUTC


def test_python_type_and_cache_ok() -> None:
    instance = DateTimeUTC()
    assert instance.python_type is dt.datetime
    assert instance.cache_ok is True


def test_default_compilation() -> None:
    t = DateTimeUTC()
    assert t.compile(dialect=mysql.dialect()) == "DATETIME"
    assert t.compile(dialect=oracle.dialect()) == "DATE"
    assert t.compile(dialect=postgresql.dialect()) == "TIMESTAMP WITH TIME ZONE"
    assert t.compile(dialect=sqlite.dialect()) == "DATETIME"


def test_fsp_compilation() -> None:
    t = DateTimeUTC(fsp=6)
    assert t.compile(dialect=mysql.dialect()) == "DATETIME(6)"
    assert t.compile(dialect=oracle.dialect()) == "TIMESTAMP WITH TIME ZONE"
    assert t.compile(dialect=postgresql.dialect()) == "TIMESTAMP WITH TIME ZONE"
    assert t.compile(dialect=sqlite.dialect()) == "DATETIME"


def test_precision_alias() -> None:
    t = DateTimeUTC(precision=3)
    assert t.fsp == 3
    assert t.compile(dialect=mysql.dialect()) == "DATETIME(3)"


def test_process_bind_param() -> None:
    t = DateTimeUTC(fsp=6)
    dialect = sqlite.dialect()

    assert t.process_bind_param(None, dialect) is None

    naive = dt.datetime(2026, 1, 1, 12, 0, 0, 123456)
    with pytest.raises(TypeError, match="tzinfo is required"):
        t.process_bind_param(naive, dialect)

    eastern = dt.timezone(dt.timedelta(hours=-5))
    aware = dt.datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=eastern)
    bound = t.process_bind_param(aware, dialect)
    assert bound is not None
    assert bound.tzinfo == dt.timezone.utc
    assert bound.hour == 17
    assert bound.microsecond == 123456


def test_process_result_value() -> None:
    t = DateTimeUTC(fsp=6)
    dialect = sqlite.dialect()

    assert t.process_result_value(None, dialect) is None

    naive = dt.datetime(2026, 1, 1, 12, 0, 0, 654321)
    res = t.process_result_value(naive, dialect)
    assert res is not None
    assert res.tzinfo == dt.timezone.utc
    assert res.microsecond == 654321

    already_aware = dt.datetime(2026, 1, 1, 12, 0, 0, 654321, tzinfo=dt.timezone.utc)
    res2 = t.process_result_value(already_aware, dialect)
    assert res2 == already_aware

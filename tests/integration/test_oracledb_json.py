"""Unit tests for the SQLAlchemy Repository implementation for psycopg."""
from __future__ import annotations

import platform
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.dialects import oracle
from sqlalchemy.schema import CreateTable

from tests.models_uuid import UUIDEventLog

if TYPE_CHECKING:
    from sqlalchemy import Engine

pytestmark = [
    pytest.mark.skipif(platform.uname()[4] != "x86_64", reason="oracle not available on this platform"),
    pytest.mark.integration,
    pytest.mark.xdist_group("oracle"),
]


def test_json_constraint_generation(oracle_engine: Engine) -> None:
    ddl = str(CreateTable(UUIDEventLog.__table__).compile(oracle_engine, dialect=oracle.dialect()))  # type: ignore
    assert "BLOB" in ddl.upper()
    assert "JSON" in ddl.upper()
    with oracle_engine.begin() as conn:
        UUIDEventLog.metadata.create_all(conn)

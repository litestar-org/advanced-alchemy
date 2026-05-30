"""Unit tests for advanced_alchemy.types.json.ORA_JSONB dialect dispatch."""

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects.oracle import BLOB as ORA_BLOB
from sqlalchemy.engine import Dialect

from advanced_alchemy.types.json import ORA_JSONB


def _make_dialect(server_version_info: Any) -> MagicMock:
    """Build a MagicMock dialect that returns the input descriptor unchanged."""
    dialect = MagicMock(spec=Dialect)
    dialect.name = "oracle"
    dialect.server_version_info = server_version_info
    dialect.type_descriptor.side_effect = lambda t: t
    return dialect


@pytest.fixture
def _no_oracle_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate SA 2.0.x where sqlalchemy.dialects.oracle has no JSON symbol."""
    import sqlalchemy.dialects.oracle as ora

    monkeypatch.delattr(ora, "JSON", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "sqlalchemy.dialects.oracle",
        ora,
    )


@pytest.fixture
def _with_oracle_json(monkeypatch: pytest.MonkeyPatch) -> type:
    """Simulate SA 2.1+ by injecting a fake JSON class into sqlalchemy.dialects.oracle."""
    import sqlalchemy.dialects.oracle as ora

    class _FakeOracleJSON:
        def __init__(self) -> None:
            self.is_fake_native_oracle_json = True

    monkeypatch.setattr(ora, "JSON", _FakeOracleJSON, raising=False)
    return _FakeOracleJSON


def test_load_dialect_impl_sa20_returns_blob(_no_oracle_json: None) -> None:
    """SA 2.0.x: no native oracle.JSON available, fall back to ORA_BLOB."""
    dialect = _make_dialect(server_version_info=(23, 0))
    result = ORA_JSONB().load_dialect_impl(dialect)
    assert isinstance(result, ORA_BLOB)


def test_load_dialect_impl_sa21_oracle_23c_returns_native_json(_with_oracle_json: type) -> None:
    """SA 2.1+ on Oracle 21c or newer returns native oracle.JSON."""
    dialect = _make_dialect(server_version_info=(23, 0))
    result = ORA_JSONB().load_dialect_impl(dialect)
    assert isinstance(result, _with_oracle_json)


def test_load_dialect_impl_sa21_oracle_21c_returns_native_json(_with_oracle_json: type) -> None:
    """SA 2.1+ on Oracle 21c exactly returns native oracle.JSON."""
    dialect = _make_dialect(server_version_info=(21, 0))
    result = ORA_JSONB().load_dialect_impl(dialect)
    assert isinstance(result, _with_oracle_json)


def test_load_dialect_impl_sa21_oracle_19c_returns_blob(_with_oracle_json: type) -> None:
    """SA 2.1+ on Oracle 19c falls back to ORA_BLOB."""
    dialect = _make_dialect(server_version_info=(19, 0))
    result = ORA_JSONB().load_dialect_impl(dialect)
    assert isinstance(result, ORA_BLOB)


def test_load_dialect_impl_sa21_missing_server_version_returns_blob(_with_oracle_json: type) -> None:
    """SA 2.1+ but server_version_info is None (offline / first-connect) falls back to ORA_BLOB."""
    dialect = _make_dialect(server_version_info=None)
    result = ORA_JSONB().load_dialect_impl(dialect)
    assert isinstance(result, ORA_BLOB)


def test_should_create_constraint_non_oracle_dialect_returns_false() -> None:
    """Non-oracle dialects never get the JSON CHECK constraint."""
    compiler = MagicMock()
    compiler.dialect.name = "postgresql"
    assert ORA_JSONB()._should_create_constraint(compiler) is False


def test_should_create_constraint_sa20_oracle_returns_true(_no_oracle_json: None) -> None:
    """SA 2.0.x oracle still emits the 'is json (strict)' CHECK."""
    compiler = MagicMock()
    compiler.dialect.name = "oracle"
    compiler.dialect.server_version_info = (23, 0)
    assert ORA_JSONB()._should_create_constraint(compiler) is True


def test_should_create_constraint_sa21_oracle_21c_returns_false(_with_oracle_json: type) -> None:
    """SA 2.1+ oracle 21c+ skips CHECK because native JSON validates itself."""
    compiler = MagicMock()
    compiler.dialect.name = "oracle"
    compiler.dialect.server_version_info = (21, 0)
    assert ORA_JSONB()._should_create_constraint(compiler) is False


def test_should_create_constraint_sa21_oracle_19c_returns_true(_with_oracle_json: type) -> None:
    """SA 2.1+ oracle 19c still needs CHECK because we keep ORA_BLOB path."""
    compiler = MagicMock()
    compiler.dialect.name = "oracle"
    compiler.dialect.server_version_info = (19, 0)
    assert ORA_JSONB()._should_create_constraint(compiler) is True


def test_should_create_constraint_sa21_oracle_missing_version_returns_true(_with_oracle_json: type) -> None:
    """SA 2.1+ oracle with no server version info is treated like older Oracle and keeps CHECK."""
    compiler = MagicMock()
    compiler.dialect.name = "oracle"
    compiler.dialect.server_version_info = None
    assert ORA_JSONB()._should_create_constraint(compiler) is True

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import oracle as oracle_dialect_module
from sqlalchemy.engine import Dialect
from sqlalchemy.types import Boolean

from advanced_alchemy.types import Bool
from advanced_alchemy.types.boolean import _OracleAwareBoolean


class _FakeOracleBoolean(Boolean):
    """Sentinel subclass used to simulate SA 2.1+ exposing oracle.BOOLEAN."""


@pytest.fixture
def fake_oracle_boolean(monkeypatch: pytest.MonkeyPatch) -> type[Boolean]:
    """Inject a BOOLEAN attribute into sqlalchemy.dialects.oracle to simulate SA 2.1+."""
    monkeypatch.setattr(oracle_dialect_module, "BOOLEAN", _FakeOracleBoolean, raising=False)
    return _FakeOracleBoolean


@pytest.fixture
def remove_oracle_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure oracle.BOOLEAN is absent to simulate SA 2.0.x."""
    if hasattr(oracle_dialect_module, "BOOLEAN"):
        monkeypatch.delattr(oracle_dialect_module, "BOOLEAN")


def _make_dialect(name: str, server_version_info: Optional[tuple[int, ...]] = None) -> Dialect:
    dialect = MagicMock(spec=Dialect)
    dialect.name = name
    dialect.server_version_info = server_version_info
    dialect.type_descriptor.side_effect = lambda t: t
    return dialect


def test_python_type_and_cache_ok() -> None:
    assert Bool is _OracleAwareBoolean
    instance = Bool()
    assert instance.python_type is bool
    assert instance.cache_ok is True


def test_oracle_23_with_sa_2_1_uses_native_boolean(fake_oracle_boolean: type[Boolean]) -> None:
    dialect = _make_dialect("oracle", server_version_info=(23, 0, 0, 0, 0))
    result = Bool().load_dialect_impl(dialect)
    assert isinstance(result, fake_oracle_boolean)


def test_oracle_23_with_sa_2_0_falls_back_to_boolean(remove_oracle_boolean: None) -> None:
    dialect = _make_dialect("oracle", server_version_info=(23, 0, 0, 0, 0))
    result = Bool().load_dialect_impl(dialect)
    assert isinstance(result, Boolean)
    assert not isinstance(result, _FakeOracleBoolean)


def test_oracle_19_with_sa_2_1_falls_back_to_boolean(fake_oracle_boolean: type[Boolean]) -> None:
    dialect = _make_dialect("oracle", server_version_info=(19, 0, 0, 0, 0))
    result = Bool().load_dialect_impl(dialect)
    assert isinstance(result, Boolean)
    assert not isinstance(result, _FakeOracleBoolean)


def test_oracle_18_with_sa_2_1_falls_back_to_boolean(fake_oracle_boolean: type[Boolean]) -> None:
    dialect = _make_dialect("oracle", server_version_info=(18, 0, 0, 0, 0))
    result = Bool().load_dialect_impl(dialect)
    assert isinstance(result, Boolean)
    assert not isinstance(result, _FakeOracleBoolean)


def test_oracle_with_no_server_version_falls_back(fake_oracle_boolean: type[Boolean]) -> None:
    dialect = _make_dialect("oracle", server_version_info=None)
    result = Bool().load_dialect_impl(dialect)
    assert isinstance(result, Boolean)
    assert not isinstance(result, _FakeOracleBoolean)


@pytest.mark.parametrize("dialect_name", ["postgresql", "mysql", "sqlite", "mssql", "duckdb", "cockroachdb"])
def test_non_oracle_dialects_use_stock_boolean(
    dialect_name: str,
    fake_oracle_boolean: type[Boolean],
) -> None:
    dialect = _make_dialect(dialect_name, server_version_info=(99, 0, 0))
    result = Bool().load_dialect_impl(dialect)
    assert isinstance(result, Boolean)
    assert not isinstance(result, _FakeOracleBoolean)


def test_load_dialect_impl_returns_type_engine(fake_oracle_boolean: type[Boolean]) -> None:
    dialect = _make_dialect("oracle", server_version_info=(23, 0, 0, 0, 0))
    instance = Bool()
    result: Any = instance.load_dialect_impl(dialect)
    assert result is not None
    assert dialect.type_descriptor.called

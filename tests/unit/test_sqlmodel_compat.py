"""Tests for SQLModel compatibility with Advanced Alchemy.

Validates that SQLModel table=True models can be used with AA repositories and services.
"""

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

sqlmodel = pytest.importorskip("sqlmodel")

from sqlmodel import Field as SQLModelField
from sqlmodel import SQLModel

from advanced_alchemy.base import ModelProtocol, model_to_dict
from advanced_alchemy.service.typing import is_sqlmodel_table_model, schema_dump


# ---------------------------------------------------------------------------
# Test fixtures: SQLModel table models
# ---------------------------------------------------------------------------


class HeroModel(SQLModel, table=True):
    """A simple SQLModel table model for testing."""

    __tablename__ = "test_hero"  # type: ignore[assignment]

    id: Optional[int] = SQLModelField(default=None, primary_key=True)
    name: str
    secret_name: str
    age: Optional[int] = None


class PlainSchema(SQLModel):
    """A plain SQLModel schema (no table) — should NOT satisfy ModelProtocol."""

    name: str
    age: int


# ---------------------------------------------------------------------------
# Task 1.1: ModelProtocol no longer requires to_dict()
# ---------------------------------------------------------------------------


def test_sqlmodel_table_satisfies_model_protocol() -> None:
    """SQLModel table=True models should satisfy ModelProtocol (no to_dict required)."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert isinstance(hero, ModelProtocol)


def test_sqlmodel_table_class_has_required_attrs() -> None:
    """SQLModel table=True classes have __table__ and __mapper__."""
    assert hasattr(HeroModel, "__table__")
    assert hasattr(HeroModel, "__mapper__")


def test_plain_schema_does_not_satisfy_protocol() -> None:
    """Plain SQLModel schemas (no table) should NOT satisfy ModelProtocol."""
    schema = PlainSchema(name="test", age=5)
    # Plain schemas don't have __table__ or __mapper__
    assert not hasattr(schema, "__table__")
    assert not hasattr(schema, "__mapper__")


# ---------------------------------------------------------------------------
# Task 1.2: model_to_dict utility
# ---------------------------------------------------------------------------


def test_model_to_dict_with_sqlmodel() -> None:
    """model_to_dict should work with SQLModel table instances (no to_dict method)."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    result = model_to_dict(hero)
    assert result["id"] == 1
    assert result["name"] == "Spider-Boy"
    assert result["secret_name"] == "Pedro"
    assert result["age"] == 10


def test_model_to_dict_with_exclude() -> None:
    """model_to_dict should respect the exclude parameter."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    result = model_to_dict(hero, exclude={"secret_name"})
    assert "secret_name" not in result
    assert result["name"] == "Spider-Boy"


def test_model_to_dict_with_aa_model_delegates_to_to_dict() -> None:
    """model_to_dict should call to_dict() when available (AA models)."""
    mock_model = MagicMock()
    mock_model.to_dict.return_value = {"id": 1, "name": "test"}
    result = model_to_dict(mock_model, exclude={"secret"})
    mock_model.to_dict.assert_called_once_with(exclude={"secret"})
    assert result == {"id": 1, "name": "test"}


def test_model_to_dict_excludes_sentinel_fields() -> None:
    """model_to_dict should exclude sa_orm_sentinel and _sentinel by default."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    result = model_to_dict(hero)
    assert "sa_orm_sentinel" not in result
    assert "_sentinel" not in result


# ---------------------------------------------------------------------------
# Task 1.3: is_sqlmodel_table_model detection
# ---------------------------------------------------------------------------


def test_is_sqlmodel_table_model_with_table_instance() -> None:
    """SQLModel table=True instances should be detected."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_sqlmodel_table_model(hero) is True


def test_is_sqlmodel_table_model_with_table_class() -> None:
    """SQLModel table=True classes should be detected."""
    assert is_sqlmodel_table_model(HeroModel) is True


def test_is_sqlmodel_table_model_with_plain_schema() -> None:
    """Plain SQLModel schemas (no table) should NOT be detected."""
    schema = PlainSchema(name="test", age=5)
    assert is_sqlmodel_table_model(schema) is False


def test_is_sqlmodel_table_model_with_dict() -> None:
    """Dicts should not be detected as SQLModel table models."""
    assert is_sqlmodel_table_model({"name": "test"}) is False


def test_is_sqlmodel_table_model_with_none() -> None:
    """None should not be detected."""
    assert is_sqlmodel_table_model(None) is False


# ---------------------------------------------------------------------------
# Task 3.1: schema_dump should NOT decompose SQLModel table instances
# ---------------------------------------------------------------------------


def test_schema_dump_preserves_sqlmodel_table_instance() -> None:
    """schema_dump should return SQLModel table instances as-is (not call model_dump)."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    result = schema_dump(hero)
    # Should return the same instance, not a dict from model_dump()
    assert result is hero


def test_schema_dump_converts_plain_schema_to_dict() -> None:
    """schema_dump should still convert plain Pydantic/SQLModel schemas to dicts."""
    schema = PlainSchema(name="test", age=5)
    result = schema_dump(schema)
    assert isinstance(result, dict)
    assert result["name"] == "test"
    assert result["age"] == 5

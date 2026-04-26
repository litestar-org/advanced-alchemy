"""Tests for SQLModel compatibility with Advanced Alchemy.

Validates that SQLModel table=True models can be used with AA repositories and services.
"""

from collections.abc import Generator
from typing import Optional, cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sqlmodel = pytest.importorskip("sqlmodel")

from sqlmodel import Field as SQLModelField  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from advanced_alchemy.base import ModelProtocol, model_to_dict  # noqa: E402
from advanced_alchemy.repository import SQLAlchemySyncRepository  # noqa: E402
from advanced_alchemy.repository._util import get_instrumented_attr, get_primary_key_info, model_from_dict  # noqa: E402
from advanced_alchemy.utils.serializers import (  # noqa: E402
    is_pydantic_model,
    is_schema,
    is_schema_or_dict,
    is_schema_or_dict_with_field,
    is_schema_or_dict_without_field,
    is_schema_with_field,
    is_schema_without_field,
    is_sqlmodel_table_model,
    schema_dump,
)

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
    result = model_to_dict(cast(ModelProtocol, hero))
    assert result["id"] == 1
    assert result["name"] == "Spider-Boy"
    assert result["secret_name"] == "Pedro"
    assert result["age"] == 10


def test_model_to_dict_with_exclude() -> None:
    """model_to_dict should respect the exclude parameter."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    result = model_to_dict(cast(ModelProtocol, hero), exclude={"secret_name"})
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
    result = model_to_dict(cast(ModelProtocol, hero))
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
    # mypy can't see HeroModel as ModelProtocol (sqlmodel stubs lack __mapper__/__table__)
    # so it resolves to the Any catch-all overload returning dict[str, Any]
    assert result is hero  # type: ignore[comparison-overlap]


def test_schema_dump_converts_plain_schema_to_dict() -> None:
    """schema_dump should still convert plain Pydantic/SQLModel schemas to dicts."""
    schema = PlainSchema(name="test", age=5)
    result = schema_dump(schema)
    assert isinstance(result, dict)
    assert result["name"] == "test"
    assert result["age"] == 5


# ---------------------------------------------------------------------------
# Chapter 2: is_schema() family excludes SQLModel table models
# ---------------------------------------------------------------------------


def test_is_pydantic_model_still_matches_sqlmodel_table() -> None:
    """is_pydantic_model() is a structural check — SQLModel table models ARE BaseModel subclasses."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_pydantic_model(hero) is True


def test_is_pydantic_model_matches_plain_schema() -> None:
    """Plain SQLModel schemas are also BaseModel subclasses."""
    schema = PlainSchema(name="test", age=5)
    assert is_pydantic_model(schema) is True


def test_is_schema_excludes_sqlmodel_table_instance() -> None:
    """is_schema() is a semantic check — SQLModel table models are NOT schemas."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_schema(hero) is False


def test_is_schema_includes_plain_sqlmodel_schema() -> None:
    """Plain SQLModel schemas (no table) should still be recognized as schemas."""
    schema = PlainSchema(name="test", age=5)
    assert is_schema(schema) is True


def test_is_schema_with_field_excludes_sqlmodel_table() -> None:
    """is_schema_with_field() should return False for SQLModel table models."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_schema_with_field(hero, "name") is False


def test_is_schema_with_field_includes_plain_schema() -> None:
    """is_schema_with_field() should work for plain SQLModel schemas."""
    schema = PlainSchema(name="test", age=5)
    assert is_schema_with_field(schema, "name") is True


def test_is_schema_without_field_excludes_sqlmodel_table() -> None:
    """is_schema_without_field() should return False for SQLModel table models."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_schema_without_field(hero, "nonexistent") is False


def test_is_schema_or_dict_excludes_sqlmodel_table() -> None:
    """is_schema_or_dict() should return False for SQLModel table models."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_schema_or_dict(hero) is False


def test_is_schema_or_dict_with_field_excludes_sqlmodel_table() -> None:
    """is_schema_or_dict_with_field() should return False for SQLModel table models."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_schema_or_dict_with_field(hero, "name") is False


def test_is_schema_or_dict_without_field_excludes_sqlmodel_table() -> None:
    """is_schema_or_dict_without_field() should return False for SQLModel table models."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert is_schema_or_dict_without_field(hero, "nonexistent") is False


# ---------------------------------------------------------------------------
# Chapter 3: Repository utilities with SQLModel
# ---------------------------------------------------------------------------


def test_model_from_dict_creates_sqlmodel_instance() -> None:
    """model_from_dict should create a SQLModel table instance from kwargs."""
    hero = model_from_dict(HeroModel, id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    assert isinstance(hero, HeroModel)
    assert hero.name == "Spider-Boy"
    assert hero.secret_name == "Pedro"
    assert hero.age == 10


def test_model_from_dict_with_partial_kwargs() -> None:
    """model_from_dict should handle partial kwargs (optional fields omitted)."""
    hero = model_from_dict(HeroModel, name="Spider-Boy", secret_name="Pedro")
    assert isinstance(hero, HeroModel)
    assert hero.name == "Spider-Boy"
    assert hero.age is None


def test_get_primary_key_info_with_sqlmodel() -> None:
    """get_primary_key_info should extract PK info from SQLModel table models."""
    pk_columns, pk_attr_names = get_primary_key_info(cast("type[ModelProtocol]", HeroModel))
    assert len(pk_columns) == 1
    assert pk_attr_names == ("id",)


def test_get_instrumented_attr_with_sqlmodel() -> None:
    """get_instrumented_attr should retrieve attributes from SQLModel table models."""
    attr = get_instrumented_attr(cast("type[ModelProtocol]", HeroModel), "name")
    assert attr.key == "name"


def test_get_instrumented_attr_passthrough() -> None:
    """get_instrumented_attr should pass through InstrumentedAttribute objects."""
    attr = get_instrumented_attr(cast("type[ModelProtocol]", HeroModel), HeroModel.name)  # type: ignore[arg-type]
    assert attr.key == "name"


def test_model_to_dict_roundtrip_via_model_from_dict() -> None:
    """model_to_dict -> model_from_dict should produce an equivalent instance."""
    hero = HeroModel(id=1, name="Spider-Boy", secret_name="Pedro", age=10)
    as_dict = model_to_dict(cast(ModelProtocol, hero))
    rebuilt = model_from_dict(HeroModel, **as_dict)
    assert rebuilt.id == hero.id
    assert rebuilt.name == hero.name
    assert rebuilt.secret_name == hero.secret_name
    assert rebuilt.age == hero.age


# ---------------------------------------------------------------------------
# Chapter 4: Repository integration with SQLModel (in-memory SQLite)
# ---------------------------------------------------------------------------


class HeroRepository(SQLAlchemySyncRepository[HeroModel]):
    """Repository for HeroModel."""

    model_type = HeroModel


@pytest.fixture()
def hero_session() -> "Generator[Session, None, None]":
    """Create an in-memory SQLite session with the HeroModel table."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as session:
        yield session  # type: ignore[misc]


def test_repo_update_many_with_sqlmodel(hero_session: "Session") -> None:
    """Repository.update_many should handle SQLModel model instances via model_to_dict."""
    repo = HeroRepository(session=hero_session)
    hero = repo.add(HeroModel(name="Spider-Boy", secret_name="Pedro", age=10))
    hero_session.commit()

    hero.age = 20
    updated = repo.update_many([hero])
    hero_session.commit()
    assert updated[0].age == 20


def test_repo_upsert_creates_with_sqlmodel(hero_session: "Session") -> None:
    """Repository.upsert should create a new SQLModel instance when not found."""
    repo = HeroRepository(session=hero_session)
    hero = HeroModel(name="Spider-Boy", secret_name="Pedro", age=10)
    result = repo.upsert(hero)
    hero_session.commit()
    assert result.name == "Spider-Boy"
    assert result.id is not None


def test_repo_upsert_updates_with_sqlmodel(hero_session: "Session") -> None:
    """Repository.upsert should update existing SQLModel instance when found by match_fields."""
    repo = HeroRepository(session=hero_session)
    existing = repo.add(HeroModel(name="Spider-Boy", secret_name="Pedro", age=10))
    hero_session.commit()

    updated_hero = HeroModel(name="Spider-Boy", secret_name="Pedro P", age=15)
    result = repo.upsert(updated_hero, match_fields=["name"])
    hero_session.commit()
    assert result.id == existing.id
    assert result.secret_name == "Pedro P"


def test_repo_upsert_fallback_match_by_all_fields(hero_session: "Session") -> None:
    """Repository.upsert should match by all non-PK fields when no id and no match_fields."""
    repo = HeroRepository(session=hero_session)
    repo.add(HeroModel(name="Spider-Boy", secret_name="Pedro", age=10))
    hero_session.commit()

    # No id set, no match_fields — triggers model_to_dict(data, exclude=exclude_cols) fallback
    lookup = HeroModel(name="Spider-Boy", secret_name="Pedro", age=10)
    result = repo.upsert(lookup)
    hero_session.commit()
    assert result.name == "Spider-Boy"
    assert result.id is not None

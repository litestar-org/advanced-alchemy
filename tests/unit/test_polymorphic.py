"""Tests for with_polymorphic() support in repositories and services.

Covers:
- _polymorphic.py utility functions
- PolymorphicEntityConfig
- PolymorphicIdentityFilter
- SQLAlchemyAsyncRepository / SQLAlchemySyncRepository with AliasedClass model_type
- Service layer _to_model with AliasedClass
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column, with_polymorphic
from sqlalchemy.orm import Mapped as SAMapped

from advanced_alchemy.repository._polymorphic import (
    PolymorphicEntityConfig,
    get_base_class_mapper,
    get_base_model_class,
    get_model_display_name,
    get_polymorphic_type_map,
    get_table_name,
    is_aliased_class,
    resolve_polymorphic_subclass,
    validate_polymorphic_entity,
)
from advanced_alchemy.filters import PolymorphicIdentityFilter


# ---------------------------------------------------------------------------
# Fixture models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class Animal(Base):
    """Base polymorphic model with single-table inheritance."""

    __tablename__ = "animal"

    id: SAMapped[int] = mapped_column(Integer, primary_key=True)
    name: SAMapped[str] = mapped_column(String(100), nullable=False)
    kind: SAMapped[str] = mapped_column(String(50), nullable=False)

    __mapper_args__ = {
        "polymorphic_on": "kind",
        "polymorphic_identity": "animal",
    }


class Dog(Animal):
    """Dog subclass — polymorphic_identity='dog'."""

    breed: SAMapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "dog"}


class Cat(Animal):
    """Cat subclass — polymorphic_identity='cat'."""

    indoor: SAMapped[Optional[str]] = mapped_column(String(10), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "cat"}


class UnmappedClass:
    """A plain Python class with no SQLAlchemy mapping."""


# AliasedClass that queries all subtypes
AllAnimals = with_polymorphic(Animal, (Dog, Cat))


# ---------------------------------------------------------------------------
# Database fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Dog(id=1, name="Rex", kind="dog", breed="Labrador"),
                Dog(id=2, name="Buddy", kind="dog", breed="Poodle"),
                Cat(id=3, name="Whiskers", kind="cat", indoor="yes"),
                Cat(id=4, name="Luna", kind="cat", indoor="no"),
                Animal(id=5, name="Unknown", kind="animal"),
            ]
        )
        session.commit()
        yield session


# ===========================================================================
# is_aliased_class
# ===========================================================================


def test_is_aliased_class_returns_true_for_aliased():
    assert is_aliased_class(AllAnimals) is True


def test_is_aliased_class_returns_false_for_plain_model():
    assert is_aliased_class(Animal) is False
    assert is_aliased_class(Dog) is False


def test_is_aliased_class_returns_false_for_non_model():
    assert is_aliased_class(UnmappedClass) is False
    assert is_aliased_class("not_a_model") is False
    assert is_aliased_class(None) is False
    assert is_aliased_class(42) is False


# ===========================================================================
# get_base_model_class
# ===========================================================================


def test_get_base_model_class_returns_base_for_aliased():
    result = get_base_model_class(AllAnimals)
    assert result is Animal


def test_get_base_model_class_returns_same_for_plain():
    assert get_base_model_class(Animal) is Animal
    assert get_base_model_class(Dog) is Dog


# ===========================================================================
# get_model_display_name
# ===========================================================================


def test_get_model_display_name_for_aliased():
    assert get_model_display_name(AllAnimals) == "Animal"


def test_get_model_display_name_for_plain_class():
    assert get_model_display_name(Animal) == "Animal"
    assert get_model_display_name(Dog) == "Dog"


def test_get_model_display_name_fallback_for_non_model():
    result = get_model_display_name(UnmappedClass)
    assert "UnmappedClass" in result


# ===========================================================================
# get_table_name
# ===========================================================================


def test_get_table_name_for_aliased():
    name = get_table_name(AllAnimals)
    assert name == "animal"


def test_get_table_name_for_plain_class():
    assert get_table_name(Animal) == "animal"


def test_get_table_name_returns_none_for_non_model():
    assert get_table_name(UnmappedClass) is None


# ===========================================================================
# get_base_class_mapper
# ===========================================================================


def test_get_base_class_mapper_for_aliased():
    from sqlalchemy.orm import class_mapper

    mapper = get_base_class_mapper(AllAnimals)
    assert mapper is class_mapper(Animal)


def test_get_base_class_mapper_for_plain_class():
    from sqlalchemy.orm import class_mapper

    mapper = get_base_class_mapper(Animal)
    assert mapper is class_mapper(Animal)


# ===========================================================================
# resolve_polymorphic_subclass
# ===========================================================================


def test_resolve_polymorphic_subclass_routes_to_dog():
    result = resolve_polymorphic_subclass(AllAnimals, {"kind": "dog", "name": "Rex"})
    assert result is Dog


def test_resolve_polymorphic_subclass_routes_to_cat():
    result = resolve_polymorphic_subclass(AllAnimals, {"kind": "cat", "name": "Luna"})
    assert result is Cat


def test_resolve_polymorphic_subclass_falls_back_to_base():
    result = resolve_polymorphic_subclass(AllAnimals, {"kind": "unknown_type", "name": "X"})
    assert result is Animal


def test_resolve_polymorphic_subclass_without_discriminator_key():
    result = resolve_polymorphic_subclass(AllAnimals, {"name": "No kind provided"})
    assert result is Animal


def test_resolve_polymorphic_subclass_on_plain_class():
    result = resolve_polymorphic_subclass(Animal, {"kind": "dog"})
    assert result is Animal


# ===========================================================================
# get_polymorphic_type_map
# ===========================================================================


def test_get_polymorphic_type_map_from_aliased():
    type_map = get_polymorphic_type_map(AllAnimals)
    assert "dog" in type_map
    assert "cat" in type_map
    assert type_map["dog"] is Dog
    assert type_map["cat"] is Cat


def test_get_polymorphic_type_map_from_plain_class():
    type_map = get_polymorphic_type_map(Animal)
    assert "dog" in type_map
    assert "cat" in type_map


def test_get_polymorphic_type_map_returns_empty_for_non_model():
    assert get_polymorphic_type_map(UnmappedClass) == {}


# ===========================================================================
# validate_polymorphic_entity
# ===========================================================================


def test_validate_polymorphic_entity_accepts_mapped_class():
    validate_polymorphic_entity(Animal)
    validate_polymorphic_entity(Dog)


def test_validate_polymorphic_entity_accepts_aliased_class():
    validate_polymorphic_entity(AllAnimals)


def test_validate_polymorphic_entity_raises_for_string():
    with pytest.raises(TypeError):
        validate_polymorphic_entity("not_a_model")


def test_validate_polymorphic_entity_raises_for_none():
    with pytest.raises(TypeError):
        validate_polymorphic_entity(None)


def test_validate_polymorphic_entity_raises_for_instance():
    dog = Dog.__new__(Dog)
    with pytest.raises(TypeError):
        validate_polymorphic_entity(dog)


# ===========================================================================
# PolymorphicEntityConfig
# ===========================================================================


def test_polymorphic_entity_config_from_entity_captures_subclass_map():
    config = PolymorphicEntityConfig.from_entity(AllAnimals)
    assert config.base_class is Animal
    assert config.discriminator_attr == "kind"
    assert config.subclass_map.get("dog") is Dog
    assert config.subclass_map.get("cat") is Cat


def test_polymorphic_entity_config_from_entity_entity_stored():
    config = PolymorphicEntityConfig.from_entity(AllAnimals)
    assert config.entity is AllAnimals


def test_polymorphic_entity_config_raises_for_plain_class():
    with pytest.raises(ValueError, match="AliasedClass"):
        PolymorphicEntityConfig.from_entity(Animal)


def test_polymorphic_entity_config_resolve_class_for_dog():
    config = PolymorphicEntityConfig.from_entity(AllAnimals)
    assert config.resolve_class_for({"kind": "dog"}) is Dog


def test_polymorphic_entity_config_resolve_class_for_cat():
    config = PolymorphicEntityConfig.from_entity(AllAnimals)
    assert config.resolve_class_for({"kind": "cat"}) is Cat


def test_polymorphic_entity_config_resolve_class_for_unknown():
    config = PolymorphicEntityConfig.from_entity(AllAnimals)
    assert config.resolve_class_for({"kind": "bird"}) is Animal


def test_polymorphic_entity_config_resolve_class_no_discriminator():
    config = PolymorphicEntityConfig.from_entity(AllAnimals)
    assert config.resolve_class_for({}) is Animal


# ===========================================================================
# PolymorphicIdentityFilter
# ===========================================================================


def test_polymorphic_identity_filter_single_value(db_session: Session):
    from sqlalchemy import select

    filt = PolymorphicIdentityFilter(identities=["dog"])
    stmt = select(AllAnimals)
    stmt = filt.append_to_statement(stmt, AllAnimals)
    results = db_session.execute(stmt).scalars().all()
    assert all(isinstance(r, Dog) for r in results)
    assert len(results) == 2


def test_polymorphic_identity_filter_multiple_values(db_session: Session):
    from sqlalchemy import select

    filt = PolymorphicIdentityFilter(identities=["dog", "cat"])
    stmt = select(AllAnimals)
    stmt = filt.append_to_statement(stmt, AllAnimals)
    results = db_session.execute(stmt).scalars().all()
    assert len(results) == 4


def test_polymorphic_identity_filter_no_op_when_none(db_session: Session):
    from sqlalchemy import select

    filt = PolymorphicIdentityFilter(identities=None)
    stmt = select(AllAnimals)
    filtered = filt.append_to_statement(stmt, AllAnimals)
    assert filtered is stmt


def test_polymorphic_identity_filter_no_op_when_empty(db_session: Session):
    from sqlalchemy import select

    filt = PolymorphicIdentityFilter(identities=[])
    stmt = select(AllAnimals)
    filtered = filt.append_to_statement(stmt, AllAnimals)
    assert filtered is stmt


def test_polymorphic_identity_filter_explicit_polymorphic_on(db_session: Session):
    from sqlalchemy import select

    filt = PolymorphicIdentityFilter(identities=["cat"], polymorphic_on="kind")
    stmt = select(AllAnimals)
    stmt = filt.append_to_statement(stmt, AllAnimals)
    results = db_session.execute(stmt).scalars().all()
    assert all(isinstance(r, Cat) for r in results)
    assert len(results) == 2


def test_polymorphic_identity_filter_on_plain_model(db_session: Session):
    from sqlalchemy import select

    filt = PolymorphicIdentityFilter(identities=["dog"])
    stmt = select(Animal)
    stmt = filt.append_to_statement(stmt, Animal)
    results = db_session.execute(stmt).scalars().all()
    assert all(r.kind == "dog" for r in results)
    assert len(results) == 2


# ===========================================================================
# Repository integration: sync repository with with_polymorphic model_type
# ===========================================================================


def test_sync_repository_list_with_polymorphic(db_session: Session):
    """Listing all records through a polymorphic repo returns instances of correct subclasses."""
    from advanced_alchemy.repository import SQLAlchemySyncRepository

    class AnimalRepo(SQLAlchemySyncRepository[Animal]):
        model_type = AllAnimals  # type: ignore[assignment]

    repo = AnimalRepo(session=db_session)
    results = repo.list()
    assert len(results) == 5
    kinds = {type(r).__name__ for r in results}
    assert "Dog" in kinds
    assert "Cat" in kinds


def test_sync_repository_list_filter_by_identity(db_session: Session):
    """PolymorphicIdentityFilter works end-to-end with a polymorphic repo."""
    from advanced_alchemy.repository import SQLAlchemySyncRepository

    class AnimalRepo(SQLAlchemySyncRepository[Animal]):
        model_type = AllAnimals  # type: ignore[assignment]

    repo = AnimalRepo(session=db_session)
    dogs = repo.list(PolymorphicIdentityFilter(identities=["dog"]))
    assert all(isinstance(d, Dog) for d in dogs)
    assert len(dogs) == 2


def test_sync_repository_get_with_polymorphic(db_session: Session):
    """get() returns the correct concrete subclass through a polymorphic repo."""
    from advanced_alchemy.repository import SQLAlchemySyncRepository

    class AnimalRepo(SQLAlchemySyncRepository[Animal]):
        model_type = AllAnimals  # type: ignore[assignment]

    repo = AnimalRepo(session=db_session)
    result = repo.get(1)
    assert isinstance(result, Dog)
    assert result.name == "Rex"


def test_sync_repository_count_with_polymorphic(db_session: Session):
    from advanced_alchemy.repository import SQLAlchemySyncRepository

    class AnimalRepo(SQLAlchemySyncRepository[Animal]):
        model_type = AllAnimals  # type: ignore[assignment]

    repo = AnimalRepo(session=db_session)
    total = repo.count()
    assert total == 5


def test_sync_repository_delete_with_polymorphic(db_session: Session):
    """delete() through a polymorphic repo removes the correct record."""
    from advanced_alchemy.repository import SQLAlchemySyncRepository

    class AnimalRepo(SQLAlchemySyncRepository[Animal]):
        model_type = AllAnimals  # type: ignore[assignment]

    repo = AnimalRepo(session=db_session)
    repo.delete(1)
    db_session.flush()
    remaining = repo.list()
    ids = [r.id for r in remaining]
    assert 1 not in ids
    assert len(remaining) == 4


def test_sync_repository_add_with_polymorphic_routes_subclass(db_session: Session):
    """add() through a polymorphic repo creates the correct concrete subclass."""
    from advanced_alchemy.repository import SQLAlchemySyncRepository

    class AnimalRepo(SQLAlchemySyncRepository[Animal]):
        model_type = AllAnimals  # type: ignore[assignment]

    repo = AnimalRepo(session=db_session)
    new_dog = Dog(id=10, name="Spot", kind="dog", breed="Dalmatian")
    saved = repo.add(new_dog)
    assert isinstance(saved, Dog)
    assert saved.breed == "Dalmatian"


# ===========================================================================
# model_from_dict respects discriminator routing for AliasedClass
# ===========================================================================


def test_model_from_dict_routes_to_dog_for_aliased():
    from advanced_alchemy.repository._util import model_from_dict

    instance = model_from_dict(AllAnimals, id=20, name="Sparky", kind="dog", breed="Beagle")
    assert isinstance(instance, Dog)
    assert instance.breed == "Beagle"


def test_model_from_dict_routes_to_cat_for_aliased():
    from advanced_alchemy.repository._util import model_from_dict

    instance = model_from_dict(AllAnimals, id=21, name="Mittens", kind="cat", indoor="yes")
    assert isinstance(instance, Cat)
    assert instance.indoor == "yes"


def test_model_from_dict_falls_back_to_base_for_aliased():
    from advanced_alchemy.repository._util import model_from_dict

    instance = model_from_dict(AllAnimals, id=22, name="Unknown", kind="animal")
    assert isinstance(instance, Animal)

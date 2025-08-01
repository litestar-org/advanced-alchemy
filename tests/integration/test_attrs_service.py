# ruff: noqa: UP045
"""Integration tests for attrs support in Advanced Alchemy services."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, cast

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session

from advanced_alchemy import base, mixins
from advanced_alchemy.repository import (
    SQLAlchemyAsyncRepository,
    SQLAlchemySyncRepository,
)
from advanced_alchemy.service import SQLAlchemyAsyncQueryService, SQLAlchemySyncQueryService
from advanced_alchemy.service._async import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.service._sync import SQLAlchemySyncRepositoryService
from advanced_alchemy.service.typing import (
    ATTRS_INSTALLED,
    is_attrs_instance,
    is_attrs_instance_with_field,
    is_attrs_instance_without_field,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed"),
]

here = Path(__file__).parent
fixture_path = here.parent.parent / "examples"
attrs_registry = base.create_registry()

if ATTRS_INSTALLED:
    from attrs import define, field

    @define
    class PersonAttrs:
        """attrs class for testing."""

        name: str
        age: int
        email: Optional[str] = None

    @define
    class PersonWithDefaults:
        """attrs class with field defaults."""

        name: str
        age: int = field(default=18)
        is_active: bool = field(default=True)
        tags: list[str] = field(factory=list)

    @define
    class StateAttrs:
        """attrs class matching US State structure."""

        abbreviation: str
        name: str

    @define
    class StateQueryAttrs:
        """attrs class for query results."""

        state_abbreviation: str
        state_name: str


class UUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID primary keys."""

    registry = attrs_registry


class Person(UUIDBase):
    """Person model for testing attrs integration."""

    __tablename__ = "person"
    name: Mapped[str]
    age: Mapped[int]
    email: Mapped[Optional[str]]


class USState(UUIDBase):
    """US State model for testing."""

    __tablename__ = "us_state_lookup"
    abbreviation: Mapped[str]
    name: Mapped[str]


class PersonSyncRepository(SQLAlchemySyncRepository[Person]):
    """Person repository."""

    model_type = Person


class PersonSyncService(SQLAlchemySyncRepositoryService[Person, PersonSyncRepository]):
    """Person service."""

    repository_type = PersonSyncRepository


class PersonAsyncRepository(SQLAlchemyAsyncRepository[Person]):
    """Person async repository."""

    model_type = Person


class PersonAsyncService(SQLAlchemyAsyncRepositoryService[Person, PersonAsyncRepository]):
    """Person async service."""

    repository_type = PersonAsyncRepository


class USStateSyncRepository(SQLAlchemySyncRepository[USState]):
    """US State repository."""

    model_type = USState


class USStateSyncService(SQLAlchemySyncRepositoryService[USState, USStateSyncRepository]):
    """US State service."""

    repository_type = USStateSyncRepository


class USStateAsyncRepository(SQLAlchemyAsyncRepository[USState]):
    """US State async repository."""

    model_type = USState


class USStateAsyncService(SQLAlchemyAsyncRepositoryService[USState, USStateAsyncRepository]):
    """US State async service."""

    repository_type = USStateAsyncRepository


class StateQuery(base.SQLQuery):
    """Custom query for testing attrs conversion."""

    __table__ = select(  # type: ignore[misc]
        USState.abbreviation.label("state_abbreviation"),
        USState.name.label("state_name"),
    ).alias("state_lookup")
    __mapper_args__ = {
        "primary_key": [USState.abbreviation],
    }
    state_abbreviation: str  # type: ignore[misc]
    state_name: str  # type: ignore[misc]


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_sync_attrs_service_basic_operations() -> None:
    """Test basic service operations with attrs classes."""
    engine = create_engine("sqlite://")
    attrs_registry.metadata.create_all(engine)

    with Session(engine) as session:
        service = PersonSyncService(session=session)

        # Test create with dict data first (which works with existing services)
        person_data = {"name": "John Doe", "age": 30, "email": "john@example.com"}
        created_person = service.create(person_data)

        assert created_person.name == "John Doe"
        assert created_person.age == 30
        assert created_person.email == "john@example.com"

        # Test create many with dict data
        people_data = [
            {"name": "Jane Smith", "age": 25, "email": "jane@example.com"},
            {"name": "Bob Wilson", "age": 35, "email": "bob@example.com"},
        ]
        created_people = service.create_many(people_data)
        assert len(created_people) == 2

        # Test to_schema conversion to attrs - this is the main integration point
        person_attrs = service.to_schema(created_person, schema_type=PersonAttrs)
        assert isinstance(person_attrs, PersonAttrs)
        assert is_attrs_instance(person_attrs)
        assert is_attrs_instance_with_field(person_attrs, "name")
        assert is_attrs_instance_with_field(person_attrs, "age")
        assert is_attrs_instance_with_field(person_attrs, "email")
        assert not is_attrs_instance_without_field(person_attrs, "name")

        # Test list conversion to attrs
        all_people = service.list()
        people_paginated = service.to_schema(all_people, schema_type=PersonAttrs)
        assert len(people_paginated.items) == 3
        assert all(isinstance(person, PersonAttrs) for person in people_paginated.items)


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_sync_attrs_with_defaults() -> None:
    """Test attrs classes with default values."""
    engine = create_engine("sqlite://")
    attrs_registry.metadata.create_all(engine)

    with Session(engine) as session:
        service = PersonSyncService(session=session)

        # Create with dict data and default values
        person_data = {"name": "Default Person", "age": 18}
        created_person = service.create(person_data)

        assert created_person.name == "Default Person"
        assert created_person.age == 18

        # Convert to attrs with defaults - this tests the attrs schema conversion
        person_attrs = service.to_schema(created_person, schema_type=PersonWithDefaults)
        assert isinstance(person_attrs, PersonWithDefaults)
        assert person_attrs.name == "Default Person"
        assert person_attrs.age == 18
        assert person_attrs.is_active is True  # default value from attrs class
        assert person_attrs.tags == []  # default factory from attrs class


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_sync_query_service_with_attrs() -> None:
    """Test query service with attrs schema conversion."""
    engine = create_engine("sqlite://")
    attrs_registry.metadata.create_all(engine)

    with Session(engine) as session:
        state_service = USStateSyncService(session=session)
        query_service = SQLAlchemySyncQueryService(session=session)

        # Create test data with dict data
        states_data = [
            {"abbreviation": "CA", "name": "California"},
            {"abbreviation": "TX", "name": "Texas"},
            {"abbreviation": "NY", "name": "New York"},
        ]
        state_service.create_many(states_data)

        # Query and convert to attrs
        query_results, count = query_service.repository.list_and_count(statement=select(StateQuery))
        assert count >= 3

        # Test single item conversion
        single_result = query_service.to_schema(
            data=query_results[0],
            schema_type=StateQueryAttrs,
        )
        assert isinstance(single_result, StateQueryAttrs)
        assert is_attrs_instance(single_result)
        assert hasattr(single_result, "state_abbreviation")
        assert hasattr(single_result, "state_name")

        # Test paginated conversion
        paginated_results = query_service.to_schema(
            data=query_results,
            total=count,
            schema_type=StateQueryAttrs,
        )
        assert len(paginated_results.items) >= 3
        assert all(isinstance(item, StateQueryAttrs) for item in paginated_results.items)
        assert all(is_attrs_instance(item) for item in paginated_results.items)


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
async def test_async_attrs_service_basic_operations() -> None:
    """Test async service operations with attrs classes."""
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(attrs_registry.metadata.create_all)

    async with AsyncSession(engine) as session:
        service = PersonAsyncService(session=session)

        # Test create with dict data
        person_data = {"name": "Async John", "age": 28, "email": "async.john@example.com"}
        created_person = await service.create(person_data)

        assert created_person.name == "Async John"
        assert created_person.age == 28
        assert created_person.email == "async.john@example.com"

        # Test create many with dict data
        people_data = [
            {"name": "Async Jane", "age": 26, "email": "async.jane@example.com"},
            {"name": "Async Bob", "age": 32, "email": "async.bob@example.com"},
        ]
        created_people = await service.create_many(people_data)
        assert len(created_people) == 2

        # Test to_schema conversion to attrs
        person_attrs = service.to_schema(created_person, schema_type=PersonAttrs)
        assert isinstance(person_attrs, PersonAttrs)
        assert is_attrs_instance(person_attrs)
        # Type cast to help pyright understand the specific attrs type
        person_attrs = cast(PersonAttrs, person_attrs)
        assert person_attrs.name == "Async John"
        assert person_attrs.age == 28

        # Test list conversion to attrs
        all_people = await service.list()
        people_paginated = service.to_schema(all_people, schema_type=PersonAttrs)
        assert len(people_paginated.items) == 3
        assert all(isinstance(person, PersonAttrs) for person in people_paginated.items)


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
async def test_async_query_service_with_attrs() -> None:
    """Test async query service with attrs schema conversion."""
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(attrs_registry.metadata.create_all)

    async with AsyncSession(engine) as session:
        state_service = USStateAsyncService(session=session)
        query_service = SQLAlchemyAsyncQueryService(session=session)

        # Create test data with dict data
        states_data = [
            {"abbreviation": "FL", "name": "Florida"},
            {"abbreviation": "WA", "name": "Washington"},
            {"abbreviation": "OR", "name": "Oregon"},
        ]
        await state_service.create_many(states_data)

        # Query and convert to attrs
        query_results, count = await query_service.repository.list_and_count(statement=select(StateQuery))
        assert count >= 3

        # Test single item conversion
        single_result = query_service.to_schema(
            data=query_results[0],
            schema_type=StateQueryAttrs,
        )
        assert isinstance(single_result, StateQueryAttrs)
        assert is_attrs_instance(single_result)

        # Test paginated conversion
        paginated_results = query_service.to_schema(
            data=query_results,
            total=count,
            schema_type=StateQueryAttrs,
        )
        assert len(paginated_results.items) >= 3
        assert all(isinstance(item, StateQueryAttrs) for item in paginated_results.items)


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_attrs_error_handling() -> None:
    """Test error handling with attrs integration."""
    engine = create_engine("sqlite://")
    attrs_registry.metadata.create_all(engine)

    with Session(engine) as session:
        service = PersonSyncService(session=session)

        # Test with invalid attrs-like class (should work with duck typing)
        class FakeAttrsClass:
            def __init__(self, name: str, age: int) -> None:
                self.name = name
                self.age = age

        fake_data = FakeAttrsClass(name="Fake", age=25)

        # This should still work because the service will use __dict__ fallback
        created_person = service.create(fake_data)  # type: ignore[arg-type]
        assert created_person.name == "Fake"
        assert created_person.age == 25


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_attrs_mixed_with_other_schemas() -> None:
    """Test attrs alongside other schema types."""
    engine = create_engine("sqlite://")
    attrs_registry.metadata.create_all(engine)

    with Session(engine) as session:
        service = PersonSyncService(session=session)

        # Create with attrs
        attrs_person = PersonAttrs(name="Attrs Person", age=30)
        created_attrs = service.create(attrs_person)  # type: ignore[arg-type]

        # Create with dict
        dict_person = {"name": "Dict Person", "age": 25, "email": "dict@example.com"}
        created_dict = service.create(dict_person)

        # Both should work
        assert created_attrs.name == "Attrs Person"
        assert created_dict.name == "Dict Person"

        # Convert both to attrs
        attrs_result = service.to_schema(created_attrs, schema_type=PersonAttrs)
        dict_to_attrs_result = service.to_schema(created_dict, schema_type=PersonAttrs)

        assert isinstance(attrs_result, PersonAttrs)
        assert isinstance(dict_to_attrs_result, PersonAttrs)
        assert is_attrs_instance(attrs_result)
        assert is_attrs_instance(dict_to_attrs_result)

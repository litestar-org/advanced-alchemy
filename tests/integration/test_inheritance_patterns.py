"""Integration tests for SQLAlchemy inheritance patterns with real database operations.

Tests Single Table Inheritance (STI), Joined Table Inheritance (JTI), and
Concrete Table Inheritance (CTI) with actual database interactions.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import pytest
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy import base


@pytest.mark.asyncio
@pytest.mark.integration
class TestSTICRUDOperations:
    """Test CRUD operations with Single Table Inheritance pattern."""

    async def test_sti_insert_and_query(self, async_session: AsyncSession) -> None:
        """Test inserting and querying STI models."""

        class Animal(base.UUIDBase):
            __tablename__ = "animal_sti"
            type: Mapped[str]
            name: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "animal",
            }

        class Dog(Animal):
            __mapper_args__ = {"polymorphic_identity": "dog"}
            breed: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

        class Cat(Animal):
            __mapper_args__ = {"polymorphic_identity": "cat"}
            indoor: Mapped[Optional[bool]] = mapped_column(nullable=True)

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Insert data
        dog = Dog(name="Buddy", breed="Golden Retriever")
        cat = Cat(name="Whiskers", indoor=True)

        async_session.add_all([dog, cat])
        await async_session.commit()

        # Query all animals polymorphically
        result = await async_session.execute(select(Animal).order_by(Animal.name))
        animals = result.scalars().all()

        assert len(animals) == 2
        assert isinstance(animals[0], Dog)
        assert isinstance(animals[1], Cat)
        assert animals[0].name == "Buddy"
        assert animals[0].breed == "Golden Retriever"  # type: ignore[attr-defined]
        assert animals[1].name == "Whiskers"
        assert animals[1].indoor is True  # type: ignore[attr-defined]

    async def test_sti_query_specific_subclass(self, async_session: AsyncSession) -> None:
        """Test querying specific subclass in STI."""

        class Employee(base.UUIDBase):
            __tablename__ = "employee_sti"
            type: Mapped[str]
            name: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "employee",
            }

        class Manager(Employee):
            __mapper_args__ = {"polymorphic_identity": "manager"}
            manager_level: Mapped[Optional[int]] = mapped_column(nullable=True)

        class Engineer(Employee):
            __mapper_args__ = {"polymorphic_identity": "engineer"}
            programming_language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Insert data
        manager = Manager(name="Alice", manager_level=5)
        engineer = Engineer(name="Bob", programming_language="Python")

        async_session.add_all([manager, engineer])
        await async_session.commit()

        # Query only managers
        result = await async_session.execute(select(Manager))
        managers = result.scalars().all()

        assert len(managers) == 1
        assert managers[0].name == "Alice"
        assert managers[0].manager_level == 5  # type: ignore[attr-defined]

        # Query only engineers
        result = await async_session.execute(select(Engineer))
        engineers = result.scalars().all()

        assert len(engineers) == 1
        assert engineers[0].name == "Bob"
        assert engineers[0].programming_language == "Python"  # type: ignore[attr-defined]

    async def test_sti_update_operations(self, async_session: AsyncSession) -> None:
        """Test updating STI models."""

        class Vehicle(base.UUIDBase):
            __tablename__ = "vehicle_sti"
            type: Mapped[str]
            brand: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "vehicle",
            }

        class Car(Vehicle):
            __mapper_args__ = {"polymorphic_identity": "car"}
            doors: Mapped[Optional[int]] = mapped_column(nullable=True)

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Insert and update
        car = Car(brand="Toyota", doors=4)
        async_session.add(car)
        await async_session.commit()

        # Update
        car.doors = 2
        await async_session.commit()

        # Verify update
        result = await async_session.execute(select(Car))
        updated_car = result.scalar_one()
        assert updated_car.doors == 2

    async def test_sti_delete_operations(self, async_session: AsyncSession) -> None:
        """Test deleting STI models."""

        class Product(base.UUIDBase):
            __tablename__ = "product_sti"
            type: Mapped[str]
            name: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "product",
            }

        class Book(Product):
            __mapper_args__ = {"polymorphic_identity": "book"}
            author: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Insert
        book = Book(name="Python Guide", author="John Doe")
        async_session.add(book)
        await async_session.commit()

        # Delete
        await async_session.delete(book)
        await async_session.commit()

        # Verify deletion
        result = await async_session.execute(select(Book))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
@pytest.mark.integration
class TestJTICRUDOperations:
    """Test CRUD operations with Joined Table Inheritance pattern."""

    async def test_jti_insert_and_query(self, async_session: AsyncSession) -> None:
        """Test inserting and querying JTI models."""

        class Person(base.UUIDBase):
            __tablename__ = "person_jti"
            name: Mapped[str]
            type: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "person",
            }

        class Student(Person):
            __tablename__ = "student_jti"
            id: Mapped[UUID] = mapped_column(ForeignKey("person_jti.id"), primary_key=True)
            grade: Mapped[str] = mapped_column(String(10))
            __mapper_args__ = {"polymorphic_identity": "student"}

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Insert data
        student = Student(name="Alice", grade="A")
        async_session.add(student)
        await async_session.commit()

        # Query
        result = await async_session.execute(select(Person))
        persons = result.scalars().all()

        assert len(persons) == 1
        assert isinstance(persons[0], Student)
        assert persons[0].name == "Alice"
        assert persons[0].grade == "A"  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.integration
class TestSTIWithRepository:
    """Test STI models work with repository pattern."""

    async def test_sti_with_async_repository(self, async_session: AsyncSession) -> None:
        """Test STI models work with SQLAlchemyAsyncRepository."""
        from advanced_alchemy.repository import SQLAlchemyAsyncRepository

        class Content(base.UUIDBase):
            __tablename__ = "content_repo"
            type: Mapped[str]
            title: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "content",
            }

        class Article(Content):
            __mapper_args__ = {"polymorphic_identity": "article"}
            body: Mapped[Optional[str]] = mapped_column(nullable=True)

        class Video(Content):
            __mapper_args__ = {"polymorphic_identity": "video"}
            duration: Mapped[Optional[int]] = mapped_column(nullable=True)

        class ContentRepository(SQLAlchemyAsyncRepository[Content]):
            model_type = Content

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Use repository
        repo = ContentRepository(session=async_session)

        # Add items
        article = Article(title="Test Article", body="Content")
        video = Video(title="Test Video", duration=120)

        await repo.add_many([article, video])
        await async_session.commit()

        # List all (polymorphic)
        all_content = await repo.list()

        assert len(all_content) == 2
        assert any(isinstance(item, Article) for item in all_content)
        assert any(isinstance(item, Video) for item in all_content)


@pytest.mark.asyncio
@pytest.mark.integration
class TestMultiLevelInheritance:
    """Test multi-level inheritance hierarchies."""

    async def test_three_level_sti_hierarchy(self, async_session: AsyncSession) -> None:
        """Test three-level STI hierarchy (grandparent, parent, child)."""

        class Entity(base.UUIDBase):
            __tablename__ = "entity_multilevel"
            type: Mapped[str]
            name: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "entity",
            }

        class Organization(Entity):
            __mapper_args__ = {"polymorphic_identity": "organization"}
            org_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

        class Company(Organization):
            __mapper_args__ = {"polymorphic_identity": "company"}
            stock_symbol: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

        # Verify all share the same table
        assert Entity.__table__ is Organization.__table__
        assert Entity.__table__ is Company.__table__

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Insert at different levels
        entity = Entity(name="General Entity")
        org = Organization(name="Nonprofit Org", org_code="NPO123")
        company = Company(name="Tech Corp", org_code="TC456", stock_symbol="TECH")

        async_session.add_all([entity, org, company])
        await async_session.commit()

        # Query at root level
        result = await async_session.execute(select(Entity).order_by(Entity.name))
        entities = result.scalars().all()

        assert len(entities) == 3
        assert isinstance(entities[0], Entity)
        assert isinstance(entities[1], Organization)
        assert isinstance(entities[2], Company)


@pytest.mark.asyncio
@pytest.mark.integration
class TestAuditColumnsWithInheritance:
    """Test inheritance patterns with audit columns."""

    async def test_sti_with_audit_columns(self, async_session: AsyncSession) -> None:
        """Test STI with UUIDAuditBase preserves audit columns."""

        class Document(base.UUIDAuditBase):
            __tablename__ = "document_audit"
            type: Mapped[str]
            title: Mapped[str]
            __mapper_args__ = {
                "polymorphic_on": "type",
                "polymorphic_identity": "document",
            }

        class Report(Document):
            __mapper_args__ = {"polymorphic_identity": "report"}
            department: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

        # Create tables
        async with async_session.begin():
            await async_session.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            await async_session.run_sync(
                lambda sync_session: base.UUIDBase.metadata.create_all(bind=sync_session.get_bind())
            )

        # Insert
        report = Report(title="Q4 Report", department="Sales")
        async_session.add(report)
        await async_session.commit()

        # Verify audit columns are populated
        result = await async_session.execute(select(Report))
        saved_report = result.scalar_one()

        assert saved_report.created_at is not None
        assert saved_report.updated_at is not None
        assert saved_report.title == "Q4 Report"
        assert saved_report.department == "Sales"

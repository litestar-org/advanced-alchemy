"""Tests for SQLAlchemy inheritance pattern support.

This module tests all three SQLAlchemy inheritance patterns:
- Single Table Inheritance (STI)
- Joined Table Inheritance (JTI)
- Concrete Table Inheritance (CTI)
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import ForeignKey, MetaData, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy import base

if TYPE_CHECKING:
    pass


# ============================================================================
# Single Table Inheritance (STI) Tests
# ============================================================================


@pytest.mark.integration
def test_sti_basic_table_names() -> None:
    """STI: Child classes use parent table name (auto-generated)."""
    # Create isolated base with unique metadata
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    # No explicit __tablename__ - let CommonTableAttributes generate it
    class STIEmployee(base.CommonTableAttributes, LocalBase):
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        name: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class STIManager(STIEmployee):
        department: Mapped[str | None] = mapped_column(nullable=True)
        __mapper_args__ = {"polymorphic_identity": "manager"}

    class STIEngineer(STIEmployee):
        programming_language: Mapped[str | None] = mapped_column(nullable=True)
        __mapper_args__ = {"polymorphic_identity": "engineer"}

    # Verify all use same table (auto-generated from parent class name)
    expected_name = "sti_employee"  # snake_case of STIEmployee
    assert STIEmployee.__table__.name == expected_name
    assert STIManager.__table__.name == expected_name
    assert STIEngineer.__table__.name == expected_name
    assert STIManager.__table__ is STIEmployee.__table__  # Same table object


@pytest.mark.integration
def test_sti_table_columns() -> None:
    """STI: Single table contains all columns from hierarchy."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "sti_employee_cols"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        name: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        department: Mapped[str | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "manager"}

    class Engineer(Employee):
        programming_language: Mapped[str | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "engineer"}

    # Verify columns exist in single table
    columns = {col.name for col in Employee.__table__.columns}
    assert "type" in columns
    assert "name" in columns
    assert "department" in columns
    assert "programming_language" in columns


@pytest.mark.integration
def test_sti_multi_level() -> None:
    """STI: Three levels of inheritance share one table."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "sti_employee_ml"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        department: Mapped[str | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "manager"}

    class SeniorManager(Manager):
        budget: Mapped[int | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "senior_manager"}

    # All three levels use same table
    assert Employee.__table__.name == "sti_employee_ml"
    assert Manager.__table__.name == "sti_employee_ml"
    assert SeniorManager.__table__.name == "sti_employee_ml"


@pytest.mark.integration
@pytest.mark.sqlite
def test_sti_crud_operations(session: Session, sqlite_engine: Any) -> None:
    """STI: CRUD operations work correctly with polymorphic models."""
    from sqlalchemy.orm import Session as SessionType

    # Create fresh metadata and registry for this test
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "sti_employee_crud"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        name: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        department: Mapped[str | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "manager"}

    class Engineer(Employee):
        programming_language: Mapped[str | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "engineer"}

    # Create tables
    test_metadata.create_all(sqlite_engine)

    try:
        with SessionType(sqlite_engine) as test_session:
            # Create instances
            manager = Manager(name="Alice", department="Engineering", type="manager")
            engineer = Engineer(name="Bob", programming_language="Python", type="engineer")
            employee = Employee(name="Charlie", type="employee")

            test_session.add_all([manager, engineer, employee])
            test_session.commit()

            # Query all employees
            all_employees = test_session.execute(select(Employee)).scalars().all()
            assert len(all_employees) == 3

            # Query specific type
            managers = test_session.execute(select(Manager)).scalars().all()
            assert len(managers) == 1
            assert isinstance(managers[0], Manager)
            assert managers[0].department == "Engineering"

            # Polymorphic identity check
            retrieved_manager = test_session.execute(select(Employee).where(Employee.name == "Alice")).scalar_one()
            assert isinstance(retrieved_manager, Manager)
            assert retrieved_manager.department == "Engineering"
    finally:
        test_metadata.drop_all(sqlite_engine)


# ============================================================================
# Joined Table Inheritance (JTI) Tests
# ============================================================================


@pytest.mark.integration
def test_jti_basic() -> None:
    """JTI: Child has separate table with foreign key."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "jti_employee"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        name: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        __tablename__ = "jti_manager"
        id: Mapped[int] = mapped_column(ForeignKey("jti_employee.id"), primary_key=True)
        department: Mapped[str]
        __mapper_args__ = {"polymorphic_identity": "manager"}

    # Verify separate tables
    assert Employee.__table__.name == "jti_employee"
    assert Manager.__table__.name == "jti_manager"

    # Verify foreign key relationship
    fk_columns = [fk.parent.name for fk in Manager.__table__.foreign_keys]
    assert "id" in fk_columns


@pytest.mark.integration
def test_jti_multiple_children() -> None:
    """JTI: Multiple children each with own table."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "jti_employee_multi"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        __tablename__ = "jti_manager_multi"
        id: Mapped[int] = mapped_column(ForeignKey("jti_employee_multi.id"), primary_key=True)
        department: Mapped[str]
        __mapper_args__ = {"polymorphic_identity": "manager"}

    class Engineer(Employee):
        __tablename__ = "jti_engineer_multi"
        id: Mapped[int] = mapped_column(ForeignKey("jti_employee_multi.id"), primary_key=True)
        language: Mapped[str]
        __mapper_args__ = {"polymorphic_identity": "engineer"}

    # Three separate tables
    assert Employee.__table__.name == "jti_employee_multi"
    assert Manager.__table__.name == "jti_manager_multi"
    assert Engineer.__table__.name == "jti_engineer_multi"


@pytest.mark.integration
@pytest.mark.sqlite
def test_jti_crud_operations(session: Session, sqlite_engine: Any) -> None:
    """JTI: CRUD operations with joined tables."""
    from sqlalchemy.orm import Session as SessionType

    # Create fresh metadata for this test
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "jti_employee_crud"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        name: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        __tablename__ = "jti_manager_crud"
        id: Mapped[int] = mapped_column(ForeignKey("jti_employee_crud.id"), primary_key=True)
        department: Mapped[str]
        __mapper_args__ = {"polymorphic_identity": "manager"}

    # Create tables
    test_metadata.create_all(sqlite_engine)

    try:
        with SessionType(sqlite_engine) as test_session:
            # Create instance
            manager = Manager(name="Alice", department="Engineering", type="manager")
            test_session.add(manager)
            test_session.commit()

            # Query
            retrieved = test_session.execute(select(Manager)).scalar_one()
            assert retrieved.name == "Alice"
            assert retrieved.department == "Engineering"

            # Query as base class
            as_employee = test_session.execute(select(Employee).where(Employee.name == "Alice")).scalar_one()
            assert isinstance(as_employee, Manager)
    finally:
        test_metadata.drop_all(sqlite_engine)


# ============================================================================
# Concrete Table Inheritance (CTI) Tests
# ============================================================================


@pytest.mark.integration
def test_cti_basic() -> None:
    """CTI: Child has independent table (no foreign key)."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "cti_employee"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]

    class Manager(Employee):
        __tablename__ = "cti_manager"
        id: Mapped[int] = mapped_column(primary_key=True)
        department: Mapped[str]
        __mapper_args__ = {"concrete": True}

    # Separate independent tables
    assert Employee.__table__.name == "cti_employee"
    assert Manager.__table__.name == "cti_manager"

    # No foreign keys
    assert len(list(Manager.__table__.foreign_keys)) == 0


@pytest.mark.integration
def test_cti_multiple_concrete_classes() -> None:
    """CTI: Multiple concrete subclasses with independent tables."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "cti_employee_multi"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]

    class Manager(Employee):
        __tablename__ = "cti_manager_multi"
        id: Mapped[int] = mapped_column(primary_key=True)
        department: Mapped[str]
        __mapper_args__ = {"concrete": True}

    class Engineer(Employee):
        __tablename__ = "cti_engineer_multi"
        id: Mapped[int] = mapped_column(primary_key=True)
        language: Mapped[str]
        __mapper_args__ = {"concrete": True}

    # All have independent tables
    assert Employee.__table__.name == "cti_employee_multi"
    assert Manager.__table__.name == "cti_manager_multi"
    assert Engineer.__table__.name == "cti_engineer_multi"

    # No foreign keys
    assert len(list(Manager.__table__.foreign_keys)) == 0
    assert len(list(Engineer.__table__.foreign_keys)) == 0


@pytest.mark.integration
@pytest.mark.sqlite
def test_cti_crud_operations(session: Session, sqlite_engine: Any) -> None:
    """CTI: CRUD operations with concrete tables."""
    from sqlalchemy.orm import Session as SessionType

    # Create fresh metadata for this test
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "cti_employee_crud"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]

    class Manager(Employee):
        __tablename__ = "cti_manager_crud"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]  # Must redeclare inherited columns for CTI
        department: Mapped[str]
        __mapper_args__ = {"concrete": True}

    # Create tables
    test_metadata.create_all(sqlite_engine)

    try:
        with SessionType(sqlite_engine) as test_session:
            # Create instance
            manager = Manager(name="Alice", department="Engineering")
            test_session.add(manager)
            test_session.commit()

            # Query
            retrieved = test_session.execute(select(Manager)).scalar_one()
            assert retrieved.name == "Alice"
            assert retrieved.department == "Engineering"
    finally:
        test_metadata.drop_all(sqlite_engine)


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.integration
def test_explicit_tablename_override() -> None:
    """Explicit __tablename__ always respected."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "employee_explicit"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        __tablename__ = "manager_explicit_override"  # Explicit override
        id: Mapped[int] = mapped_column(ForeignKey("employee_explicit.id"), primary_key=True)
        department: Mapped[str]
        __mapper_args__ = {"polymorphic_identity": "manager"}

    # Explicit tablename used (JTI pattern)
    assert Manager.__table__.name == "manager_explicit_override"


@pytest.mark.integration
def test_mixin_with_inheritance() -> None:
    """Mixins don't break inheritance detection."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class TimestampMixin:
        created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.now)

    class Employee(TimestampMixin, base.CommonTableAttributes, LocalBase):
        __tablename__ = "employee_mixin"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        department: Mapped[str | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "manager"}

    # STI works despite mixin
    assert Manager.__table__.name == "employee_mixin"


@pytest.mark.integration
def test_abstract_base_class() -> None:
    """Abstract base classes handled correctly."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class BaseEntity(base.CommonTableAttributes, LocalBase):
        __abstract__ = True
        created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.now)

    class Employee(BaseEntity):
        __tablename__ = "employee_abstract"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]

    # Abstract base doesn't create table
    assert not hasattr(BaseEntity, "__table__")
    assert Employee.__table__.name == "employee_abstract"


@pytest.mark.integration
def test_no_inheritance_generates_tablename() -> None:
    """Classes without inheritance get auto-generated tablename."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class StandaloneModel(base.CommonTableAttributes, LocalBase):
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]

    # Auto-generated from class name
    assert StandaloneModel.__table__.name == "standalone_model"


@pytest.mark.integration
def test_sti_without_polymorphic_identity_on_child() -> None:
    """STI child without explicit polymorphic_identity still uses parent table."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "employee_no_poly_id"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        department: Mapped[str | None] = mapped_column(default=None)
        # No __mapper_args__ - should still detect STI from parent

    # Should use parent table even without explicit polymorphic_identity
    assert Manager.__table__.name == "employee_no_poly_id"


@pytest.mark.integration
def test_backward_compatibility_simple_models() -> None:
    """Existing simple models without inheritance work as before."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class User(base.CommonTableAttributes, LocalBase):
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]
        email: Mapped[str]

    class Product(base.CommonTableAttributes, LocalBase):
        id: Mapped[int] = mapped_column(primary_key=True)
        title: Mapped[str]
        price: Mapped[int]

    # Auto-generated tablenames still work
    assert User.__table__.name == "user"
    assert Product.__table__.name == "product"


@pytest.mark.integration
def test_sti_with_multiple_inheritance_levels() -> None:
    """Multi-level STI inheritance hierarchy."""
    test_metadata = MetaData()

    class LocalBase(DeclarativeBase):
        metadata = test_metadata

    class Employee(base.CommonTableAttributes, LocalBase):
        __tablename__ = "employee_deep"
        id: Mapped[int] = mapped_column(primary_key=True)
        type: Mapped[str]
        __mapper_args__ = {"polymorphic_on": "type", "polymorphic_identity": "employee"}

    class Manager(Employee):
        level: Mapped[int | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "manager"}

    class SeniorManager(Manager):
        budget: Mapped[int | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "senior_manager"}

    class ExecutiveManager(SeniorManager):
        bonus: Mapped[int | None] = mapped_column(default=None)
        __mapper_args__ = {"polymorphic_identity": "executive_manager"}

    # All levels use same table
    assert Employee.__table__.name == "employee_deep"
    assert Manager.__table__.name == "employee_deep"
    assert SeniorManager.__table__.name == "employee_deep"
    assert ExecutiveManager.__table__.name == "employee_deep"

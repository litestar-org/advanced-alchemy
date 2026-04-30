====================
Inheritance Patterns
====================

Advanced Alchemy provides robust support for SQLAlchemy's inheritance patterns, ensuring that mixins and common attributes are correctly applied across the hierarchy.

Common Table Attributes
-----------------------

When using inheritance, it is recommended to use the ``CommonTableAttributes`` mixin. This ensures that table names are correctly generated and that shared attributes (like primary keys or audit columns) are inherited properly.

.. code-block:: python

    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
    from advanced_alchemy.base import CommonTableAttributes, orm_registry

    class Base(CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

Single Table Inheritance (STI)
------------------------------

In STI, multiple classes are mapped to a single table. A "discriminator" column is used to determine which class a particular row represents.

.. code-block:: python

    from typing import Optional
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDAuditBase

    class Employee(UUIDAuditBase):
        __tablename__ = "employee"
        name: Mapped[str]
        type: Mapped[str]

        __mapper_args__ = {
            "polymorphic_on": "type",
            "polymorphic_identity": "employee",
        }

    class Manager(Employee):
        __mapper_args__ = {
            "polymorphic_identity": "manager",
        }
        manager_data: Mapped[Optional[str]]

    class Engineer(Employee):
        __mapper_args__ = {
            "polymorphic_identity": "engineer",
        }
        engineer_info: Mapped[Optional[str]]

Joined Table Inheritance (JTI)
------------------------------

In JTI, each class in the hierarchy is mapped to its own table. Sub-tables contain only the columns specific to that class and a foreign key to the parent table.

.. code-block:: python

    from uuid import UUID

    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDAuditBase

    class Person(UUIDAuditBase):
        __tablename__ = "person"
        name: Mapped[str]
        type: Mapped[str]

        __mapper_args__ = {
            "polymorphic_on": "type",
            "polymorphic_identity": "person",
        }

    class Staff(Person):
        __tablename__ = "staff"
        id: Mapped[UUID] = mapped_column(ForeignKey("person.id"), primary_key=True)
        staff_no: Mapped[str]

        __mapper_args__ = {
            "polymorphic_identity": "staff",
        }

Concrete Table Inheritance (CTI)
--------------------------------

In CTI, each class is mapped to a completely independent table containing all columns for that class.

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDAuditBase

    class Vehicle(UUIDAuditBase):
        __abstract__ = True
        name: Mapped[str]

    class Car(Vehicle):
        __tablename__ = "car"
        engine_type: Mapped[str]

    class Bicycle(Vehicle):
        __tablename__ = "bicycle"
        has_basket: Mapped[bool]

Repository Usage with Inheritance
---------------------------------

Advanced Alchemy's repositories work seamlessly with inheritance. You can create a repository for the base class to query across all types, or for a specific subclass.

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    class EmployeeRepository(SQLAlchemyAsyncRepository[Employee]):
        model_type = Employee

    async def list_employees(db_session: AsyncSession) -> list[Employee]:
        repository = EmployeeRepository(session=db_session)
        return await repository.get_many()

    class ManagerRepository(SQLAlchemyAsyncRepository[Manager]):
        model_type = Manager

    async def list_managers(db_session: AsyncSession) -> list[Manager]:
        repository = ManagerRepository(session=db_session)
        return await repository.get_many()

====================
Inheritance Patterns
====================

Advanced Alchemy's declarative base classes and repositories support all three SQLAlchemy inheritance strategies:

* **Single Table**: Subclasses share one table distinguished by a discriminator column (``polymorphic_on``). Suitable when subclasses add only a few nullable columns.
* **Joined Table**: Shared columns reside in a parent table and subtype-specific columns reside in child tables joined by a foreign key.
* **Concrete Table**: An abstract Python base class (``__abstract__ = True``) shares column definitions while each subclass maps to an independent table.

Comparing the Layouts
---------------------

.. tab-set::

    .. tab-item:: Single Table

        .. code-block:: python

            from typing import Optional
            from sqlalchemy.orm import Mapped
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
                __mapper_args__ = {"polymorphic_identity": "manager"}
                department: Mapped[Optional[str]]


            class Engineer(Employee):
                __mapper_args__ = {"polymorphic_identity": "engineer"}
                primary_language: Mapped[Optional[str]]

    .. tab-item:: Joined Table

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
                badge_number: Mapped[str]

                __mapper_args__ = {"polymorphic_identity": "staff"}

    .. tab-item:: Concrete Table

        .. code-block:: python

            from sqlalchemy.orm import Mapped
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

Querying Inherited Models
-------------------------

Bind a repository to the parent model to query across all polymorphic subtypes, or bind a repository to a specific subclass to query only that subtype:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository


    class EmployeeRepository(SQLAlchemyAsyncRepository[Employee]):
        model_type = Employee


    class ManagerRepository(SQLAlchemyAsyncRepository[Manager]):
        model_type = Manager


    async def list_staff(db_session: AsyncSession) -> tuple[list[Employee], list[Manager]]:
        all_employees = await EmployeeRepository(session=db_session).get_many()
        only_managers = await ManagerRepository(session=db_session).get_many()
        return all_employees, only_managers

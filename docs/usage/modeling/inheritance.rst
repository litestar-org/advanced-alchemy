====================
Inheritance Patterns
====================

Sometimes several models share most of their fields—for example, **Managers** and **Engineers** are both **Employees**, or **Articles** and **Videos** are both **Posts**.

SQLAlchemy supports three ways to lay out shared models in the database, and Advanced Alchemy's base classes and repositories work with all three:

* **Single Table**: Everything lives in **one table** with a ``type`` column. Fastest to query when subclasses only add a few optional columns.
* **Joined Table**: Shared fields live in a **parent table**, and extra fields live in **child tables** linked by a foreign key. Best when subclasses have many required columns.
* **Concrete Table**: An abstract Python base class shares column definitions, while each subclass gets its own **separate table**.

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

Attach a repository to the parent model when you want all subtypes back together, or attach one to a child model when you only want rows of that specific subtype:

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

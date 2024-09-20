Using Base Models
=================

Advanced Alchemy provides base models that you can use to create your database models. Two commonly used base models are ``UUIDBase`` and ``BigIntBase``. This guide will illustrate how to use these base models to create your own database models and how to apply migrations using Litestar's built-in commands.

UUIDBase
--------

The ``UUIDBase`` model uses a UUID as the primary key. This is useful when you want a globally unique identifier for your records.

Here's an example of how to use ``UUIDBase``:

.. code-block:: python

    from uuid import UUID
    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase

    class User(UUIDBase):
        __tablename__ = "users"

        name: Mapped[str] = mapped_column(String(length=100))
        email: Mapped[str] = mapped_column(String(length=100), unique=True)

In this example, the ``User`` model inherits from ``UUIDBase``. It will automatically have a ``id`` column of type ``UUID`` as its primary key.

BigIntBase
----------

The ``BigIntBase`` model uses a big integer as the primary key. This is useful when you need a large range of unique identifiers.

Here's an example of how to use ``BigIntBase``:

.. code-block:: python

    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase

    class Product(BigIntBase):
        __tablename__ = "products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[str] = mapped_column(String(length=500))
        price: Mapped[float]

In this example, the ``Product`` model inherits from ``BigIntBase``. It will automatically have an ``id`` column of type ``BigInteger`` as its primary key.

Using These Models
------------------

Once you've defined your models, you can use them to create, read, update, and delete records in your database. Here's a brief example:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    async def create_user(session: AsyncSession, name: str, email: str) -> User:
        user_repo = SQLAlchemyAsyncRepository(model_type=User, session=session)
        user = User(name=name, email=email)
        return await user_repo.add(user)

    async def get_product(session: AsyncSession, product_id: int) -> Product | None:
        product_repo = SQLAlchemyAsyncRepository(model_type=Product, session=session)
        return await product_repo.get(product_id)

These examples demonstrate how to create a new user and retrieve a product using the repositories provided by Advanced Alchemy.

Applying Migrations
-------------------

Advanced Alchemy offers built-in commands for Litestar to apply database migrations. After you've defined your models and created your migration scripts, you can apply the migrations by running:

.. code-block:: bash

    litestar database upgrade

This command will apply any pending migrations to your database, ensuring that your database schema matches your defined models.

Remember to adjust your database configuration and session management according to your specific setup and requirements. Also, make sure you have set up your Litestar application correctly to use Advanced Alchemy's database commands.


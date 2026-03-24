=====================
SQLModel Integration
=====================

Advanced Alchemy provides built-in compatibility for `SQLModel <https://sqlmodel.tiangolo.com/>`_, allowing you to use SQLModel's elegant syntax for defining models while leveraging Advanced Alchemy's powerful repositories and services.

Basic Setup
-----------

To use SQLModel with Advanced Alchemy, ensure your models are defined with ``table=True``.

.. code-block:: python

    from typing import Optional
    from sqlmodel import Field, SQLModel
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    class Hero(SQLModel, table=True):
        id: Optional[int] = Field(default=None, primary_key=True)
        name: str
        secret_name: str
        age: Optional[int] = None

    class HeroRepository(SQLAlchemyAsyncRepository[Hero]):
        model_type = Hero

Usage with Repositories
-----------------------

Repositories automatically detect SQLModel classes and handle them correctly during CRUD operations.

.. code-block:: python

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_factory = sessionmaker(engine, class_=AsyncSession)

    async with async_session_factory() as session:
        repo = HeroRepository(session=session)

        # Create
        hero = Hero(name="Deadpond", secret_name="Dive Wilson")
        await repo.add(hero)
        await session.commit()

        # List
        heroes = await repo.list()

Limitations
-----------

While SQLModel is supported, some Advanced Alchemy features that rely on specific SQLAlchemy base class behaviors (like some automated mixin detections) may require explicit configuration when used with SQLModel.

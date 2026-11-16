====================
SQLModel Integration
====================

`SQLModel <https://sqlmodel.tiangolo.com/>`_ classes configured with ``table=True`` work directly with Advanced Alchemy repositories and services.

Defining and Querying a SQLModel Table
--------------------------------------

Mark your SQLModel class with ``table=True`` and point a repository at it just like any SQLAlchemy model:

.. code-block:: python

    from typing import Optional
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlmodel import Field, SQLModel
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository


    class Hero(SQLModel, table=True):
        id: Optional[int] = Field(default=None, primary_key=True)
        name: str
        secret_name: str
        age: Optional[int] = None


    class HeroRepository(SQLAlchemyAsyncRepository[Hero]):
        model_type = Hero


    async def create_and_list_heroes() -> list[Hero]:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        try:
            async with session_factory() as session:
                repo = HeroRepository(session=session)
                await repo.add(Hero(name="Spider-Man", secret_name="Peter Parker"))
                await session.commit()
                return await repo.get_many()
        finally:
            await engine.dispose()

Metadata Configuration
----------------------

SQLModel registers tables on ``SQLModel.metadata`` rather than Advanced Alchemy's ``orm_registry.metadata``. Pass ``metadata=SQLModel.metadata`` to ``SQLAlchemyAsyncConfig`` or ``SQLAlchemySyncConfig`` so Alembic migrations and ``create_all`` target your SQLModel tables.

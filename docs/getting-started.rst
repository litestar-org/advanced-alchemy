===============
Getting Started
===============

A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy 2.0+:

* **Models**: Declarative base classes with UUID, NanoID, or integer primary keys, ``created_at`` and ``updated_at`` audit timestamps, and portable custom column types.
* **Repositories**: Synchronous and asynchronous ``add``, ``get``, ``get_many_and_count``, ``upsert``, filtering, and bulk operations for SQLAlchemy models.
* **Services**: Typed service wrappers converting between ORM models and Pydantic, Msgspec, dataclass, ``attrs``, or SQLModel schemas.
* **Framework plugins**: Engine lifecycle management, per-request sessions, dependency injection providers, and migration CLIs.

Installation
------------

Install ``advanced-alchemy`` with your preferred package manager and database/framework extras (such as ``asyncpg``, ``psycopg``, ``aiosqlite``, ``litestar``, or ``fastapi``):

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[aiosqlite]"

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[aiosqlite]"

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[aiosqlite]"

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[aiosqlite]"

Your First Model and Repository
-------------------------------

Define a ``BlogPost`` model using ``UUIDAuditBase`` (which provides a UUID ``id`` column along with ``created_at`` and ``updated_at`` timestamps) and attach an async repository to persist and query rows:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped
    from advanced_alchemy.base import UUIDAuditBase
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository


    class BlogPost(UUIDAuditBase):
        __tablename__ = "quickstart_post"

        title: Mapped[str]
        published: Mapped[bool] = False


    class BlogPostRepository(SQLAlchemyAsyncRepository[BlogPost]):
        model_type = BlogPost


    async def run_demo(db_session: AsyncSession) -> None:
        conn = await db_session.connection()
        await conn.run_sync(UUIDAuditBase.metadata.create_all)

        repo = BlogPostRepository(session=db_session)
        await repo.add(BlogPost(title="Hello Advanced Alchemy", published=True))
        await db_session.commit()

        posts, total = await repo.get_many_and_count(published=True)
        assert total == 1
        assert posts[0].title == "Hello Advanced Alchemy"

Where to Go Next
----------------

* :doc:`Usage Guide <usage/index>`: Models, repositories, services, caching, replica routing, CLI commands, and fixture seeding.
* :doc:`Framework Integrations <usage/frameworks/index>`: Integrate Advanced Alchemy with Litestar, FastAPI, Starlette, Flask, or Sanic.
* `Discord Community <https://discord.gg/dSDXd4mKhp>`_: Ask questions and discuss with maintainers.

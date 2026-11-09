===============
Getting Started
===============

When you build an app with SQLAlchemy from scratch, you end up writing the same plumbing over and over: ID and timestamp columns on every table, ``select()`` and pagination queries in every endpoint, and session cleanup code for every web request.

Advanced Alchemy handles that repetitive plumbing while keeping plain SQLAlchemy 2.0 front and center:

* **Models** come with ready-made IDs, ``created_at`` / ``updated_at`` timestamps, and portable column types.
* **Repositories** give every model ``add``, ``get``, ``list_and_count``, ``upsert``, and ``delete`` methods out of the box.
* **Services** connect your repositories to Pydantic, Msgspec, or dataclass API schemas.
* **Framework plugins** manage database engines and per-request sessions automatically.

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

Imagine you are building a small blog. Define a ``BlogPost`` table using ``UUIDAuditBase`` (which automatically adds a UUID ``id`` plus ``created_at`` and ``updated_at`` columns) and attach a repository to save and query posts:

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

        posts, total = await repo.list_and_count(published=True)
        assert total == 1
        assert posts[0].title == "Hello Advanced Alchemy"

Where to Go Next
----------------

* :doc:`Usage Guide <usage/index>` — Walk through models, repositories, services, caching, and read-replica routing step by step.
* :doc:`Framework Integrations <usage/frameworks/index>` — Plug Advanced Alchemy into Litestar, FastAPI, Starlette, Flask, or Sanic.
* `Discord Community <https://discord.gg/dSDXd4mKhp>`_ — Ask questions and get help from the maintainers.

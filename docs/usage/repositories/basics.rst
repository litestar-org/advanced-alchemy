===================
Repository Basics
===================

Advanced Alchemy's repository pattern provides a consistent, type-safe interface for database operations that abstracts SQLAlchemy session and query construction.

Base Repository Types
---------------------

.. list-table:: Repository Types
   :header-rows: 1
   :widths: 35 65

   * - Repository Class
     - Features
   * - :class:`~advanced_alchemy.repository.SQLAlchemyAsyncRepository`
     - Async session support, CRUD, filtering, pagination, and bulk operations.
   * - :class:`~advanced_alchemy.repository.SQLAlchemyAsyncSlugRepository`
     - Base async repository features plus slug generation and lookup helpers.
   * - :class:`~advanced_alchemy.repository.SQLAlchemyAsyncQueryRepository`
     - Arbitrary SQLAlchemy ``Select`` execution and aggregations.
   * - :class:`~advanced_alchemy.repository.SQLAlchemySyncRepository`
     - Synchronous counterpart of the base repository.
   * - :class:`~advanced_alchemy.repository.SQLAlchemySyncSlugRepository`
     - Synchronous counterpart of the slug repository.
   * - :class:`~advanced_alchemy.repository.SQLAlchemySyncQueryRepository`
     - Synchronous counterpart of the query repository.

Basic Usage
-----------

Define your SQLAlchemy models and bind a repository subclass via ``model_type``:

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.mixins import SlugKey
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped, mapped_column


    class Post(BigIntAuditBase):
        __tablename__ = "repo_basics_post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)


    class Tag(BigIntAuditBase, SlugKey):
        __tablename__ = "repo_basics_tag"

        name: Mapped[str]


    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        """Repository for managing blog posts."""

        model_type = Post


    async def create_post(db_session: AsyncSession, title: str, content: str) -> Post:
        repository = PostRepository(session=db_session)
        return await repository.add(Post(title=title, content=content), auto_commit=True)

Bulk Operations
---------------

Repositories support efficient bulk operations for adding, updating, deleting, and upserting multiple records.

Add, Update, and Delete Many
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from collections.abc import Sequence
    from sqlalchemy.ext.asyncio import AsyncSession


    async def create_posts(db_session: AsyncSession, data: list[tuple[str, str]]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)
        return await repository.add_many(
            [Post(title=title, content=content) for title, content in data],
            auto_commit=True,
        )


    async def publish_posts(db_session: AsyncSession, post_ids: list[int]) -> list[Post]:
        repository = PostRepository(session=db_session)
        posts = await repository.get_many(Post.id.in_(post_ids), published=False)
        for post in posts:
            post.published = True
        return await repository.update_many(posts)


    async def delete_posts(db_session: AsyncSession, post_ids: list[int]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)
        return await repository.delete_many(post_ids)

Upsert Many
~~~~~~~~~~~

``upsert_many`` dispatches to the native upsert primitive supported by the active dialect when ``match_fields`` maps to a provably unique key (primary key, unique constraint, or unique index). Otherwise, it falls back to ``SELECT`` followed by ``add_many`` and ``update_many``.

.. list-table:: Per-Dialect Upsert Primitives
   :header-rows: 1
   :widths: 22 38 12 28

   * - Dialect
     - Native Statement
     - RETURNING
     - Hydration Path
   * - ``postgresql``, ``cockroachdb``
     - ``INSERT … ON CONFLICT DO UPDATE``
     - Yes
     - Cursor rows via ``.returning(model_type)``
   * - ``sqlite``, ``duckdb``
     - ``INSERT … ON CONFLICT DO UPDATE``
     - Yes
     - Cursor rows via ``.returning(model_type)``
   * - ``mysql``, ``mariadb``
     - ``INSERT … ON DUPLICATE KEY UPDATE``
     - No
     - Re-SELECT on ``match_fields``
   * - ``oracle``
     - ``MERGE INTO … USING (SELECT … FROM DUAL UNION ALL …)``
     - No
     - Re-SELECT on ``match_fields``
   * - ``mssql``
     - ``MERGE INTO … USING (VALUES (…)) AS src(…)``
     - No
     - Re-SELECT on ``match_fields``
   * - ``spanner+spanner``
     - ``INSERT OR UPDATE INTO … (…) VALUES (…)``
     - Yes
     - Cursor rows via ``.returning(model_type)``
   * - Other dialects
     - Fallback: ``SELECT`` + ``add_many`` + ``update_many``
     - N/A
     - SQLAlchemy ORM identity map

Key dispatch rules:

- **Uniqueness safety gate**: Native upsert executes only when ``match_fields`` is provably unique; non-unique keys, deferrable constraints, partial/expression indexes, multi-unique-key MySQL tables, and non-PK Spanner ``match_fields`` use the fallback path.
- **Deterministic batches**: Duplicate conflict keys in one batch are rejected before execution, and heterogeneous explicit column sets or missing server-generated PK values on ``MERGE`` / Spanner paths fall back to ORM partitioning.
- **Execution controls**: Pass ``no_merge=True`` to force the fallback path or ``chunk_size`` to cap parameters per statement.

.. code-block:: python

    from collections.abc import Sequence
    from sqlalchemy.ext.asyncio import AsyncSession


    async def upsert_posts(db_session: AsyncSession, posts: list[Post]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)
        return await repository.upsert_many(
            posts,
            match_fields=["id"],
            chunk_size=500,
        )

Specialized Repositories
------------------------

For models using :class:`~advanced_alchemy.mixins.SlugKey`, :class:`~advanced_alchemy.repository.SQLAlchemyAsyncSlugRepository` adds ``get_by_slug`` and ``get_available_slug``. For custom ``Select`` queries and aggregations, use :class:`~advanced_alchemy.repository.SQLAlchemyAsyncQueryRepository`:

.. code-block:: python

    from typing import Any

    from advanced_alchemy.repository import (
        SQLAlchemyAsyncQueryRepository,
        SQLAlchemyAsyncSlugRepository,
    )
    from sqlalchemy import Row, func, select
    from sqlalchemy.ext.asyncio import AsyncSession


    class TagRepository(SQLAlchemyAsyncSlugRepository[Tag]):
        model_type = Tag


    async def get_tag_by_slug(db_session: AsyncSession, slug: str) -> Tag:
        repository = TagRepository(session=db_session)
        return await repository.get_by_slug(slug)


    async def get_posts_count_by_status(db_session: AsyncSession) -> list[Row[Any]]:
        repository = SQLAlchemyAsyncQueryRepository(session=db_session)
        return await repository.get_many(
            select(Post.published, func.count(Post.id)).group_by(Post.published)
        )

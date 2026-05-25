===================
Repository Basics
===================

Advanced Alchemy's repository pattern provides a clean, consistent interface for database operations.
This pattern abstracts away the complexity of SQLAlchemy sessions and query-building while providing
type-safe operations.

Understanding Repositories
--------------------------

A repository acts as a collection-like interface to your database models, providing:

- Type-safe CRUD operations
- Filtering and pagination
- Bulk operations
- Transaction management
- Specialized repository types for common patterns

Base Repository Types
---------------------

.. list-table:: Repository Types
   :header-rows: 1
   :widths: 30 70

   * - Repository Class
     - Features
   * - ``SQLAlchemyAsyncRepository``
     - Async session support, basic CRUD, filtering, and bulk operations.
   * - ``SQLAlchemyAsyncSlugRepository``
     - All base features plus slug-based lookups.
   * - ``SQLAlchemyAsyncQueryRepository``
     - Custom query execution and complex aggregations.
   * - ``SQLAlchemySyncRepository``
     - Synchronous version of the base repository.
   * - ``SQLAlchemySyncSlugRepository``
     - Synchronous version of the slug repository.
   * - ``SQLAlchemySyncQueryRepository``
     - Synchronous version of the query repository.

Basic Usage
-----------

Let's implement a basic repository for a blog post model:

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.mixins import SlugKey
    from sqlalchemy.orm import Mapped, mapped_column

    class Post(BigIntAuditBase):
        __tablename__ = "post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)

    class Tag(BigIntAuditBase, SlugKey):
        __tablename__ = "tag"

        name: Mapped[str]

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from sqlalchemy.ext.asyncio import AsyncSession

    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        """Repository for managing blog posts."""
        model_type = Post

    async def create_post(db_session: AsyncSession, title: str, content: str) -> Post:
        repository = PostRepository(session=db_session)
        return await repository.add(Post(title=title, content=content), auto_commit=True)

Bulk Operations
---------------

Repositories support efficient bulk operations for adding, updating, and deleting multiple records.

Add Many
~~~~~~~~

.. code-block:: python

    from collections.abc import Sequence
    from sqlalchemy.ext.asyncio import AsyncSession

    async def create_posts(db_session: AsyncSession, data: list[tuple[str, str]]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)
        return await repository.add_many(
            [Post(title=title, content=content) for title, content in data],
            auto_commit=True,
        )

Update Many
~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

    async def publish_posts(db_session: AsyncSession, post_ids: list[int]) -> list[Post]:
        repository = PostRepository(session=db_session)
        posts = await repository.get_many(Post.id.in_(post_ids), published=False)

        for post in posts:
            post.published = True

        return await repository.update_many(posts)

Delete Many
~~~~~~~~~~~

.. code-block:: python

    from collections.abc import Sequence
    from sqlalchemy.ext.asyncio import AsyncSession

    async def delete_posts(db_session: AsyncSession, post_ids: list[int]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)
        return await repository.delete_many(post_ids)

Upsert Many
~~~~~~~~~~~

``upsert_many`` automatically dispatches to the most efficient native upsert
primitive supported by the active dialect. When ``match_fields`` maps to a
primary key, unique constraint, or unique index, a single dialect-native
statement per chunk is issued. Otherwise the repository falls back to the
historical SELECT-then-partition-then-add/update path.

Dispatch matrix:

.. list-table:: Per-dialect upsert primitive
   :header-rows: 1
   :widths: 22 38 12 28

   * - Dialect
     - Native statement
     - RETURNING
     - Hydration path
   * - ``postgresql``, ``cockroachdb``
     - ``INSERT … ON CONFLICT DO UPDATE``
     - Yes
     - cursor rows via ``.returning(model_type)``
   * - ``sqlite``, ``duckdb``
     - ``INSERT … ON CONFLICT DO UPDATE``
     - Yes
     - cursor rows via ``.returning(model_type)``
   * - ``mysql``, ``mariadb``
     - ``INSERT … ON DUPLICATE KEY UPDATE``
     - No
     - re-SELECT on ``match_fields``
   * - ``oracle``
     - ``MERGE INTO … USING (SELECT … FROM DUAL UNION ALL …) …``
     - Yes
     - re-SELECT on ``match_fields``
   * - ``mssql``
     - ``MERGE INTO … USING (VALUES (…)) AS src(…) … OUTPUT inserted.*;``
     - Yes
     - re-SELECT on ``match_fields``
   * - ``spanner``
     - ``INSERT OR UPDATE INTO … (…) VALUES (…)``
     - No
     - re-SELECT on ``match_fields``
   * - anything else
     - fallback: ``SELECT`` + ``add_many`` + ``update_many``
     - n/a
     - SQLAlchemy ORM identity map

Important behaviors:

- **Match key safety gate.** The resolver only takes the native path when
  ``match_fields`` is *provably* unique (PK / UniqueConstraint / unique
  Index). If it cannot prove uniqueness, ``kind="fallback"`` is selected
  silently — this is the correctness anchor that prevents non-unique match
  keys from inserting duplicates instead of updating.
- **``no_merge=True``** forces the fallback path regardless of dialect
  capability. Use it as a deterministic per-call override for testing or to
  preserve historical per-row ``UPDATE``/``INSERT`` semantics.
- **``chunk_size``** mirrors ``add_many``: each chunk compiles to exactly one
  native statement (plus a re-SELECT for hydration on dialects without
  RETURNING).
- **Server-managed PK safety net.** ``MERGE`` (oracle / mssql) and
  ``INSERT OR UPDATE`` (spanner) cannot transparently invoke server-side
  ``Sequence`` / ``Identity`` defaults the way ``INSERT ... ON CONFLICT``
  does on PostgreSQL. When any prepared row is missing a primary-key
  column on those dialects, ``upsert_many`` transparently falls back to
  the SELECT-then-partition path so the sequence/identity machinery
  runs normally. Models with Python-callable PK defaults (UUIDv6 /
  UUIDv7 / nano-id) keep the single-statement native path because
  the row is populated before dispatch.
- **No breaking changes.** ``Sequence[ModelT]`` return shape is preserved;
  Litestar session / store callers using the single-row ``OnConflictUpsert``
  API are unaffected.

.. code-block:: python

    from collections.abc import Sequence
    from sqlalchemy.ext.asyncio import AsyncSession

    async def upsert_posts(db_session: AsyncSession, posts: list[Post]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)
        return await repository.upsert_many(
            posts,
            match_fields=["slug"],
            chunk_size=500,
        )

Specialized Repositories
------------------------

Advanced Alchemy provides specialized repositories for common patterns.

Slug Repository
~~~~~~~~~~~~~~~

For models using the ``SlugKey`` mixin, the ``SQLAlchemyAsyncSlugRepository`` adds a ``get_by_slug`` method:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository

    class TagRepository(SQLAlchemyAsyncSlugRepository[Tag]):
        model_type = Tag

    async def get_tag_by_slug(db_session: AsyncSession, slug: str) -> Tag:
        repository = TagRepository(session=db_session)
        return await repository.get_by_slug(slug)

Query Repository
~~~~~~~~~~~~~~~~

For complex custom queries or aggregations:

.. code-block:: python

    from typing import Any
    from advanced_alchemy.repository import SQLAlchemyAsyncQueryRepository
    from sqlalchemy import select, func, Row

    async def get_posts_count_by_status(db_session: AsyncSession) -> list[Row[Any]]:
        repository = SQLAlchemyAsyncQueryRepository(session=db_session)
        return await repository.get_many(
            select(Post.published, func.count(Post.id)).group_by(Post.published)
        )

=================
Repository Basics
=================

A **Repository** encapsulates SQLAlchemy queries and persistence logic for one mapped model behind a uniform interface (``add``, ``get``, ``get_many``, ``update``, ``delete``), keeping query logic reusable and testable against SQL or in-memory mock repositories.

Choosing a Repository Class
---------------------------

Every async repository has a synchronous counterpart; use the async classes with ``AsyncSession`` and the sync classes with ``Session``:

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Repository Type
     - Description
   * - ``SQLAlchemyAsyncRepository`` / ``SQLAlchemySyncRepository``
     - Standard model CRUD, filtering, pagination, and bulk upserts.
   * - ``SQLAlchemyAsyncSlugRepository`` / ``SQLAlchemySyncSlugRepository``
     - Models with URL slugs (such as ``/posts/hello-world``): generates unique slugs and queries rows by slug.
   * - ``SQLAlchemyAsyncQueryRepository`` / ``SQLAlchemySyncQueryRepository``
     - Arbitrary ``SELECT`` statements, joins, and ``GROUP BY`` aggregations not bound to a single model.

Creating and Reading Rows
-------------------------

Subclass ``SQLAlchemyAsyncRepository`` and set ``model_type`` to your mapped model class:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.mixins import SlugKey
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository


    class Post(BigIntAuditBase):
        __tablename__ = "repo_basics_post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)


    class Tag(BigIntAuditBase, SlugKey):
        __tablename__ = "repo_basics_tag"

        name: Mapped[str]


    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        model_type = Post


    async def create_and_fetch_post(db_session: AsyncSession) -> Post:
        repo = PostRepository(session=db_session)
        saved = await repo.add(
            Post(title="Getting Started", content="Repositories keep queries simple."),
            auto_commit=True,
        )
        return await repo.get(saved.id)

When missing records are expected, use ``get_or_none`` to return ``None`` instead of raising
``NotFoundError``:

.. code-block:: python

    from typing import Optional


    async def find_post_or_none(db_session: AsyncSession, post_id: int) -> Optional[Post]:
        repo = PostRepository(session=db_session)
        return await repo.get_or_none(post_id)

Saving, Updating, and Deleting in Bulk
--------------------------------------

Use ``add_many``, ``update_many``, and ``delete_many`` to persist, modify, or remove batches of records without per-row round-trips:

.. tab-set::

    .. tab-item:: Add Many

        .. code-block:: python

            from collections.abc import Sequence
            from sqlalchemy.ext.asyncio import AsyncSession


            async def create_drafts(
                db_session: AsyncSession,
                drafts: list[tuple[str, str]],
            ) -> Sequence[Post]:
                repo = PostRepository(session=db_session)
                return await repo.add_many(
                    [Post(title=title, content=body) for title, body in drafts],
                    auto_commit=True,
                )

    .. tab-item:: Update Many

        .. code-block:: python

            from sqlalchemy.ext.asyncio import AsyncSession


            async def publish_posts(db_session: AsyncSession, post_ids: list[int]) -> list[Post]:
                repo = PostRepository(session=db_session)
                posts = await repo.get_many(Post.id.in_(post_ids), published=False)
                for post in posts:
                    post.published = True
                return await repo.update_many(posts, auto_commit=True)

    .. tab-item:: Delete Many

        .. code-block:: python

            from collections.abc import Sequence
            from sqlalchemy.ext.asyncio import AsyncSession


            async def remove_posts(db_session: AsyncSession, post_ids: list[int]) -> Sequence[Post]:
                repo = PostRepository(session=db_session)
                return await repo.delete_many(post_ids, auto_commit=True)

Syncing External Data with Upserts
----------------------------------

``upsert_many`` inserts new rows and updates matching records in a single call. When ``match_fields`` targets a unique or primary-key constraint, it compiles a native dialect upsert (``ON CONFLICT DO UPDATE`` on PostgreSQL, CockroachDB, SQLite, and DuckDB, ``ON DUPLICATE KEY UPDATE`` on MySQL and MariaDB, ``MERGE`` on Oracle and SQL Server, or ``INSERT OR UPDATE`` on Spanner) and falls back to an ORM select-then-save path otherwise:

.. code-block:: python

    from collections.abc import Sequence
    from sqlalchemy.ext.asyncio import AsyncSession


    async def sync_imported_posts(db_session: AsyncSession, incoming: list[Post]) -> Sequence[Post]:
        repo = PostRepository(session=db_session)
        return await repo.upsert_many(
            incoming,
            match_fields=["id"],
            auto_commit=True,
        )

URL Slugs and Summary Queries
-----------------------------

Use ``SQLAlchemyAsyncSlugRepository`` for slug-based lookups (such as ``/tags/python``) and ``SQLAlchemyAsyncQueryRepository`` for arbitrary ``SELECT`` and ``GROUP BY`` statements:

.. tab-set::

    .. tab-item:: Slug Lookups

        .. code-block:: python

            from sqlalchemy.ext.asyncio import AsyncSession
            from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository


            class TagRepository(SQLAlchemyAsyncSlugRepository[Tag]):
                model_type = Tag


            async def find_tag(db_session: AsyncSession, slug: str) -> Tag:
                repo = TagRepository(session=db_session)
                return await repo.get_by_slug(slug)

    .. tab-item:: Custom Summary Query

        .. code-block:: python

            from typing import Any
            from sqlalchemy import Row, func, select
            from sqlalchemy.ext.asyncio import AsyncSession
            from advanced_alchemy.repository import SQLAlchemyAsyncQueryRepository


            async def count_posts_by_status(db_session: AsyncSession) -> list[Row[Any]]:
                query_repo = SQLAlchemyAsyncQueryRepository(session=db_session)
                return await query_repo.get_many(
                    select(Post.published, func.count(Post.id)).group_by(Post.published),
                )

Next Steps
----------

* :doc:`filtering`: Search text, filter by collections or nullability, and paginate results.
* :doc:`/reference/repository`: Complete repository API reference.

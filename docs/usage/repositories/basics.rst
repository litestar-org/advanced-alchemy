=================
Repository Basics
=================

Think of a **Repository** as a dedicated helper for one database table. Instead of writing raw SQLAlchemy ``select()`` and ``session.add()`` calls throughout your app, you point a repository at your ``Post`` model once and call clear methods like ``repo.add(post)``, ``repo.get(post_id)``, or ``repo.get_many()``.

Choosing a Repository Class
---------------------------

Every async repository has an identical synchronous version—pick async when using ``AsyncSession`` and sync when using ``Session``:

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Repository Type
     - When to Use It
   * - ``SQLAlchemyAsyncRepository`` / ``SQLAlchemySyncRepository``
     - Everyday tables: create, read, update, delete, filter, paginate, and bulk upsert.
   * - ``SQLAlchemyAsyncSlugRepository`` / ``SQLAlchemySyncSlugRepository``
     - Tables with URL slugs (like ``/posts/hello-world``): generates unique slugs and looks up rows by slug.
   * - ``SQLAlchemyAsyncQueryRepository`` / ``SQLAlchemySyncQueryRepository``
     - Custom ``SELECT`` queries, joins, and ``GROUP BY`` summaries that don't map to a single model.

Creating and Reading Rows
-------------------------

Suppose our blog has ``Post`` and ``Tag`` tables. Subclass ``SQLAlchemyAsyncRepository`` and set ``model_type = Post``:

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

Saving, Updating, and Deleting in Bulk
--------------------------------------

When importing a batch of drafts or publishing ten posts at once, looping one query at a time is slow. Use the ``*_many`` methods to handle whole batches in a single step:

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

Imagine syncing posts from an external CMS: some posts are brand new, and others are updates to rows already in your database.

``upsert_many`` inserts new rows and updates matching ones in one call. Behind the scenes, it uses your database's native upsert command (such as ``ON CONFLICT DO UPDATE`` on PostgreSQL/SQLite or ``MERGE`` on Oracle/SQL Server) whenever ``match_fields`` points to a unique column, and safely falls back to a standard lookup-and-save flow otherwise:

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

Need to look up tags by URL slug (like ``/tags/python``) or run a custom ``GROUP BY`` count? Use the slug or query repository:

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

* :doc:`filtering` — Search text, filter by lists or null values, and paginate results.
* :doc:`/reference/repository` — Complete repository API reference.

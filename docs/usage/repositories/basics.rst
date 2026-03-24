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
        posts = await repository.list(Post.id.in_(post_ids), published=False)

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
        return await repository.list(
            select(Post.published, func.count(Post.id)).group_by(Post.published)
        )

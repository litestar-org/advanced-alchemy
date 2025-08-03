============
Repositories
============

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
     - | - Async session support
       | - Basic CRUD operations
       | - Filtering and pagination
       | - Bulk operations
   * - ``SQLAlchemyAsyncSlugRepository``
     - | - Async session support
       | - All base repository features
       | - Slug-based lookups
       | - URL-friendly operations
   * - ``SQLAlchemyAsyncQueryRepository``
     - | - Async session support
       | - Custom query execution
       | - Complex aggregations
       | - Raw SQL support
   * - ``SQLAlchemySyncRepository``
     - | - Sync session support
       | - Basic CRUD operations
       | - Filtering and pagination
       | - Bulk operations
   * - ``SQLAlchemySyncSlugRepository``
     - | - Sync session support
       | - All base repository features
       | - Slug-based lookups
       | - URL-friendly operations
   * - ``SQLAlchemySyncQueryRepository``
     - | - Sync session support
       | - Custom query execution
       | - Complex aggregations
       | - Raw SQL support

Basic Repository Usage
----------------------

.. note::

    The following examples assumes the existence of the
    ``Post`` model defined in :ref:`many_to_many_relationships` and the
    ``Tag`` model defined in :ref:`using_unique_mixin`.

Let's implement a basic repository for our blog post model:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from sqlalchemy.ext.asyncio import AsyncSession
    from uuid import UUID

    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        """Repository for managing blog posts."""
        model_type = Post

    async def create_post(db_session: AsyncSession, title: str, content: str, author_id: UUID) -> Post:
        repository = PostRepository(session=db_session)
        return await repository.add(
            Post(title=title, content=content, author_id=author_id), auto_commit=True
        )

Filtering and Querying
----------------------

Advanced Alchemy provides powerful filtering capabilities:

.. code-block:: python

    import datetime

    async def get_recent_posts(db_session: AsyncSession) -> list[Post]:
        repository = PostRepository(session=db_session)

        # Create filter for posts from last week
        return await repository.list(
            Post.published == True,
            Post.created_at > (datetime.datetime.utcnow() - timedelta(days=7))
        )

Pagination
----------

`list_and_count` enables us to quickly create paginated queries that include a total count of rows.

.. code-block:: python

    from advanced_alchemy.filters import LimitOffset

    async def get_paginated_posts(
        db_session: AsyncSession,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[list[Post], int]:
        repository = PostRepository(session=db_session)

        offset = (page - 1) * page_size

        # Get page of results and total count
        results, total = await repository.list_and_count(
            LimitOffset(offset=offset, limit=page_size)
        )

        return results, total

Bulk Operations
---------------

Repositories support efficient bulk operations:

Add Many
--------

.. code-block:: python

    async def create_posts(db_session: AsyncSession, data: list[tuple[str, str, UUID]]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)

        # Create posts
        return await repository.add_many(
            [Post(title=title, content=content, author_id=author_id) for title, content, author_id in data],
            auto_commit=True
        )

Update Many
-----------

.. code-block:: python

    async def publish_posts(db_session: AsyncSession, post_ids: list[int]) -> list[Post]:
        repository = PostRepository(session=db_session)

        # Fetch posts to update
        posts = await repository.list(Post.id.in_(post_ids), published =False)

        # Update all posts
        for post in posts:
            post.published = True

        return await repository.update_many(posts)

Delete Many
-----------

.. code-block:: python

    async def delete_posts(db_session: AsyncSession, post_ids: list[int]) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.delete_many(Post.id.in_(post_ids))

Delete Where
-------------

.. code-block:: python

    async def delete_unpublished_posts (db_session: AsyncSession) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.delete_where(Post.published == False)



Transaction Management
----------------------



.. code-block:: python

    async def create_post_with_tags(
        db_session: AsyncSession,
        title: str,
        content: str,
        tag_names: list[str]
    ) -> Post:
        # Both repositories share the same transaction
        post_repo = PostRepository(session=db_session)
        tag_repo = TagRepository(session=db_session)

        async with db_session.begin():
            # Create or get existing tags
            tags = []
            for name in tag_names:
                tag = await tag_repo.get_one_or_none(name=name)
                if not tag:
                    tag = await tag_repo.add(Tag(name=name, slug=slugify(name)))
                tags.append(tag)

            # Create post with tags
            post = await post_repo.add(
                Post(title=title, content=content, tags=tags),
                auto_commit=True
            )

            return post

.. seealso::

    This is just to illustrate the concept. In practice, :class:`UniqueMixin`
    should be used to handle this lookup even more easily.  See :ref:`using_unique_mixin`.

Specialized Repositories
------------------------

Advanced Alchemy provides specialized repositories for common patterns.

Slug Repository
~~~~~~~~~~~~~~~

For models using the :class:`SlugKey` mixin, there is a specialized Slug repository that adds a ``get_by_slug`` method:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository

    class ArticleRepository(SQLAlchemyAsyncSlugRepository[Article]):
        """Repository for articles with slug-based lookups."""
        model_type = Article

    async def get_article_by_slug(db_session: AsyncSession, slug: str) -> Article:
        repository = ArticleRepository(session=db_session)
        return await repository.get_by_slug(slug)

Query Repository
----------------

For complex custom queries:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncQueryRepository
    from sqlalchemy import select, func

    async def get_posts_per_author(db_session: AsyncSession) -> list[tuple[UUID, int]]:
        repository = SQLAlchemyAsyncQueryRepository(session=db_session)
        return await repository.list(select(Post.author_id, func.count(Post.id)).group_by(Post.author_id))

This covers the core functionality of repositories. The next section will explore services,
which build upon repositories to provide higher-level business logic and data transformation.

============
Repositories
============

Advanced Alchemy's repository pattern provides a clean, consistent interface for database operations.
This pattern abstracts away the complexity of SQLAlchemy sessions and query building while providing
type-safe operations.

Understanding Repositories
--------------------------

A repository acts as a collection-like interface to your database models. It provides methods for:

- Creating, reading, updating, and deleting records
- Filtering and pagination
- Bulk operations

Basic Repository Usage
----------------------

Let's continue with our blog example:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from sqlalchemy.ext.asyncio import AsyncSession

    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        """Repository for managing blog posts."""
        model_type = Post

    async def create_post(session: AsyncSession, title: str, content: str, author_id: UUID) -> Post:
        repository = PostRepository(session=session)
        return await repository.add(
            Post(title=title, content=content, author_id=author_id)
        )

Filtering and Querying
----------------------

Advanced Alchemy provides powerful filtering capabilities:

.. code-block:: python

    from advanced_alchemy.filters import CollectionFilter, FilterTypes
    from datetime import datetime, timedelta

    # Define filters for posts
    class PostFilter(CollectionFilter):
        title: str | None = None
        published: bool | None = None
        created_after: datetime | None = None

        # Map filters to model fields
        model_type = Post

    async def get_recent_posts(session: AsyncSession) -> list[Post]:
        repository = PostRepository(session=session)

        # Create filter for posts from last week
        filters = PostFilter(
            published=True,
            created_after=datetime.utcnow() - timedelta(days=7)
        )

        return await repository.list(filters)

Pagination
----------

Repositories support offset/limit pagination:

.. code-block:: python

    async def get_paginated_posts(
        session: AsyncSession,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[list[Post], int]:
        repository = PostRepository(session=session)

        # Get page of results and total count
        results, total = await repository.list_and_count(
            offset=(page - 1) * page_size,
            limit=page_size
        )

        return results, total

Bulk Operations
---------------

Repositories support efficient bulk operations:

.. code-block:: python

    async def publish_posts(session: AsyncSession, post_ids: list[int]) -> list[Post]:
        repository = PostRepository(session=session)

        # Fetch posts to update
        posts = await repository.list(
            PostFilter(id__in=post_ids, published=False)
        )

        # Update all posts
        for post in posts:
            post.published = True

        return await repository.update_many(posts)

Transaction Management
----------------------

Repositories handle transaction management automatically:

.. code-block:: python

    async def create_post_with_tags(
        session: AsyncSession,
        title: str,
        content: str,
        tag_names: list[str]
    ) -> Post:
        # Both repositories share the same transaction
        post_repo = PostRepository(session=session)
        tag_repo = TagRepository(session=session)

        async with session.begin():
            # Create or get existing tags
            tags = []
            for name in tag_names:
                tag = await tag_repo.get_one_or_none(TagFilter(name=name))
                if not tag:
                    tag = await tag_repo.add(Tag(name=name))
                tags.append(tag)

            # Create post with tags
            post = await post_repo.add(
                Post(title=title, content=content, tags=tags)
            )

            return post

Specialized Repositories
------------------------

Advanced Alchemy provides specialized repositories for common patterns:

Slug Repository
---------------

For models using the SlugMixin:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository

    class ArticleRepository(SQLAlchemyAsyncSlugRepository[Article]):
        """Repository for articles with slug-based lookups."""
        model_type = Article

    async def get_article_by_slug(session: AsyncSession, slug: str) -> Article:
        repository = ArticleRepository(session=session)
        return await repository.get_by_slug(slug)

Query Repository
----------------

For complex custom queries:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncQueryRepository
    from sqlalchemy import select, func

    class PostAnalyticsRepository(SQLAlchemyAsyncQueryRepository[Post]):
        """Repository for post analytics queries."""
        model_type = Post

        async def get_posts_per_author(self) -> list[tuple[UUID, int]]:
            query = (
                select(Post.author_id, func.count(Post.id))
                .group_by(Post.author_id)
            )
            return await self.execute_many(query)

This covers the core functionality of repositories. The next section will explore services,
which build upon repositories to provide higher-level business logic and data transformation.

========
Advanced
========

Advanced Alchemy supports bulk operations, specialized repositories, and custom query patterns for complex requirements.

Prerequisites
=============

Understanding of :doc:`basics` and :doc:`filtering` recommended.

Bulk Operations
===============

Repositories provide efficient bulk operation methods for working with multiple records.

Add Many
--------

Create multiple records in a single operation:

.. code-block:: python

    from typing import Sequence

    async def create_posts(db_session: AsyncSession, data: list[tuple[str, str, UUID]]) -> Sequence[Post]:
        repository = PostRepository(session=db_session)

        # Create posts
        return await repository.add_many(
            [Post(title=title, content=content, author_id=author_id) for title, content, author_id in data],
            auto_commit=True
        )

Characteristics:

- Single database round-trip
- Batch insert operation
- Returns sequence of created records
- More efficient than multiple ``add()`` calls

Update Many
-----------

Update multiple records:

.. code-block:: python

    async def publish_posts(db_session: AsyncSession, post_ids: list[int]) -> list[Post]:
        repository = PostRepository(session=db_session)

        # Fetch posts to update
        posts = await repository.list(Post.id.in_(post_ids), Post.published == False)

        # Update all posts
        for post in posts:
            post.published = True

        return await repository.update_many(posts, auto_commit=True)

Characteristics:

- Updates multiple records in single transaction
- Maintains object state
- Returns updated records

Delete Many
-----------

Delete multiple records by IDs:

.. code-block:: python

    async def delete_posts(db_session: AsyncSession, post_ids: list[int]) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.delete_many(post_ids, auto_commit=True)

Characteristics:

- Deletes by primary key list
- Single database operation
- Returns deleted records (before deletion)

Delete Where
------------

Delete records matching filter criteria:

.. code-block:: python

    async def delete_unpublished_posts(db_session: AsyncSession) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.delete_where(Post.published == False, auto_commit=True)

Characteristics:

- Deletes all records matching filter
- More efficient than fetch-then-delete
- Returns deleted records (before deletion)

Upsert Operations
=================

Upsert (insert or update) handles conflicts automatically:

.. code-block:: python

    async def upsert_post(
        db_session: AsyncSession,
        post_id: int,
        title: str,
        content: str
    ) -> Post:
        repository = PostRepository(session=db_session)

        return await repository.upsert(
            {"id": post_id, "title": title, "content": content},
            match_fields=["id"],
            auto_commit=True
        )

Parameters:

- ``match_fields``: Columns to match for existing records
- If match found: updates existing record
- If no match: inserts new record

Characteristics:

- Atomic operation
- Database-specific implementation (``ON CONFLICT``, ``MERGE``, etc.)
- Handles race conditions

Bulk Upsert
-----------

Upsert multiple records:

.. code-block:: python

    async def upsert_posts(
        db_session: AsyncSession,
        posts_data: list[dict]
    ) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.upsert_many(
            posts_data,
            match_fields=["id"],
            auto_commit=True
        )

Characteristics:

- Efficient batch upsert
- Single database round-trip
- Maintains consistency

Transaction Management
======================

Complex Multi-Repository Transactions
--------------------------------------

Coordinate multiple repositories in a single transaction:

.. code-block:: python

    from advanced_alchemy.utils.text import slugify

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
                tag = await tag_repo.get_one_or_none(Tag.name == name)
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
    should be used to handle this lookup more easily. See :ref:`using_unique_mixin`.

Characteristics:

- Multiple repositories share session
- Single transaction boundary
- Automatic rollback on exception
- Maintains ACID properties

Specialized Repositories
========================

Slug Repository
---------------

For models using the ``SlugKey`` mixin, use ``SQLAlchemyAsyncSlugRepository``:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository

    class ArticleRepository(SQLAlchemyAsyncSlugRepository[Article]):
        """Repository for articles with slug-based lookups."""
        model_type = Article

    async def get_article_by_slug(db_session: AsyncSession, slug: str) -> Article:
        repository = ArticleRepository(session=db_session)
        return await repository.get_by_slug(slug)

Additional methods:

- ``get_by_slug(slug: str)`` - Retrieve record by slug
- All standard repository methods

Characteristics:

- Slug-based lookups
- URL-friendly operations
- Optimized for slug queries

Query Repository
----------------

For complex custom queries:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncQueryRepository
    from sqlalchemy import select, func

    async def get_posts_per_author(db_session: AsyncSession) -> list[tuple[UUID, int]]:
        repository = SQLAlchemyAsyncQueryRepository(session=db_session)

        stmt = select(Post.author_id, func.count(Post.id)).group_by(Post.author_id)

        return await repository.list(stmt)

Characteristics:

- Executes raw SELECT statements
- Supports aggregations, joins, subqueries
- Returns query results (not model instances for aggregations)
- Useful for reporting and analytics

Implementation Patterns
=======================

Performance Characteristics
---------------------------

Different patterns have distinct performance profiles:

**Single Insert Pattern**

.. code-block:: python

    # Multiple individual inserts
    for user_data in users:
        await repository.add(User(**user_data), auto_commit=True)
    # Characteristics: N commits, slower with many records, simple code

**Bulk Insert Pattern**

.. code-block:: python

    # Bulk insert
    await repository.add_many(
        [User(**data) for data in users],
        auto_commit=True
    )
    # Characteristics: 1 commit, faster with many records, efficient

Choose bulk operations for multiple records.

Upsert vs Select-Then-Update
-----------------------------

Two patterns for conditional updates:

**Select-Then-Update Pattern**

.. code-block:: python

    # Fetch record
    post = await repository.get_one_or_none(Post.id == post_id)

    if post:
        # Update existing
        post.title = new_title
        await repository.update(post, auto_commit=True)
    else:
        # Create new
        await repository.add(Post(id=post_id, title=new_title), auto_commit=True)

Characteristics:

- Two database round-trips
- Race condition possible between select and insert
- Clear logic flow

**Upsert Pattern**

.. code-block:: python

    # Upsert
    await repository.upsert(
        {"id": post_id, "title": new_title},
        match_fields=["id"],
        auto_commit=True
    )

Characteristics:

- Single database round-trip
- Atomic operation, no race conditions
- Database-specific implementation

Upsert is more efficient and safer for concurrent access.

Custom Repository Methods
--------------------------

Extend repositories with custom methods:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from sqlalchemy import select, func

    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        """Extended repository with custom methods."""
        model_type = Post

        async def get_published_count(self) -> int:
            """Get count of published posts."""
            stmt = select(func.count(Post.id)).where(Post.published == True)
            result = await self.session.execute(stmt)
            return result.scalar_one()

        async def get_recent_published(self, limit: int = 10) -> list[Post]:
            """Get recent published posts."""
            return await self.list(
                Post.published == True,
                Post.published_at.isnot(None),
                load=[selectinload(Post.tags)],
                order_by=[Post.published_at.desc()],
                limit=limit
            )

Custom methods encapsulate domain-specific queries.

Technical Constraints
=====================

Bulk Operation Atomicity
-------------------------

Bulk operations are atomic within transactions:

.. code-block:: python

    # ✅ Correct - bulk operation is atomic
    async with db_session.begin():
        posts = await repository.add_many(post_instances)
        # All inserts succeed or all fail

    # ⚠️ Note - individual auto_commit operations are separate transactions
    posts = await repository.add_many(post_instances, auto_commit=True)
    # Each insert is separate transaction (database-dependent behavior)

Use manual transactions for guaranteed atomicity across bulk operations.

Upsert Match Field Requirements
--------------------------------

``match_fields`` must correspond to unique constraints:

.. code-block:: python

    # ✅ Correct - match_fields on unique columns
    await repository.upsert(
        {"email": "user@example.com", "name": "Alice"},
        match_fields=["email"],  # email has unique constraint
        auto_commit=True
    )

    # ❌ Incorrect - match_fields without unique constraint
    await repository.upsert(
        {"name": "Alice", "age": 30},
        match_fields=["name"],  # name is not unique
        auto_commit=True
    )
    # May update wrong record or fail

Ensure ``match_fields`` have unique constraints or primary key.

Database-Specific Upsert Behavior
----------------------------------

Upsert implementation varies by database:

- **PostgreSQL**: Uses ``ON CONFLICT DO UPDATE``
- **MySQL**: Uses ``ON DUPLICATE KEY UPDATE``
- **SQLite**: Uses ``ON CONFLICT DO UPDATE`` (requires SQLite 3.24.0+)
- **Oracle**: Uses ``MERGE`` statement
- **SQL Server**: Uses ``MERGE`` statement

Test upsert behavior for your target database backend.

Next Steps
==========

This covers core repository functionality. Next, explore services for business logic.

Related Topics
==============

- :doc:`../services/index` - Service layer built on repositories
- :doc:`basics` - Basic CRUD operations
- :doc:`filtering` - Query filtering and pagination
- :doc:`../modeling/advanced` - UniqueMixin for automatic deduplication

======
Basics
======

Advanced Alchemy repositories provide type-safe CRUD operations for database models.

Prerequisites
=============

This section builds on :doc:`../modeling/basics`. Ensure you understand models before working with repositories.

Understanding Repositories
==========================

A repository acts as a collection-like interface to your database models, abstracting away SQLAlchemy session management and query building.

Basic Repository Implementation
================================

Creating a repository for the Post model:

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

.. note::

    The following examples assume the existence of the
    ``Post`` model defined in :ref:`many_to_many_relationships` and the
    ``Tag`` model defined in :ref:`using_unique_mixin`.

Repository configuration:

- Generic type parameter ``[Post]`` provides type safety
- ``model_type`` class attribute specifies the model class
- Session passed to constructor manages transactions

CRUD Operations
===============

Create
------

Adding a single record:

.. code-block:: python

    async def create_post(db_session: AsyncSession, title: str, content: str) -> Post:
        repository = PostRepository(session=db_session)
        post = Post(title=title, content=content, published=False)
        return await repository.add(post, auto_commit=True)

The ``auto_commit=True`` parameter automatically commits the transaction.

Read
----

Retrieving records with different methods:

.. code-block:: python

    # Get one record (raises NotFoundError if not found)
    post = await repository.get_one(Post.id == post_id)

    # Get one or None (returns None if not found)
    post = await repository.get_one_or_none(Post.id == post_id)

    # List all records matching criteria
    posts = await repository.list(Post.published == True)

    # List with multiple conditions
    posts = await repository.list(
        Post.published == True,
        Post.created_at > start_date
    )

Update
------

Updating a record:

.. code-block:: python

    async def update_post(db_session: AsyncSession, post_id: int, title: str) -> Post:
        repository = PostRepository(session=db_session)
        post = await repository.get_one(Post.id == post_id)
        post.title = title
        return await repository.update(post, auto_commit=True)

Alternative using dictionary:

.. code-block:: python

    post = await repository.update(
        post,
        {"title": title, "content": content},
        auto_commit=True
    )

Delete
------

Deleting a record:

.. code-block:: python

    async def delete_post(db_session: AsyncSession, post_id: int) -> Post:
        repository = PostRepository(session=db_session)
        post = await repository.get_one(Post.id == post_id)
        return await repository.delete(post, auto_commit=True)

Simple Filtering
================

Basic query filters using SQLAlchemy expressions:

.. code-block:: python

    import datetime
    from datetime import timedelta

    async def get_recent_posts(db_session: AsyncSession) -> list[Post]:
        repository = PostRepository(session=db_session)

        # Filter for posts from last week
        return await repository.list(
            Post.published == True,
            Post.created_at > (datetime.datetime.utcnow() - timedelta(days=7))
        )

Filters use standard SQLAlchemy column expressions (``==``, ``>``, ``<``, ``in_``, etc.).

Implementation Patterns
=======================

Repository Method Reference
---------------------------

Common repository methods:

.. list-table:: Core Methods
   :header-rows: 1
   :widths: 30 70

   * - Method
     - Purpose
   * - ``add(instance, auto_commit=False)``
     - Add single record
   * - ``get_one(*filters)``
     - Get single record, raise if not found
   * - ``get_one_or_none(*filters)``
     - Get single record or None
   * - ``list(*filters, **kwargs)``
     - Get multiple records
   * - ``update(instance, auto_commit=False)``
     - Update single record
   * - ``delete(instance, auto_commit=False)``
     - Delete single record
   * - ``list_and_count(*filters, **kwargs)``
     - Get records with total count

Auto-Commit vs Manual Transactions
-----------------------------------

Two transaction management patterns:

**Auto-Commit Pattern**

.. code-block:: python

    # Each operation commits immediately
    post = await repository.add(Post(title="New Post"), auto_commit=True)
    # Characteristics: Simple, immediate persistence, separate transaction per operation

**Manual Transaction Pattern**

.. code-block:: python

    # Multiple operations in single transaction
    async with db_session.begin():
        post = await repository.add(Post(title="New Post"))
        tag = await tag_repository.add(Tag(name="Python"))
        post.tags.append(tag)
        await db_session.flush()
    # Characteristics: Multiple operations, single transaction, automatic rollback on error

Use auto-commit for single operations, manual transactions for multiple related operations.

Sync Repositories
-----------------

For synchronous code, use ``SQLAlchemySyncRepository``:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from sqlalchemy.orm import Session

    class PostRepository(SQLAlchemySyncRepository[Post]):
        """Sync repository for posts."""
        model_type = Post

    def create_post(db_session: Session, title: str, content: str) -> Post:
        repository = PostRepository(session=db_session)
        return repository.add(
            Post(title=title, content=content), auto_commit=True
        )

Sync repositories have the same API as async repositories, without ``await``.

Technical Constraints
=====================

Session Management
------------------

Repositories do not manage session lifecycle:

.. code-block:: python

    # ✅ Correct - session managed externally
    async with AsyncSession(engine) as session:
        repository = PostRepository(session=session)
        post = await repository.add(Post(title="Test"), auto_commit=True)
        # Session closes here

    # ❌ Incorrect - repository doesn't close session
    repository = PostRepository(session=session)
    post = await repository.add(Post(title="Test"), auto_commit=True)
    # Session remains open, must be closed manually

Always manage session lifecycle outside repositories.

NotFoundError Behavior
----------------------

``get_one`` raises exception when record not found:

.. code-block:: python

    from advanced_alchemy.exceptions import NotFoundError

    # ✅ Correct - handle exception
    try:
        post = await repository.get_one(Post.id == post_id)
    except NotFoundError:
        # Handle missing record
        post = None

    # ✅ Correct - use get_one_or_none for optional records
    post = await repository.get_one_or_none(Post.id == post_id)
    if post is None:
        # Handle missing record
        pass

Use ``get_one_or_none`` when records may not exist.

N+1 Query Problem
-----------------

Accessing relationships without eager loading causes N+1 queries:

.. code-block:: python

    # ❌ Incorrect - causes N+1 queries
    posts = await repository.list(Post.published == True)
    for post in posts:
        print(post.author.name)  # Triggers separate query per post

    # ✅ Correct - eager load relationships
    from sqlalchemy.orm import selectinload

    posts = await repository.list(
        Post.published == True,
        load=[selectinload(Post.author)]
    )
    for post in posts:
        print(post.author.name)  # No additional queries

Use eager loading (see :doc:`../modeling/relationships`) to prevent N+1 queries.

Next Steps
==========

Learn about filtering and pagination in :doc:`filtering`.

Related Topics
==============

- :doc:`filtering` - Advanced filtering and pagination
- :doc:`advanced` - Bulk operations and specialized repositories
- :doc:`../modeling/relationships` - Eager loading strategies

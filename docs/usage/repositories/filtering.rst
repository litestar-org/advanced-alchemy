========================
Filtering and Pagination
========================

Advanced Alchemy provides a powerful and flexible system for filtering and paginating your database queries.

Basic Filtering
---------------

You can pass SQLAlchemy expressions directly to repository methods like ``list``, ``list_and_count``, and ``count``.

.. code-block:: python

    import datetime
    from sqlalchemy.ext.asyncio import AsyncSession

    async def get_recent_posts(db_session: AsyncSession) -> list[Post]:
        repository = PostRepository(session=db_session)
        return await repository.list(
            Post.published.is_(True),
            Post.created_at > (datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=7))
        )

Filter Constructs
-----------------

Advanced Alchemy includes several pre-defined filter constructs located in ``advanced_alchemy.filters``.

Collection Filter
~~~~~~~~~~~~~~~~~

Filters records where a column's value is (or is not) in a collection of values.

.. code-block:: python

    from advanced_alchemy.filters import CollectionFilter

    # Get posts with specific IDs
    posts = await repository.list(CollectionFilter(field_name="id", values=[1, 2, 3]))

Search Filter
~~~~~~~~~~~~~

Provides basic string search capabilities.

.. code-block:: python

    from advanced_alchemy.filters import SearchFilter

    # Case-insensitive search for posts containing "sqlalchemy" in the title
    posts = await repository.list(SearchFilter(field_name="title", value="sqlalchemy", ignore_case=True))

Null and Not Null Filters
~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 1.9.0

Filters records based on whether a column is ``NULL`` or ``NOT NULL``.

.. code-block:: python

    from advanced_alchemy.filters import NullFilter, NotNullFilter

    # Get posts that have not been published yet (published_at is NULL)
    unpublished = await repository.list(NullFilter(field_name="published_at"))

    # Get posts that have been published
    published = await repository.list(NotNullFilter(field_name="published_at"))

Pagination
----------

The ``LimitOffset`` filter is used for standard limit/offset pagination. The ``list_and_count`` method is particularly useful here as it returns both the page of results and the total record count.

.. code-block:: python

    from advanced_alchemy.filters import LimitOffset

    async def get_paginated_posts(
        db_session: AsyncSession,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[list[Post], int]:
        repository = PostRepository(session=db_session)
        offset = (page - 1) * page_size

        return await repository.list_and_count(
            LimitOffset(offset=offset, limit=page_size)
        )

Explicit Routing
----------------

All read and count operations support an optional ``bind_group`` parameter for explicit routing control when using read replicas.

.. code-block:: python

    # Query from a specific bind group
    posts = await repository.list(bind_group="analytics")

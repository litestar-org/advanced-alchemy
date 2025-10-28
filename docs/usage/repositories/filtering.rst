=========
Filtering
=========

Advanced Alchemy provides powerful filtering capabilities for queries, including pagination, sorting, date ranges, and full-text search.

Prerequisites
=============

This section builds on :doc:`basics`.

Understanding Filters
=====================

Advanced Alchemy filter objects provide reusable, composable query filters. Filters encapsulate common query patterns like pagination, date ranges, and search.

Pagination
==========

``LimitOffset`` Filter
----------------------

Standard offset-based pagination:

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

``list_and_count`` returns:

- ``results``: List of records for the current page
- ``total``: Total count of records matching filters

Characteristics:

- Offset-based pagination
- Total count in single query
- Supports jumping to arbitrary pages
- Page numbers calculated client-side

Date Range Filtering
====================

``BeforeAfter`` Filter
----------------------

Filter records by date range:

.. code-block:: python

    from advanced_alchemy.filters import BeforeAfter
    import datetime

    async def get_posts_in_range(
        db_session: AsyncSession,
        start_date: datetime.datetime,
        end_date: datetime.datetime
    ) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.list(
            BeforeAfter(
                field_name="created_at",
                before=end_date,
                after=start_date
            )
        )

Parameters:

- ``field_name``: Column name to filter (e.g., "created_at", "updated_at")
- ``before``: Upper bound (inclusive)
- ``after``: Lower bound (inclusive)

Search Filtering
================

``SearchFilter``
----------------

Full-text search across columns:

.. code-block:: python

    from advanced_alchemy.filters import SearchFilter

    async def search_posts(
        db_session: AsyncSession,
        search_term: str
    ) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.list(
            SearchFilter(
                field_name="title",
                value=search_term,
                ignore_case=True
            )
        )

Parameters:

- ``field_name``: Column to search
- ``value``: Search term
- ``ignore_case``: Case-insensitive search (default: True)

Characteristics:

- Uses SQL LIKE operator
- Wildcard matching (``%search_term%``)
- Case-insensitive option
- Works with string columns

Order By Filtering
==================

``OrderBy`` Filter
------------------

Sort query results:

.. code-block:: python

    from advanced_alchemy.filters import OrderBy

    async def get_recent_posts(db_session: AsyncSession) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.list(
            OrderBy(field_name="created_at", sort_order="desc")
        )

Parameters:

- ``field_name``: Column name to sort by
- ``sort_order``: "asc" (ascending) or "desc" (descending)

Collection Filtering
====================

``CollectionFilter``
--------------------

Filter by column values in a collection:

.. code-block:: python

    from advanced_alchemy.filters import CollectionFilter

    async def get_posts_by_ids(
        db_session: AsyncSession,
        post_ids: list[int]
    ) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.list(
            CollectionFilter(field_name="id", values=post_ids)
        )

Parameters:

- ``field_name``: Column name
- ``values``: List of values to match

Equivalent to SQLAlchemy's ``Post.id.in_(post_ids)``.

Not Filter
----------

Negate other filters:

.. code-block:: python

    from advanced_alchemy.filters import NotFilter, CollectionFilter

    async def get_posts_except_ids(
        db_session: AsyncSession,
        excluded_ids: list[int]
    ) -> list[Post]:
        repository = PostRepository(session=db_session)

        return await repository.list(
            NotFilter(CollectionFilter(field_name="id", values=excluded_ids))
        )

Parameters:

- Wraps any other filter type
- Negates the filter condition

Equivalent to SQLAlchemy's ``~`` (NOT) operator.

Filter Configuration Options
=============================

When using Advanced Alchemy with web frameworks, filters can be configured declaratively. Complete reference of options:

.. code-block:: python

    filter_config = {
        # ID filtering
        "id_filter": UUID,  # Enable filtering by primary key type

        # Search configuration
        "search": "name,email",  # Comma-separated fields to search
        "search_ignore_case": True,  # Case-insensitive search

        # Pagination
        "pagination_type": "limit_offset",  # "limit_offset" or "cursor"
        "pagination_size": 20,  # Default page size

        # Date range filters
        "created_at": True,  # Enable created_at field filtering
        "updated_at": True,  # Enable updated_at field filtering

        # Sorting
        "sort_field": "created_at",  # Default sort field
        "sort_order": "desc",  # Default sort order ("asc" or "desc")
    }

Option descriptions:

- **id_filter**: Type hint for primary key filtering
- **search**: Comma-separated field names for search
- **search_ignore_case**: Case-sensitive or case-insensitive search
- **pagination_type**: Pagination strategy (offset or cursor-based)
- **pagination_size**: Default number of items per page
- **created_at**: Enable date range filtering on created_at field
- **updated_at**: Enable date range filtering on updated_at field
- **sort_field**: Default field for sorting results
- **sort_order**: Default sort direction ("asc" for ascending, "desc" for descending)

Implementation Patterns
=======================

Combining Filters
-----------------

Multiple filters compose naturally:

.. code-block:: python

    from advanced_alchemy.filters import LimitOffset, BeforeAfter, SearchFilter, OrderBy
    import datetime

    async def search_recent_posts(
        db_session: AsyncSession,
        search_term: str,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[list[Post], int]:
        repository = PostRepository(session=db_session)

        week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)

        results, total = await repository.list_and_count(
            SearchFilter(field_name="title", value=search_term),
            BeforeAfter(field_name="created_at", after=week_ago),
            OrderBy(field_name="created_at", sort_order="desc"),
            LimitOffset(offset=(page - 1) * page_size, limit=page_size)
        )

        return results, total

This query:

- Searches titles for search_term
- Filters to posts from last 7 days
- Orders by created_at descending
- Paginates results

Filters are ANDed together automatically.

Custom Filter Logic
-------------------

Combine filters with raw SQLAlchemy expressions:

.. code-block:: python

    from advanced_alchemy.filters import LimitOffset

    async def get_published_posts(
        db_session: AsyncSession,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[list[Post], int]:
        repository = PostRepository(session=db_session)

        results, total = await repository.list_and_count(
            Post.published == True,  # Raw SQLAlchemy filter
            Post.published_at.isnot(None),  # Another raw filter
            LimitOffset(offset=(page - 1) * page_size, limit=page_size)  # Filter object
        )

        return results, total

Mix filter objects with SQLAlchemy column expressions.

Building Dynamic Queries
-------------------------

Construct filters dynamically based on input:

.. code-block:: python

    from advanced_alchemy.filters import SearchFilter, BeforeAfter, OrderBy

    async def dynamic_post_search(
        db_session: AsyncSession,
        search: str | None = None,
        start_date: datetime.datetime | None = None,
        end_date: datetime.datetime | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> list[Post]:
        repository = PostRepository(session=db_session)

        filters = []

        if search:
            filters.append(SearchFilter(field_name="title", value=search))

        if start_date or end_date:
            filters.append(
                BeforeAfter(
                    field_name="created_at",
                    before=end_date,
                    after=start_date
                )
            )

        filters.append(OrderBy(field_name=sort_by, sort_order=sort_order))

        return await repository.list(*filters)

This pattern enables flexible query construction.

Technical Constraints
=====================

Pagination Limitations
----------------------

Offset-based pagination has performance characteristics:

.. code-block:: python

    # Performance degrades with large offsets
    results, total = await repository.list_and_count(
        LimitOffset(offset=10000, limit=20)  # Skips 10000 rows
    )
    # Database must scan and skip 10000 rows

Characteristics:

- ``OFFSET`` clause scans skipped rows
- Performance degrades with high offset values
- ``LIMIT`` clause is efficient
- Total count requires full table scan

For very large datasets, consider cursor-based pagination.

Search Filter Behavior
----------------------

``SearchFilter`` uses SQL LIKE with wildcards:

.. code-block:: python

    # SearchFilter behavior
    SearchFilter(field_name="title", value="python")
    # Generates: title LIKE '%python%'

Characteristics:

- Substring matching
- Cannot use indexes efficiently (leading wildcard)
- Case-sensitive or insensitive depending on database collation
- Use ``ignore_case=True`` for explicit case-insensitive search

For full-text search, consider database-specific features (PostgreSQL's ``tsvector``, MySQL's ``FULLTEXT``).

Filter Order Dependency
-----------------------

Filter application order can affect results:

.. code-block:: python

    # ✅ Correct - limit applies after filtering
    results, total = await repository.list_and_count(
        Post.published == True,  # Filter first
        LimitOffset(offset=0, limit=20)  # Then limit
    )
    # Returns 20 published posts, total counts all published posts

    # ✅ Also correct - order doesn't matter for these filters
    results, total = await repository.list_and_count(
        LimitOffset(offset=0, limit=20),  # Limit position doesn't matter
        Post.published == True
    )

Advanced Alchemy applies filters in logical order regardless of position.

Next Steps
==========

For bulk operations and specialized repositories, see :doc:`advanced`.

Related Topics
==============

- :doc:`advanced` - Bulk operations and custom queries
- :doc:`basics` - Basic CRUD operations
- :doc:`../modeling/relationships` - Filtering relationships

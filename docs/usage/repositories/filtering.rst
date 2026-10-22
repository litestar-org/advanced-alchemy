========================
Filtering and Pagination
========================

Advanced Alchemy provides a powerful and flexible system for filtering and paginating your database queries.

.. code-block:: python

    import datetime
    from typing import Optional

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.filters import CollectionFilter, LimitOffset, NotNullFilter, NullFilter, SearchFilter
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository


    class FilteringPost(BigIntAuditBase):
        __tablename__ = "filtering_post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        published_at: Mapped[Optional[datetime.datetime]] = mapped_column(default=None)


    class FilteringPostRepository(SQLAlchemyAsyncRepository[FilteringPost]):
        model_type = FilteringPost

Basic Filtering
---------------

You can pass SQLAlchemy expressions directly to repository methods like ``list``, ``list_and_count``, and ``count``.

.. code-block:: python

    async def get_recent_posts(db_session: AsyncSession) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.get_many(
            FilteringPost.published.is_(True),
            FilteringPost.created_at > (datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=7)),
        )

Filter Constructs
-----------------

Advanced Alchemy includes several pre-defined filter constructs located in ``advanced_alchemy.filters``.

Collection Filter
~~~~~~~~~~~~~~~~~

Filters records where a column's value is (or is not) in a collection of values.

.. code-block:: python

    async def get_posts_by_ids(db_session: AsyncSession, post_ids: list[int]) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.get_many(CollectionFilter(field_name="id", values=post_ids))

Search Filter
~~~~~~~~~~~~~

Provides basic string search capabilities.

.. code-block:: python

    async def search_posts(db_session: AsyncSession, query: str) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.get_many(SearchFilter(field_name="title", value=query, ignore_case=True))

``SearchFilter`` and ``NotInSearchFilter`` preserve SQL wildcard matching by
default: ``%`` matches any sequence of characters and ``_`` matches one character.
To match those characters literally in accounting codes or titles, opt in with
``escape_wildcards=True``:

.. code-block:: python

    literal_search = SearchFilter(field_name="title", value="50% off", escape_wildcards=True)

This option escapes ``%``, ``_``, and the escape character ``/`` while retaining
the surrounding substring wildcards. Dialect-specific pattern syntax, such as
SQL Server's bracket expressions (``[abc]``), is unchanged. It requires SQL
``ESCAPE`` support. Spanner has no ``ESCAPE`` clause, so ``escape_wildcards``
must stay ``False`` there. The Litestar and FastAPI filter providers enable it
through the ``search_escape_wildcards`` key of ``FilterConfig``.

Null and Not Null Filters
~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 1.9.0

Filters records based on whether a column is ``NULL`` or ``NOT NULL``.

.. code-block:: python

    async def get_unpublished_posts(db_session: AsyncSession) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.get_many(NullFilter(field_name="published_at"))


    async def get_published_posts(db_session: AsyncSession) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.get_many(NotNullFilter(field_name="published_at"))

Pagination
----------

The ``LimitOffset`` filter is used for standard limit/offset pagination. The ``list_and_count`` method is particularly useful here as it returns both the page of results and the total record count.

.. code-block:: python

    async def get_paginated_posts(
        db_session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FilteringPost], int]:
        repository = FilteringPostRepository(session=db_session)
        offset = (page - 1) * page_size

        return await repository.get_many_and_count(
            LimitOffset(offset=offset, limit=page_size),
        )

Explicit Routing
----------------

All read and count operations support an optional ``bind_group`` parameter for explicit routing control when using read replicas.

.. code-block:: python

    async def get_posts_from_analytics_replica(db_session: AsyncSession) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.get_many(bind_group="analytics")

Generated query parameter names
-------------------------------

The Litestar ``create_filter_dependencies()`` and FastAPI ``provide_filters()`` helpers
accept the same optional ``alias_generator`` configuration. Existing names such as
``pageSize``, ``searchString``, and ``orderBy`` remain the default. To expose snake_case
query parameters in either integration:

.. code-block:: python

    from advanced_alchemy.utils.dependencies import FilterConfig

    config: FilterConfig = {
        "pagination_type": "limit_offset",
        "search": "name",
        "sort_field": "created_at",
        "alias_generator": "snake_case",
    }

This configuration accepts ``?page_size=10&search_string=alice&order_by=created_at``.
Use ``"camel_case"`` to explicitly select camelCase, or supply a callable for custom
conventions. An explicit preset follows the same collision validation as a callable.
The generator receives canonical snake_case parameter names, including field-specific
names such as ``account_id_in``. Custom generators must return nonempty, distinct
strings. Names are resolved when dependencies are constructed and used consistently
for requests and OpenAPI; the generator does not run during requests.

This option controls query parameter names. It does not translate sort-field values
or change the internal dependency names configured through ``DependencyDefaults``.
Dependencies with equivalent configuration, defaults, and resolved query names reuse
the same cached provider. Different pagination defaults or dependency names remain
isolated.

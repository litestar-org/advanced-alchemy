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
        return await repository.list(
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
        return await repository.list(CollectionFilter(field_name="id", values=post_ids))

Search Filter
~~~~~~~~~~~~~

Provides basic string search capabilities.

.. code-block:: python

    async def search_posts(db_session: AsyncSession, query: str) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.list(SearchFilter(field_name="title", value=query, ignore_case=True))

Null and Not Null Filters
~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 1.9.0

Filters records based on whether a column is ``NULL`` or ``NOT NULL``.

.. code-block:: python

    async def get_unpublished_posts(db_session: AsyncSession) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.list(NullFilter(field_name="published_at"))


    async def get_published_posts(db_session: AsyncSession) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.list(NotNullFilter(field_name="published_at"))

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

        return await repository.list_and_count(
            LimitOffset(offset=offset, limit=page_size),
        )

Explicit Routing
----------------

All read and count operations support an optional ``bind_group`` parameter for explicit routing control when using read replicas.

.. code-block:: python

    async def get_posts_from_analytics_replica(db_session: AsyncSession) -> list[FilteringPost]:
        repository = FilteringPostRepository(session=db_session)
        return await repository.list(bind_group="analytics")

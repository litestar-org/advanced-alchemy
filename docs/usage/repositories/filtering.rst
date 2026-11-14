========================
Filtering and Pagination
========================

Suppose a reader visits your blog and searches for ``"python"``, filters to published articles from the past week, and views 20 posts per page.

Instead of manually conditionally appending ``.where()`` and ``.limit()`` clauses in every route, you can pass both plain SQLAlchemy expressions and ready-made filter objects directly into your repository calls.

Example Setup
-------------

.. code-block:: python

    import datetime
    from typing import Optional
    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.filters import (
        CollectionFilter,
        ComparisonFilter,
        LimitOffset,
        NotInCollectionFilter,
        NotNullFilter,
        NullFilter,
        RelationshipFilter,
        SearchFilter,
    )
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    filtering_post_tag = Table(
        "filtering_post_tag",
        BigIntAuditBase.metadata,
        Column("post_id", ForeignKey("filtering_post.id"), primary_key=True),
        Column("tag_id", ForeignKey("filtering_tag.id"), primary_key=True),
    )


    class FilteringTag(BigIntAuditBase):
        __tablename__ = "filtering_tag"

        slug: Mapped[str]


    class FilteringPost(BigIntAuditBase):
        __tablename__ = "filtering_post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        published_at: Mapped[Optional[datetime.datetime]] = mapped_column(default=None)
        tags: Mapped[list[FilteringTag]] = relationship(secondary=filtering_post_tag)


    class FilteringPostRepository(SQLAlchemyAsyncRepository[FilteringPost]):
        model_type = FilteringPost

Plain SQLAlchemy Conditions
---------------------------

For straightforward checks inside Python code, pass normal SQLAlchemy column comparisons straight to ``get_many`` or ``get_many_and_count``:

.. code-block:: python

    async def get_recent_posts(db_session: AsyncSession) -> list[FilteringPost]:
        cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=7)
        repo = FilteringPostRepository(session=db_session)
        return await repo.get_many(
            FilteringPost.published.is_(True),
            FilteringPost.created_at >= cutoff,
        )

Built-In Filter Helpers
-----------------------

When building web endpoints with optional query parameters, Advanced Alchemy's filter helpers turn user input into safe SQL conditions:

.. tab-set::

    .. tab-item:: Text Search

        .. code-block:: python

            async def search_posts(db_session: AsyncSession, query: str) -> list[FilteringPost]:
                repo = FilteringPostRepository(session=db_session)
                return await repo.get_many(
                    SearchFilter(field_name="title", value=query, ignore_case=True),
                )

            literal_discount = SearchFilter(
                field_name="title",
                value="50% off",
                escape_wildcards=True,
            )

    .. tab-item:: ID Lists

        .. code-block:: python

            async def get_selected_posts(
                db_session: AsyncSession,
                post_ids: list[int],
            ) -> list[FilteringPost]:
                repo = FilteringPostRepository(session=db_session)
                return await repo.get_many(
                    CollectionFilter(field_name="id", values=post_ids),
                )

    .. tab-item:: Empty vs. Filled

        .. code-block:: python

            async def list_drafts_and_published(
                db_session: AsyncSession,
            ) -> tuple[list[FilteringPost], list[FilteringPost]]:
                repo = FilteringPostRepository(session=db_session)
                drafts = await repo.get_many(NullFilter(field_name="published_at"))
                live = await repo.get_many(NotNullFilter(field_name="published_at"))
                return drafts, live

.. tip::

    Set ``escape_wildcards=True`` on ``SearchFilter`` when searching text that may contain literal ``%`` or ``_`` characters (such as ``"50% off"``) on databases that support SQL ``ESCAPE``.

Paginating Results
------------------

Combine ``LimitOffset`` with ``get_many_and_count`` to get both the current page of rows and the total matching row count for your UI's page switcher:

.. code-block:: python

    async def get_posts_page(
        db_session: AsyncSession,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FilteringPost], int]:
        repo = FilteringPostRepository(session=db_session)
        offset = (page - 1) * page_size
        return await repo.get_many_and_count(LimitOffset(offset=offset, limit=page_size))

Naming URL Query Parameters
---------------------------

In Litestar and FastAPI, filter dependencies use camelCase query parameters by default (``?pageSize=10&searchString=python``). Set ``alias_generator="snake_case"`` in ``FilterConfig`` when your API prefers ``?page_size=10&search_string=python``:

.. code-block:: python

    from advanced_alchemy.utils.dependencies import FilterConfig

    snake_case_filters: FilterConfig = {
        "pagination_type": "limit_offset",
        "search": "title",
        "sort_field": "created_at",
        "alias_generator": "snake_case",
    }

If you use :doc:`read replicas </usage/routing>`, any read or count call can also target a named replica pool with ``bind_group="analytics"``:

.. code-block:: python

    async def list_for_reporting(db_session: AsyncSession) -> list[FilteringPost]:
        repo = FilteringPostRepository(session=db_session)
        return await repo.get_many(bind_group="analytics")

Filtering Across Relationships
------------------------------

Use :class:`~advanced_alchemy.filters.RelationshipFilter` to correlate conditions on related tables inside an ``EXISTS`` or ``NOT EXISTS`` subquery, or pass a relationship attribute directly to :class:`~advanced_alchemy.filters.CollectionFilter` and :class:`~advanced_alchemy.filters.NotInCollectionFilter`:

.. code-block:: python

    async def filter_posts_by_tags(
        db_session: AsyncSession,
        excluded_tag_ids: list[int],
    ) -> list[FilteringPost]:
        repo = FilteringPostRepository(session=db_session)
        return await repo.get_many(
            RelationshipFilter(
                relationship=FilteringPost.tags,
                filters=[ComparisonFilter(field_name=FilteringTag.slug, operator="eq", value="python")],
            ),
            NotInCollectionFilter(field_name=FilteringPost.tags, values=excluded_tag_ids),
        )

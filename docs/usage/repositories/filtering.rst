========================
Filtering and Pagination
========================

Repository query methods accept both SQLAlchemy column expressions and reusable :class:`~advanced_alchemy.filters.StatementFilter` objects without manual conditional ``.where()`` and ``.limit()`` chaining.

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
        InCollectionFilter,
        ComparisonFilter,
        LimitOffsetFilter,
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

Pass SQLAlchemy column expressions directly to ``get_many`` or ``get_many_and_count``:

.. code-block:: python

    async def get_recent_posts(db_session: AsyncSession) -> list[FilteringPost]:
        cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=7)
        repo = FilteringPostRepository(session=db_session)
        return await repo.get_many(FilteringPost.published.is_(True), FilteringPost.created_at >= cutoff)

Built-In Filter Helpers
-----------------------

.. tab-set::

    .. tab-item:: Text Search

        .. code-block:: python

            async def search_posts(db_session: AsyncSession, query: str) -> list[FilteringPost]:
                repo = FilteringPostRepository(session=db_session)
                return await repo.get_many(SearchFilter(field_name="title", value=query, ignore_case=True))

            literal_discount = SearchFilter(field_name="title", value="50% off", escape_wildcards=True)

    .. tab-item:: ID Lists

        .. code-block:: python

            async def get_selected_posts(db_session: AsyncSession, post_ids: list[int]) -> list[FilteringPost]:
                repo = FilteringPostRepository(session=db_session)
                return await repo.get_many(InCollectionFilter(field_name="id", values=post_ids))

    .. tab-item:: Empty vs. Filled

        .. code-block:: python

            async def list_drafts_and_published(db_session: AsyncSession) -> tuple[list[FilteringPost], list[FilteringPost]]:
                repo = FilteringPostRepository(session=db_session)
                drafts = await repo.get_many(NullFilter(field_name="published_at"))
                live = await repo.get_many(NotNullFilter(field_name="published_at"))
                return drafts, live

.. tip::

    Set ``escape_wildcards=True`` on ``SearchFilter`` when searching literal ``%`` or ``_`` characters on dialects that support SQL ``ESCAPE``.

Paginating Results
------------------

Combine ``LimitOffsetFilter`` with ``get_many_and_count`` for both page rows and total matching counts. By default (``count_with_window_function=True``), ``get_many_and_count`` runs a single query using an analytical ``COUNT(*) OVER()`` window function. Pass ``count_with_window_function=False`` (per call, or as a class default on your repository or service) to run two focused queries (an indexed page ``SELECT`` and a separate ``COUNT(*)``), avoiding extra sorting or scattered heap reads on large sorted tables or random/UUID primary keys (Cloud Spanner always uses the two-query path):

.. code-block:: python

    async def get_posts_page(db_session: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[list[FilteringPost], int]:
        repo = FilteringPostRepository(session=db_session)
        return await repo.get_many_and_count(
            LimitOffsetFilter(offset=(page - 1) * page_size, limit=page_size),
            count_with_window_function=False,
        )

.. warning::

    ``count_with_window_function`` currently defaults to ``True`` in 1.x and is planned to change to ``False`` in v2.0. Set ``count_with_window_function=False`` explicitly where two-query pagination performs better, or ``True`` to preserve single-query counting after upgrading.

For deep pages, infinite scroll, or tables with frequent inserts, use :doc:`cursor_pagination` instead.

Naming URL Query Parameters
---------------------------

Litestar and FastAPI filter dependencies use camelCase parameters by default (``?pageSize=10&searchString=python``). Set ``alias_generator="snake_case"`` when your API prefers ``?page_size=10``:

.. code-block:: python

    from advanced_alchemy.utils.dependencies import FilterConfig

    snake_case_filters: FilterConfig = {
        "pagination_type": "limit_offset",
        "search": "title",
        "sort_field": "created_at",
        "alias_generator": "snake_case",
    }

Filtering Across Relationships
------------------------------

Use :class:`~advanced_alchemy.filters.RelationshipFilter` to correlate related predicates inside ``EXISTS`` / ``NOT EXISTS``, or pass a relationship attribute to :class:`~advanced_alchemy.filters.InCollectionFilter` and :class:`~advanced_alchemy.filters.NotInCollectionFilter`:

.. code-block:: python

    async def filter_posts_by_tags(db_session: AsyncSession, excluded_tag_ids: list[int]) -> list[FilteringPost]:
        repo = FilteringPostRepository(session=db_session)
        return await repo.get_many(
            RelationshipFilter(
                relationship=FilteringPost.tags,
                filters=[ComparisonFilter(field_name=FilteringTag.slug, operator="eq", value="python")],
            ),
            NotInCollectionFilter(field_name=FilteringPost.tags, values=excluded_tag_ids),
        )

For structured JSON/dict query payloads, :class:`~advanced_alchemy.filters.MultiFilter` accepts ``allowed_relationships``, ``allowed_fields``, ``max_depth``, and ``strict=True`` to restrict permitted fields and nesting depth.

Field Filtering and Sorting
---------------------------

Declare ``filter_fields`` and ``sort_fields`` in ``FilterConfig`` so Litestar and FastAPI infer column operators, group dotted relationship parameters into one ``RelationshipFilter``, and validate repeatable ``orderBy`` (``-col`` descending):

.. code-block:: python

    field_filters: FilterConfig = {
        "filter_fields": {
            "title": {"contains", "eq"},
            "published": {"eq"},
            "published_at": {"ge", "lt", "is_null"},
            "tags.slug": {"in"},
        },
        "sort_fields": {"title", "published_at"},
        "pagination_type": "limit_offset",
        "pagination_max_size": 100,
    }

Frontend grids such as TanStack Table, AG Grid, and MUI Data Grid map column filters directly to ``?titleContains=sql&publishedAtIsNull=false&tagsSlugIn=python&orderBy=-published_at&orderBy=title&currentPage=2&pageSize=25``. Set ``pagination_max_size`` (default ``None``) to cap ``pageSize``/``page_size`` via OpenAPI ``maximum`` and framework validation (400 in Litestar, 422 in FastAPI); when ``pagination_size`` is omitted, the default page size is clamped to ``pagination_max_size`` (and setting ``pagination_size`` above ``pagination_max_size`` raises ``ImproperConfigurationError``).

See :doc:`filtersets` for reusable class-based filters and automatic relationship loading.

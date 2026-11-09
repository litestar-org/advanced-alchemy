============================================
Relationship Filtering and Declarative Sets
============================================

Advanced Alchemy provides two complementary surfaces for filtering across related tables and URL query strings:

#. :class:`~advanced_alchemy.filters.RelationshipFilter` emits correlated ``EXISTS`` / ``NOT EXISTS`` subqueries for one-to-many, many-to-many, and nested relationship paths in a single database query.
#. :class:`~advanced_alchemy.filters.FilterSet` is a declarative filter container that maps double-underscore query parameters (``title__icontains``, ``author__name__iexact``) onto statement filters and OpenAPI 3 parameter schemas, validating every path against the SQLAlchemy mapper at import time.

Example Setup
-------------

.. code-block:: python

    from uuid import UUID
    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.filters import (
        CollectionFilter,
        ComparisonFilter,
        FilterSet,
        LimitOffset,
        MultiFilter,
        NumberFilter,
        OrderingFilter,
        RelationshipFilter,
        StringFilter,
    )
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    rel_post_tags = Table(
        "rel_post_tags",
        UUIDBase.metadata,
        Column("post_id", ForeignKey("rel_post.id"), primary_key=True),
        Column("tag_id", ForeignKey("rel_tag.id"), primary_key=True),
    )


    class RelAuthor(UUIDBase):
        __tablename__ = "rel_author"

        name: Mapped[str]
        country: Mapped[str]
        posts: Mapped[list["RelPost"]] = relationship(back_populates="author")


    class RelTag(UUIDBase):
        __tablename__ = "rel_tag"

        slug: Mapped[str]


    class RelPost(UUIDBase):
        __tablename__ = "rel_post"

        title: Mapped[str]
        views: Mapped[int] = mapped_column(default=0)
        published: Mapped[bool] = mapped_column(default=False)
        author_id: Mapped[UUID] = mapped_column(ForeignKey("rel_author.id"))
        author: Mapped[RelAuthor] = relationship(back_populates="posts")
        tags: Mapped[list[RelTag]] = relationship(secondary=rel_post_tags)


    class RelPostRepository(SQLAlchemyAsyncRepository[RelPost]):
        model_type = RelPost


    class RelAuthorRepository(SQLAlchemyAsyncRepository[RelAuthor]):
        model_type = RelAuthor

Correlated Relationship Filters
-------------------------------

:class:`~advanced_alchemy.filters.RelationshipFilter` correlates inner filters against a related model and emits a single ``EXISTS`` subquery across forward, reverse, many-to-many, and nested relationships:

.. tab-set::

    .. tab-item:: Many-to-One & Many-to-Many

        .. code-block:: python

            async def filter_by_author_and_tags(
                db_session: AsyncSession,
                tag_ids: list[UUID],
            ) -> list[RelPost]:
                repo = RelPostRepository(session=db_session)
                return await repo.list(
                    RelationshipFilter(
                        relationship="author",
                        filters=[ComparisonFilter(field_name="name", operator="eq", value="Ada")],
                    ),
                    RelationshipFilter(
                        relationship="tags",
                        filters=[CollectionFilter(field_name="slug", values=["python", "rust"])],
                    ),
                    CollectionFilter(field_name=RelPost.tags, values=tag_ids),
                )

    .. tab-item:: Negated & JSON Multi-Filter

        .. code-block:: python

            async def authors_without_published_posts(
                db_session: AsyncSession,
            ) -> list[RelAuthor]:
                repo = RelAuthorRepository(session=db_session)
                return await repo.list(
                    RelationshipFilter(
                        relationship="posts",
                        filters=[ComparisonFilter(field_name="published", operator="eq", value=True)],
                        negate=True,
                    ),
                )


            json_filter = MultiFilter(
                filters={
                    "and_": [
                        {
                            "type": "relationship",
                            "relationship": "author",
                            "negate": False,
                            "filters": [
                                {"type": "comparison", "field_name": "name", "operator": "eq", "value": "Ada"},
                            ],
                        },
                    ],
                },
            )

.. note::

    Passing a relationship attribute directly to :class:`~advanced_alchemy.filters.CollectionFilter` (``CollectionFilter(field_name=RelPost.tags, values=tag_ids)``) automatically delegates to :class:`~advanced_alchemy.filters.RelationshipFilter` over the related primary key.

Declarative Filter Sets
-----------------------

Subclass :class:`~advanced_alchemy.filters.FilterSet` to declare filterable fields, allowed lookups, and permitted relationship paths:

.. code-block:: python

    class RelPostFilter(FilterSet):
        title = StringFilter(lookups=["exact", "icontains"])
        views = NumberFilter(type_=int, lookups=["gt", "lt", "between"])
        author__name = StringFilter(lookups=["exact", "iexact"])
        order_by = OrderingFilter(allowed=["views", "title"])

        class Meta:
            model = RelPost
            allowed_relationships = ("author",)


    parsed = RelPostFilter.from_query_params(
        {"title__icontains": "alchemy", "views__between": "10,100", "author__name__iexact": "ada", "order_by": "-views,title"},
    )
    assert len(parsed.to_filters()) == 4
    assert any(param["name"] == "author__name__iexact" for param in RelPostFilter().to_openapi_parameters())


    async def list_filtered_posts(db_session: AsyncSession, query_params: dict[str, str]) -> list[RelPost]:
        repo = RelPostRepository(session=db_session)
        filter_set = RelPostFilter.from_query_params(query_params)
        return await repo.list(*filter_set.to_filters(), LimitOffset(limit=20, offset=0))

Built-In Field Filters and Meta Options
---------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Class / Option
     - Supported Lookups & Behavior
   * - :class:`~advanced_alchemy.filters.StringFilter`
     - ``exact``, ``iexact``, ``contains``, ``icontains``, ``startswith``, ``istartswith``, ``endswith``, ``iendswith``, ``in``, ``not_in``, ``isnull``
   * - :class:`~advanced_alchemy.filters.NumberFilter`
     - ``exact``, ``gt``, ``gte``, ``lt``, ``lte``, ``between``, ``in``, ``not_in``, ``isnull`` (coerces ``int``, ``float``, or ``Decimal`` via ``type_``)
   * - :class:`~advanced_alchemy.filters.BooleanFilter`
     - ``exact``, ``isnull`` (accepts ``true``/``false``, ``1``/``0``, ``yes``/``no``, ``on``/``off``)
   * - :class:`~advanced_alchemy.filters.DateFilter` / :class:`~advanced_alchemy.filters.DateTimeFilter`
     - ``exact``, ``gt``, ``gte``, ``lt``, ``lte``, ``between``, ``year``, ``month``, ``day`` (plus ``hour``, ``minute``, ``second`` on ``DateTimeFilter``), ``in``, ``not_in``, ``isnull``
   * - :class:`~advanced_alchemy.filters.UUIDFilter` / :class:`~advanced_alchemy.filters.EnumFilter`
     - ``exact``, ``in``, ``not_in``, ``isnull``
   * - :class:`~advanced_alchemy.filters.OrderingFilter`
     - Comma-separated column names (``-`` prefix for descending), restricted by ``allowed=[...]`` and always emitted last
   * - ``Meta.model`` / ``Meta.allowed_relationships``
     - Required target declarative model and explicit allowlist of relationship segments permitted in ``__`` paths (bounded by ``Meta.max_relationship_depth=2``)
   * - ``Meta.strict`` / ``Meta.auto_fields``
     - Set ``strict=True`` to raise :class:`~advanced_alchemy.exceptions.FilterValidationError` on unknown keys; use ``auto_fields`` and ``auto_lookups`` to generate filters from model columns

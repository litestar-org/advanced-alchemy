===================
Declarative Filters
===================

Use :class:`~advanced_alchemy.filters.FilterSet` to group allowed query fields,
sorting and relationship loading for one mapped model.

Example Setup
-------------

.. code-block:: python

    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.filters import ComparisonFilter
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    filterset_post_tag = Table(
        "filterset_post_tag", BigIntAuditBase.metadata,
        Column("post_id", ForeignKey("filterset_post.id"), primary_key=True),
        Column("tag_id", ForeignKey("filterset_tag.id"), primary_key=True),
    )


    class FilterSetTag(BigIntAuditBase):
        __tablename__ = "filterset_tag"
        slug: Mapped[str]


    class FilterSetPost(BigIntAuditBase):
        __tablename__ = "filterset_post"
        title: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        published_at: Mapped[int] = mapped_column(default=0)
        tags: Mapped[list[FilterSetTag]] = relationship(secondary=filterset_post_tag)


    class FilterSetPostRepository(SQLAlchemyAsyncRepository[FilterSetPost]):
        pass

Reusable FilterSets
-------------------

Use :class:`~advanced_alchemy.filters.FilterSet` to keep allowed query fields,
search, sorting, and pagination together. Pass an instance directly to a repository
or service read method:

.. code-block:: python

    from advanced_alchemy.filters import FilterSet


    class PostFilters(FilterSet[FilterSetPost]):
        filter_fields = {
            "title": {"contains", "eq"},
            "published": {"eq"},
            "tags.slug": {"eq", "in"},
        }
        sort_fields = {"title", "published_at"}
        search_fields = {"title", "tags.slug"}
        config = {"pagination_type": "limit_offset", "pagination_size": 20, "pagination_max_size": 100}


    async def find_filtered_posts(db_session: AsyncSession) -> list[FilterSetPost]:
        repository = FilterSetPostRepository(session=db_session)
        filters = PostFilters(title__contains="python", tags__slug__eq="sqlalchemy")
        return await repository.get_many(filters)

The generic argument supplies the mapped model; ``model_type`` can also be set
explicitly. FilterSet construction takes typed Python values. Framework providers
validate and convert HTTP query values. Pydantic remains optional. Set
``pagination_max_size`` (default ``None``) in ``config`` or on the class to cap
``pageSize``/``page_size``; oversized values raise ``ValueError`` when instantiating
a FilterSet and HTTP 400/422 through Litestar or FastAPI. When ``pagination_size``
is omitted, the default page size is clamped to ``pagination_max_size``, and
``pagination_size > pagination_max_size`` raises ``ImproperConfigurationError``.
Set ``"pagination_type": "cursor"`` to accept a ``cursor`` value instead of ``page``;
see :doc:`cursor_pagination`.

Field parameters use double underscores to separate relationship names, the field,
and the operator: ``?tags__slug__eq=sqlalchemy&title__contains=python``. A deeper
path such as ``orders__items__price__ge=10`` follows the corresponding configured
``orders.items.price`` path. Only declared fields and operators are accepted.
Existing ``FilterConfig`` dictionaries keep their own parameter aliases and behavior.

Matching Related Rows
~~~~~~~~~~~~~~~~~~~~~

Operators on one field describe one matching value. For example,
``orders__items__price__ge=10&orders__items__price__le=20`` requires an item priced
between 10 and 20. Filters on different fields match independently:
``orders__status__eq=paid`` may match a different order from the matching item.
This lets each frontend control send its own field, operator, and value.

Deep relationship filters compile into nested correlated ``EXISTS`` expressions
inside one SQL statement. When several fields must match the same related row,
construct an explicit :class:`~advanced_alchemy.filters.RelationshipFilter` containing
those predicates instead.

Loading Relationships
~~~~~~~~~~~~~~~~~~~~~~

Passing a FilterSet directly to a read method also loads relationships referenced
by active field filters, search, and sorting. To-one paths use joined eager loading;
collections use select-in loading. SQL Server collections whose parent has a
composite primary key use subquery loading with deterministic pagination ordering.
Explicit ``load=`` options take precedence on overlapping paths.

Loaded collections retain all members allowed by existing loader criteria;
filtering a post by a matching tag does not restrict its loaded ``tags`` to that tag.
Relationships used only by response serialization still need explicit ``load=``
options. Set ``auto_load = False`` on the FilterSet class to disable inferred loading.

For explicit integration, ``filters.to_statement_filters()`` returns the ordinary
filter objects and ``filters.load`` returns the inferred loading options. Expanding
only the filter list omits the automatic-loading metadata:

.. code-block:: python

    async def find_posts_with_explicit_filters(db_session: AsyncSession) -> list[FilterSetPost]:
        repository = FilterSetPostRepository(session=db_session)
        filters = PostFilters(tags__slug__eq="sqlalchemy")
        return await repository.get_many(*filters.to_statement_filters(), load=filters.load)

DuckDB can raise an internal database error when UUID-correlated ``EXISTS`` filters
are combined with a window-function count. For that query shape, call
``get_many_and_count(filters, count_with_window_function=False)`` to use separate
data and count queries.

Custom Filter Methods
~~~~~~~~~~~~~~~~~~~~~~

Add a typed ``filter_<name>`` method for application-specific filtering. The method
returns an existing filter object, a supported SQLAlchemy predicate, or ``None``
to omit the condition:

.. code-block:: python

    class PublishedPostFilters(PostFilters):
        def filter_only_published(self, value: bool) -> ComparisonFilter:
            return ComparisonFilter(field_name="published", operator="eq", value=value)


    only_published = PublishedPostFilters(only_published=True)

The custom method's argument annotation supplies the query value type. Custom SQL
predicates must be supported by the in-memory evaluator when using mock repositories.

Framework Providers
~~~~~~~~~~~~~~~~~~~~

Pass the FilterSet class to the existing providers; it supplies its own model:

.. code-block:: python

    from advanced_alchemy.extensions.fastapi.providers import provide_filters
    from advanced_alchemy.extensions.litestar.providers import create_service_dependencies
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService


    class FilterSetPostService(SQLAlchemyAsyncRepositoryService[FilterSetPost]):
        pass


    post_dependencies = create_service_dependencies(FilterSetPostService, "posts", filters=PostFilters)
    post_filter_dependency = provide_filters(PostFilters)

FastAPI's dependency yields the usual filter list; pass it with ``*filters`` to a
repository or service. Litestar service bundles expose the usual aggregate filter
dependency. For a ``ServiceGroup``, configure each member independently with
``filters={"posts": PostFilters}``. Generated field parameters use the FilterSet's
double-underscore names in both frameworks' OpenAPI schemas.

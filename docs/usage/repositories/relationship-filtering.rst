============================================
Relationship Filtering and Declarative ``FilterSet``
============================================

.. versionadded:: 1.10

Advanced Alchemy provides two complementary surfaces for filtering by
related-model fields:

#. **Tier 1 — engine.** :class:`~advanced_alchemy.filters.RelationshipFilter`
   produces a correlated ``EXISTS`` subquery for one-to-many, many-to-many,
   and nested relationship paths. This is the SQL primitive that closes
   `Issue #364 <https://github.com/litestar-org/advanced-alchemy/issues/364>`_
   (no more two-query workarounds) and
   `Issue #505 <https://github.com/litestar-org/advanced-alchemy/issues/505>`_
   (``CollectionFilter`` over many-to-many now compiles to correct SQL).
#. **Tier 2 — declarative ``FilterSet``.** A class-based filter container
   that maps query-string parameters onto Tier 1 filters using the familiar
   double-underscore lookup syntax (``title__icontains``, ``author__name__iexact``,
   ``tags__slug__in``). Every declared field, lookup, and relationship path is
   validated against the ORM model at import time so misconfiguration shows up
   as soon as the application starts, not when a request arrives.

Both surfaces compile down to the same SQL primitives, are framework-agnostic,
and are safe to combine with the existing
:class:`~advanced_alchemy.filters.LimitOffset`,
:class:`~advanced_alchemy.filters.SearchFilter`, and other filter primitives.

----

Tier 1: ``RelationshipFilter``
==============================

:class:`~advanced_alchemy.filters.RelationshipFilter` correlates a list of
inner filters against a related table and emits a single ``EXISTS`` subquery.
It works uniformly for forward and reverse one-to-many relationships,
many-to-many relationships (using the ``secondary`` association), and any
arbitrary nesting depth.

Forward one-to-many (parent filtered by child)
----------------------------------------------

.. code-block:: python

    from advanced_alchemy.filters import RelationshipFilter, ComparisonFilter

    # Posts whose author's name equals "Ada"
    posts = await post_repo.list(
        RelationshipFilter(
            relationship="author",
            filters=[ComparisonFilter(field_name="name", operator="eq", value="Ada")],
        ),
    )

Many-to-many
------------

For relationships using ``secondary``, ``RelationshipFilter`` traverses both
the primary and secondary joins; the caller does not need to know whether the
relationship is direct or M2M.

.. code-block:: python

    from advanced_alchemy.filters import RelationshipFilter, CollectionFilter

    # Posts having any tag whose slug is "python" or "rust"
    posts = await post_repo.list(
        RelationshipFilter(
            relationship="tags",
            filters=[CollectionFilter(field_name="slug", values=["python", "rust"])],
        ),
    )

Nested relationships
--------------------

Nest by passing a ``RelationshipFilter`` inside another ``RelationshipFilter``.
Each level produces another ``EXISTS`` correlation; SQLAlchemy keeps the whole
expression in a single ``SELECT``.

.. code-block:: python

    from advanced_alchemy.filters import RelationshipFilter, CollectionFilter

    # Posts written by authors whose organization is in the USA
    posts = await post_repo.list(
        RelationshipFilter(
            relationship="author",
            filters=[
                RelationshipFilter(
                    relationship="organization",
                    filters=[
                        CollectionFilter(field_name="country_code", values=["US"]),
                    ],
                ),
            ],
        ),
    )

Negation
--------

Pass ``negate=True`` to emit ``NOT EXISTS``.

.. code-block:: python

    # Authors with no published posts
    authors = await author_repo.list(
        RelationshipFilter(
            relationship="posts",
            filters=[ComparisonFilter(field_name="published", operator="eq", value=True)],
            negate=True,
        ),
    )

``CollectionFilter`` over many-to-many
--------------------------------------

When ``CollectionFilter`` is constructed over a relationship attribute (rather
than a scalar column), it now detects the relationship and delegates to a
synthesized ``RelationshipFilter`` over the related primary key. This restores
the intuitive behaviour for many-to-many filtering and closes Issue #505.

.. code-block:: python

    from advanced_alchemy.filters import CollectionFilter

    # Posts tagged with one of the given tag IDs (M2M; transparently delegates)
    posts = await post_repo.list(
        CollectionFilter(field_name=Post.tags, values=[tag_uuid_1, tag_uuid_2]),
    )

The scalar-column path is unchanged — passing a column attribute or a column
name continues to compile to ``IN``/``NOT IN`` exactly as before.

JSON-driven filtering with ``MultiFilter``
------------------------------------------

:class:`~advanced_alchemy.filters.MultiFilter` accepts ``"relationship"`` as a
filter type, so a fully JSON-serializable filter tree can express relationship
correlation without any Python-level filter-class instantiation.

.. code-block:: python

    from advanced_alchemy.filters import MultiFilter

    payload = {
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
    }
    posts = await post_repo.list(MultiFilter(filters=payload))

----

Tier 2: ``FilterSet``
=====================

:class:`~advanced_alchemy.filters.FilterSet` is the declarative facade. A
``FilterSet`` subclass declares which fields are filterable, which lookups are
allowed per field, and which relationship paths the API exposes. Once
declared, the same class drives query-parameter parsing, SQL generation, and
OpenAPI schema emission.

Quick start
-----------

.. code-block:: python

    from advanced_alchemy.filters import (
        FilterSet,
        NumberFilter,
        OrderingFilter,
        StringFilter,
    )


    class PostFilter(FilterSet):
        title = StringFilter(lookups=["exact", "icontains"])
        views = NumberFilter(type_=int, lookups=["gt", "lt", "between"])
        author__name = StringFilter(lookups=["iexact"])
        order_by = OrderingFilter(allowed=["views", "title", "created_at"])

        class Meta:
            model = Post
            allowed_relationships = ["author"]

Use the class to parse a query-parameter mapping, then hand the result to a
repository or service:

.. code-block:: python

    # Inside a route handler — works with any framework's query-param mapping
    instance = PostFilter.from_query_params(request.query_params)
    posts = await post_repo.list(*instance.to_filters())

The same instance also produces an OpenAPI parameter list:

.. code-block:: python

    PostFilter().to_openapi_parameters()
    # → list of OpenAPI 3 parameter objects, ready to merge into a route schema

Lookup syntax
-------------

Query parameters use double-underscore (``__``) to separate the field path
from the trailing lookup. The bare form (no trailing lookup) uses the field
filter's default lookup.

================================  ================================  ================================================
Query parameter                   Compiles to                       SQL effect
================================  ================================  ================================================
``?title=hello``                  ``ComparisonFilter("title","eq")``  ``WHERE title = 'hello'``
``?title__icontains=py``          ``SearchFilter`` (case-insensitive) ``WHERE LOWER(title) LIKE LOWER('%py%')``
``?views__gt=10``                 ``ComparisonFilter("views","gt")``  ``WHERE views > 10``
``?views__between=10,99``         ``ComparisonFilter`` (between)      ``WHERE views BETWEEN 10 AND 99``
``?status__in=draft,published``   ``CollectionFilter``                ``WHERE status IN ('draft','published')``
``?author__name__iexact=ada``     ``RelationshipFilter`` + ILIKE      ``WHERE EXISTS (... ILIKE 'ada')``
``?order_by=-views,title``        :class:`OrderingApply`              ``ORDER BY views DESC, title ASC``
================================  ================================  ================================================

Built-in field filters
----------------------

================================  ===============================================================
Filter class                      Lookups
================================  ===============================================================
:class:`StringFilter`             ``exact, iexact, contains, icontains, startswith, istartswith,
                                  endswith, iendswith, in, not_in, isnull``
:class:`NumberFilter`             ``exact, gt, gte, lt, lte, between, in, not_in, isnull``
:class:`BooleanFilter`            ``exact, isnull``
:class:`DateFilter`               ``exact, gt, gte, lt, lte, between, year, month, day, in,
                                  not_in, isnull``
:class:`DateTimeFilter`           Adds ``hour, minute, second`` to ``DateFilter``.
:class:`UUIDFilter`               ``exact, in, not_in, isnull``
:class:`EnumFilter`               ``exact, in, not_in, isnull`` (accepts member name or value)
:class:`OrderingFilter`           Comma-separated, ``-`` prefix is descending; restricted by
                                  ``allowed=[...]``.
================================  ===============================================================

By default a field filter accepts every lookup in its catalog. Pass
``lookups=[...]`` to constrain the surface — values outside the explicit list
are rejected at parse time, and any constrained lookups are also omitted from
the OpenAPI schema.

Coercion rules:

* ``isnull`` accepts ``true``/``false``/``1``/``0``/``yes``/``no``/``on``/``off``.
* ``in`` / ``not_in`` accept a comma-separated string or repeated keys
  (``?x=a&x=b`` → ``["a", "b"]``).
* ``between`` requires exactly two values, comma-separated.
* :class:`NumberFilter` accepts ``int``/``float``/``Decimal`` via the
  ``type_=`` argument and rejects non-numeric input with ``ValueError``.
* :class:`DateFilter` / :class:`DateTimeFilter` accept ISO-8601 strings.
* :class:`EnumFilter` accepts either the enum's value (``"red"``) or its
  member name (``"RED"``).
* :class:`UUIDFilter` rejects malformed UUID strings.

Meta options
------------

================================  ===============================================================
``Meta.model``                    *(required)* The :class:`DeclarativeBase` model the FilterSet
                                  resolves field paths against.
``Meta.allowed_relationships``    Iterable of relationship segment names that may appear in field
                                  paths. Empty by default — fields without relationship segments
                                  always work; declaring ``author__name`` requires ``"author"``
                                  here.
``Meta.max_relationship_depth``   Cap on the number of relationship segments in any field path.
                                  Defaults to ``3`` to bound query plan complexity.
``Meta.strict``                   When ``True``, any unknown query-parameter key raises
                                  :class:`FilterValidationError`. Default ``False`` (silently
                                  ignored).
``Meta.auto_fields``              Iterable of column names to auto-declare with
                                  ``auto_lookups`` (saves declaring every column individually).
``Meta.auto_lookups``             Mapping from column name (or ``"*"``) to a sequence of allowed
                                  lookups for the ``auto_fields`` declarations.
================================  ===============================================================

Validation runs at import time. The most common errors:

* a field path resolves to a relationship segment not listed in
  ``Meta.allowed_relationships``;
* the path traverses more than ``Meta.max_relationship_depth`` relationships;
* the leaf segment is not a column or relationship of the resolved model;
* a lookup is not in the field filter's :attr:`supported_lookups`.

Each surfaces as :class:`ImproperConfigurationError` with a message that
identifies the offending field declaration.

Compilation order
-----------------

:meth:`FilterSet.to_filters` walks the populated invocations in declaration
order, calls each field filter's ``compile``, and wraps the resulting Tier 1
leaf in nested :class:`RelationshipFilter` instances when the path crosses
relationship segments. :class:`OrderingFilter` always emits last so the
``WHERE`` clause stays stable across runs and so a leading ``ORDER BY`` is
never produced.

Composition with other filters
------------------------------

The list returned by :meth:`to_filters` is interchangeable with any other
sequence of statement filters. Combine with pagination, search, and
hand-rolled filters as usual:

.. code-block:: python

    instance = PostFilter.from_query_params(request.query_params)
    page = LimitOffset(limit=20, offset=0)
    posts = await post_repo.list(*instance.to_filters(), page)

----

OpenAPI integration
===================

:meth:`FilterSet.to_openapi_parameters` returns a ``list[dict[str, Any]]`` of
OpenAPI 3 parameter objects. Each declared field × allowed lookup yields one
parameter (the bare field name when the lookup matches the field's default,
otherwise ``field__lookup``); array-valued lookups (``in``/``not_in``/
``between``) include ``style: form`` and ``explode: false`` so the
comma-separated wire format round-trips. :class:`OrderingFilter` emits a
single parameter whose enum lists every allowed value plus its
``-``-prefixed descending counterpart.

.. code-block:: python

    spec_fragment = {
        "parameters": PostFilter().to_openapi_parameters(),
    }

Framework integration providers (Litestar, FastAPI, Flask, Sanic, Starlette)
that bind a ``FilterSet`` directly to HTTP query parameters live in a separate
package and consume :meth:`from_query_params` and
:meth:`to_openapi_parameters` directly — no per-framework wiring is required
inside the ``FilterSet`` class itself.

----

Adoption guide
==============

From the two-query workaround to ``RelationshipFilter``
-------------------------------------------------------

**Before** — two repository round trips and a Python-side join:

.. code-block:: python

    usa_customers = await customer_repo.list(
        CollectionFilter(field_name="country", values=["US"]),
    )
    customer_ids = [c.id for c in usa_customers]
    orders = await order_repo.list(
        CollectionFilter(field_name="customer_id", values=customer_ids),
    )

**After** — one query, correlated ``EXISTS``:

.. code-block:: python

    orders = await order_repo.list(
        RelationshipFilter(
            relationship="customer",
            filters=[CollectionFilter(field_name="country", values=["US"])],
        ),
    )

From hand-rolled query parsing to ``FilterSet``
-----------------------------------------------

**Before** — every endpoint reinvents validation:

.. code-block:: python

    async def list_posts(request: Request) -> list[Post]:
        filters: list[StatementFilter] = []
        if title := request.query_params.get("title"):
            filters.append(SearchFilter(field_name="title", value=title, ignore_case=True))
        if min_views := request.query_params.get("min_views"):
            filters.append(ComparisonFilter("views", "gt", int(min_views)))
        # ...repeat for every other field, and every other endpoint...
        return await post_repo.list(*filters)

**After** — declare once, parse anywhere:

.. code-block:: python

    class PostFilter(FilterSet):
        title = StringFilter(lookups=["icontains"])
        views = NumberFilter(type_=int, lookups=["gt"])

        class Meta:
            model = Post


    async def list_posts(request: Request) -> list[Post]:
        instance = PostFilter.from_query_params(request.query_params)
        return await post_repo.list(*instance.to_filters())

Existing imperative use of :class:`CollectionFilter`,
:class:`SearchFilter`, :class:`ComparisonFilter`, and
:class:`MultiFilter` continues to work unchanged — both tiers are additive.

----

See also
========

* :doc:`filtering` — the canonical reference for non-relationship filters.
* :ref:`filters` API reference for every filter class and its options.
* `Issue #564 comment by MortezaKarimi77
  <https://github.com/litestar-org/advanced-alchemy/issues/564>`_, which seeded
  the declarative redesign.

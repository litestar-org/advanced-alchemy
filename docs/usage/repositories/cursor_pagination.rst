=================
Cursor Pagination
=================

Cursor (keyset) pagination fetches the rows after the last row a client saw instead of skipping rows with ``OFFSET``. Every page costs the same as the first, and rows inserted earlier in the ordering never shift later pages, which suits infinite scroll, feeds, exports, and large tables. It cannot jump to page *N*; use :class:`~advanced_alchemy.filters.LimitOffsetFilter` when clients need numbered pages.

Example Setup
-------------

.. code-block:: python

    from typing import Optional
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped
    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.filters import CursorFilter, CursorKey
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import CursorPagination


    class CursorPost(BigIntAuditBase):
        __tablename__ = "cursor_usage_post"

        title: Mapped[str]
        score: Mapped[int]
        rating: Mapped[Optional[int]]


    class CursorPostRepository(SQLAlchemyAsyncRepository[CursorPost]):
        model_type = CursorPost

Fetching a Page
---------------

:class:`~advanced_alchemy.filters.CursorFilter` takes the ordering keys, the page size, and the token from the previous page (``None`` for the first page). :meth:`~advanced_alchemy.filters.CursorFilter.build_page` turns the rows into a :class:`~advanced_alchemy.service.CursorPagination`:

.. code-block:: python

    async def get_posts_page(db_session: AsyncSession, cursor: Optional[str] = None) -> CursorPagination[CursorPost]:
        repo = CursorPostRepository(session=db_session)
        cursor_filter = CursorFilter([("score", "desc")], limit=20, cursor=cursor)
        rows = await repo.get_many(cursor_filter)
        return cursor_filter.build_page(rows, model=CursorPost)

The filter fetches ``limit + 1`` rows to learn whether another page exists; ``build_page`` drops the extra row. Services do the same in one call and convert the items to a schema:

.. code-block:: python

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService


    class CursorPostService(SQLAlchemyAsyncRepositoryService[CursorPost]):
        repository_type = CursorPostRepository


    async def list_posts(service: CursorPostService, cursor: Optional[str] = None) -> CursorPagination[CursorPost]:
        cursor_filter = CursorFilter([("score", "desc")], limit=20, cursor=cursor)
        rows = await service.get_many(cursor_filter)
        return service.to_schema(rows, filters=[cursor_filter], pagination_type="cursor")

``pagination_type="cursor"`` makes type checkers infer ``CursorPagination[...]``. Passing a ``CursorFilter`` without it raises :class:`~advanced_alchemy.exceptions.ImproperConfigurationError`, so a cursor page is never returned where an ``OffsetPagination`` is declared.

The response serializes as:

.. code-block:: json

    {
        "items": [{"id": 42, "title": "Keyset paging", "score": 9}],
        "limit": 20,
        "next_cursor": "eyJkIjoiZiIsImsiOltbImkiLDldLFsiaSIsNDJdXSwibyI6Ii4uLiIsInYiOjF9",
        "previous_cursor": null,
        "has_next": true,
        "has_previous": false
    }

Pass ``next_cursor`` back to fetch the following page and ``previous_cursor`` to fetch the preceding one. Both are ``None`` at the respective end.

Ordering Keys
-------------

Keys are column names, ``(name, "asc" | "desc")`` pairs, model attributes, or :class:`~advanced_alchemy.filters.CursorKey` objects. Bare names sort ascending. The model's primary key is appended as the final key, in the direction of the last declared key, so rows that share a value still have a unique position. An empty key list pages by primary key.

.. code-block:: python

    newest_first = CursorFilter([("created_at", "desc")], limit=50)
    by_rating = CursorFilter([CursorKey("rating", "desc", nulls="last"), "title"], limit=50)

Nullable key columns need a NULL placement for keyset comparisons to be correct; left as ``None``, NULLs sort last. Placement on non-nullable columns is ignored, so the database can serve the ordering from an index. Keys must be columns of the model; relationship paths are rejected.

The filter owns ordering and limits. It replaces the repository's default ``order_by`` and any ``ORDER BY``, ``LIMIT``, or ``OFFSET`` on the statement, and repositories reject it alongside :class:`~advanced_alchemy.filters.OrderByFilter`, :class:`~advanced_alchemy.filters.LimitOffsetFilter`, or a second cursor filter. Every other filter combines with it as usual.

.. tip::

    Index the keys in the same order and directions, ending with the primary key, for example ``(score DESC, id DESC)``. The keyset predicate and ``ORDER BY`` then read one contiguous index range per page.

Counting
--------

Cursor pages do not need a total. ``get_many`` runs one query. ``get_many_and_count`` also works: it counts the full filtered set with a separate ``COUNT(*)`` query, so the total is the same on every page.

Signed, Expiring, and Encrypted Tokens
--------------------------------------

Tokens are URL-safe and record the ordering they were issued for; a token reused with a different ordering is rejected. Without a secret, a token is readable base64 holding the key values of the page's edge rows, and clients can edit it. Pass ``secret`` to sign tokens, ``ttl`` to expire them, and ``encrypted=True`` to hide the values:

.. code-block:: python

    import datetime

    signed = CursorFilter("score", limit=20, secret="load-from-settings", ttl=datetime.timedelta(hours=1))
    sealed = CursorFilter("score", limit=20, secret="load-from-settings", encrypted=True)

Use a separate secret per resource or tenant when a token must not be accepted by another endpoint. Malformed, tampered, expired, or mismatched tokens raise :class:`~advanced_alchemy.exceptions.InvalidCursorError`, a ``ValueError`` and ``RepositoryError`` subclass.

Framework Dependencies
----------------------

Set ``pagination_type="cursor"`` in :class:`~advanced_alchemy.utils.dependencies.FilterConfig`. Litestar and FastAPI then accept ``cursor`` and ``pageSize``, plus ``orderBy`` and ``sortOrder`` when ``sort_field`` or ``sort_fields`` is set, validated against the same allowlist and ``pagination_max_size`` as limit/offset pagination:

.. code-block:: python

    from advanced_alchemy.utils.dependencies import FilterConfig

    cursor_filters: FilterConfig = {
        "pagination_type": "cursor",
        "pagination_size": 20,
        "pagination_max_size": 100,
        "sort_field": "created_at",
        "sort_fields": ["created_at", "score"],
        "sort_nulls": "last",
        "pagination_cursor_secret": "load-from-settings",
    }

Invalid tokens and sort fields return 400 in Litestar and 422 in FastAPI. :class:`~advanced_alchemy.filters.FilterSet` classes accept the same configuration and a ``cursor`` value. See :doc:`/usage/frameworks/litestar` and :doc:`/usage/frameworks/fastapi` for complete applications.

Custom Value Types
------------------

Tokens encode ``None``, booleans, numbers, ``Decimal``, strings, bytes, ``UUID``, dates and times, ``timedelta``, and enum members. Register any other key type once at start-up with :func:`~advanced_alchemy.filters.register_cursor_type`.

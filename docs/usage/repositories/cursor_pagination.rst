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

``to_schema`` returns a ``CursorPagination`` whenever ``filters`` hold a ``CursorFilter``, directly or inside a :class:`~advanced_alchemy.filters.FilterSet`. Type checkers cannot see which filters a list holds, so pass ``pagination_type="cursor"`` for them to infer ``CursorPagination[...]``; without it the call is typed as ``OffsetPagination[...]``. ``pagination_type="limit_offset"`` with a ``CursorFilter`` raises :class:`~advanced_alchemy.exceptions.ImproperConfigurationError`.

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

    A nullable key needs more care. PostgreSQL uses the index only when it declares the same NULL placement, for example ``(rating DESC NULLS LAST, id DESC)``. MySQL, MariaDB, and SQL Server sort NULLs first ascending and last descending; any other placement is ordered by an extra ``CASE`` expression that no index serves. On those databases, choose the native placement or a non-nullable key.

Counting
--------

Cursor pages do not need a total. ``get_many`` runs one query. ``get_many_and_count`` also works: it counts the full filtered set with a separate ``COUNT(*)`` query, so the total is the same on every page.

Signed, Expiring, and Encrypted Tokens
--------------------------------------

Tokens are URL-safe and record the ordering they were issued for; a token reused with a different ordering is rejected. Without a secret, a token is readable base64 holding the key values of the page's edge rows, and clients can edit it, including its expiry. Pass ``secret`` to sign tokens, ``ttl`` to expire them, and ``encrypted=True`` to hide the values:

.. code-block:: python

    import datetime

    signed = CursorFilter("score", limit=20, secret="load-from-settings", ttl=datetime.timedelta(hours=1))
    sealed = CursorFilter("score", limit=20, secret="load-from-settings", encrypted=True)

Use a separate secret per resource or tenant when a token must not be accepted by another endpoint. Both direct :class:`~advanced_alchemy.filters.CursorFilter` calls and framework dependencies derive signing and encryption keys from ``secret`` so tokens issued by either are interchangeable and never sign directly with the raw secret. Malformed, tampered, expired, or mismatched tokens raise :class:`~advanced_alchemy.exceptions.InvalidCursorError`, a ``ValueError`` and ``RepositoryError`` subclass.

Encrypted tokens (``encrypted=True``) use AES-256-GCM and require the optional ``cryptography`` extra. Enabling ``encrypted=True`` without ``cryptography`` installed raises :class:`~advanced_alchemy.exceptions.MissingDependencyError`.

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[cryptography]"

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[cryptography]"

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[cryptography]"

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[cryptography]"

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
    }

Framework dependencies always sign their tokens and raise :class:`~advanced_alchemy.exceptions.ImproperConfigurationError` on a cursor request when no secret is configured. Set the secret once on the SQLAlchemy configuration; every filter dependency and :class:`~advanced_alchemy.filters.FilterSet` of the application uses it:

.. code-block:: python

    from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

    config = SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://app@localhost/app",
        pagination_cursor_secret="load-from-settings",
    )

``pagination_cursor_ttl`` and ``pagination_cursor_encrypted`` are set the same way, and the FastAPI configuration takes the same options. Each option resolves from the ``FilterConfig`` or ``FilterSet`` first, then the SQLAlchemy configuration. The secret then falls back to the ``ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET`` and ``SECRET_KEY`` environment variables. An application with several configurations must give them the same values. Tokens are signed with a key derived from the secret, never the secret itself, so an application secret shared through ``SECRET_KEY`` keeps its other uses separate. Use the same secret in every worker process so a token issued by one is accepted by another.

Invalid tokens and sort fields return 400 in Litestar and 422 in FastAPI. :class:`~advanced_alchemy.filters.FilterSet` classes accept the same configuration and a ``cursor`` value. See :doc:`/usage/frameworks/litestar` and :doc:`/usage/frameworks/fastapi` for complete applications.

Custom Value Types
------------------

Tokens encode ``None``, booleans, numbers, ``Decimal``, strings, bytes, ``UUID``, dates and times, ``timedelta``, and enum members. An enum key needs a column type that names its enum class: :class:`sqlalchemy.types.Enum`, or a ``TypeDecorator`` whose ``python_type`` returns the class. Register any other key type once at start-up with :func:`~advanced_alchemy.filters.register_cursor_type`.

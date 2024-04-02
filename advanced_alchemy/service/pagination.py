from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")
C = TypeVar("C", int, str, UUID)


@dataclass
class ClassicPagination(Generic[T]):
    """Container for data returned using limit/offset pagination."""

    __slots__ = ("items", "page_size", "current_page", "total_pages")

    items: list[T]
    """List of data being sent as part of the response."""
    page_size: int
    """Number of items per page."""
    current_page: int
    """Current page number."""
    total_pages: int
    """Total number of pages."""


@dataclass
class OffsetPagination(Generic[T]):
    """Container for data returned using limit/offset pagination."""

    __slots__ = ("items", "limit", "offset", "total")

    items: list[T]
    """List of data being sent as part of the response."""
    limit: int
    """Maximal number of items to send."""
    offset: int
    """Offset from the beginning of the query.

    Identical to an index.
    """
    total: int
    """Total number of items."""


@dataclass
class CursorPagination(Generic[C, T]):
    """Container for data returned using cursor pagination."""

    __slots__ = ("items", "results_per_page", "cursor", "next_cursor")

    items: list[T]
    """List of data being sent as part of the response."""
    results_per_page: int
    """Maximal number of items to send."""
    cursor: C | None
    """Unique ID, designating the last identifier in the given data set.

    This value can be used to request the "next" batch of records.
    """

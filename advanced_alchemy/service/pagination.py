from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar, Union

from typing_extensions import TypeAlias

T = TypeVar("T")

__all__ = ("CursorPagination", "OffsetPagination", "Pagination")


@dataclass
class OffsetPagination(Generic[T]):
    """Container for data returned using limit/offset pagination."""

    __slots__ = ("items", "limit", "offset", "total")

    items: Sequence[T]
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
class CursorPagination(Generic[T]):
    __slots__ = ("items", "next_cursor")

    items: Sequence[T]
    next_cursor: Optional[str]


Pagination: TypeAlias = Union[CursorPagination[T], OffsetPagination[T]]

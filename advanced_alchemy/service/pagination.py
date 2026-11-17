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
    """Container for data returned using cursor (keyset) pagination."""

    __slots__ = ("has_next", "has_previous", "items", "limit", "next_cursor", "previous_cursor")

    items: Sequence[T]
    """List of data being sent as part of the response."""
    limit: int
    """Maximal number of items to send."""
    next_cursor: Optional[str]
    """Token for the following page, or ``None`` on the last page."""
    previous_cursor: Optional[str]
    """Token for the preceding page, or ``None`` on the first page."""
    has_next: bool
    """Whether a page exists after this one."""
    has_previous: bool
    """Whether a page exists before this one."""


Pagination: TypeAlias = Union[CursorPagination[T], OffsetPagination[T]]
"""Either pagination container."""

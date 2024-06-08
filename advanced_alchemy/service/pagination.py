from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar
from uuid import UUID

T = TypeVar("T")
C = TypeVar("C", int, str, UUID)

__all__ = ("OffsetPagination",)


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

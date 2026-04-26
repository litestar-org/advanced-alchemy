"""Service-side typing surface."""

from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from typing_extensions import TypeAlias, TypeVar

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ("ServiceProvider", "ServiceWithSession")

T = TypeVar("T")

ServiceProvider: TypeAlias = Callable[["AsyncSession"], AsyncGenerator[T, None]]
"""Callable that yields a service instance for a session."""


@runtime_checkable
class ServiceWithSession(Protocol):
    """Structural protocol for services constructible with ``session=``."""

    def __init__(self, *, session: "AsyncSession") -> None: ...

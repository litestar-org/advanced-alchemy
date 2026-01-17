"""Null cache region implementation for when dogpile.cache is not installed."""

from collections.abc import Awaitable
from typing import Any, Callable, Optional, Protocol, TypeVar

__all__ = (
    "NO_VALUE",
    "AsyncCacheRegionProtocol",
    "NullRegion",
    "SyncCacheRegionProtocol",
)

T = TypeVar("T")


class SyncCacheRegionProtocol(Protocol):
    """Protocol defining the synchronous cache region interface used by CacheManager.

    This protocol is compatible with both dogpile.cache.CacheRegion and NullRegion.
    """

    def get(self, key: str, expiration_time: Optional[int] = None) -> Any: ...

    def get_or_create(
        self,
        key: str,
        creator: Callable[[], T],
        expiration_time: Optional[int] = None,
    ) -> T: ...

    def set(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...

    def invalidate(self) -> None: ...

    def configure(
        self,
        backend: str,
        expiration_time: Optional[int] = None,
        arguments: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> "SyncCacheRegionProtocol": ...


class AsyncCacheRegionProtocol(Protocol):
    """Protocol defining the asynchronous cache region interface.

    This protocol defines async versions of cache region operations,
    suitable for use with native async cache backends.
    """

    async def get(self, key: str, expiration_time: Optional[int] = None) -> Any: ...

    async def get_or_create(
        self,
        key: str,
        creator: Callable[[], Awaitable[T]],
        expiration_time: Optional[int] = None,
    ) -> T: ...

    async def set(self, key: str, value: Any) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def invalidate(self) -> None: ...

    async def configure(
        self,
        backend: str,
        expiration_time: Optional[int] = None,
        arguments: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> "AsyncCacheRegionProtocol": ...


class _NoValue:
    """Sentinel value to indicate a cache miss.

    This is compatible with ``dogpile.cache.api.NO_VALUE`` and is used
    when dogpile.cache is not installed to maintain API compatibility.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<NO_VALUE>"


NO_VALUE: Any = _NoValue()


class NullRegion:
    """A no-op cache region that provides the same interface as dogpile.cache.CacheRegion.

    This class is used when dogpile.cache is not installed or when caching
    is disabled. All operations are no-ops that don't actually cache anything.

    The interface matches the subset of dogpile.cache.CacheRegion methods
    that are used by the CacheManager.
    """

    __slots__ = ()

    def get(self, key: str, expiration_time: Optional[int] = None) -> Any:
        """Get a value from the cache (always returns NO_VALUE).

        Args:
            key: The cache key.
            expiration_time: Ignored.

        Returns:
            Always returns NO_VALUE to indicate a cache miss.
        """
        return NO_VALUE

    def get_or_create(
        self,
        key: str,
        creator: Callable[[], T],
        expiration_time: Optional[int] = None,
    ) -> T:
        """Get or create a value (always calls the creator).

        Args:
            key: The cache key.
            creator: Function to create the value.
            expiration_time: Ignored.

        Returns:
            The result of calling the creator function.
        """
        return creator()

    def set(self, key: str, value: Any) -> None:
        """Set a value in the cache (no-op).

        Args:
            key: The cache key.
            value: The value to cache.
        """

    def delete(self, key: str) -> None:
        """Delete a value from the cache (no-op).

        Args:
            key: The cache key to delete.
        """

    def invalidate(self) -> None:
        """Invalidate all cached values (no-op)."""

    def configure(
        self,
        backend: str,
        expiration_time: Optional[int] = None,
        arguments: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> "NullRegion":
        """Configure the region (no-op, returns self).

        Args:
            backend: Ignored.
            expiration_time: Ignored.
            arguments: Ignored.
            **kwargs: Ignored.

        Returns:
            Self for method chaining.
        """
        return self

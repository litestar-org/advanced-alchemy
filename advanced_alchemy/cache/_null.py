"""Null cache region implementation for when dogpile.cache is not installed."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

__all__ = ("NullRegion",)

T = TypeVar("T")


# Sentinel value to indicate a cache miss (compatible with dogpile.cache.api.NO_VALUE)
class _NoValue:
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

    def get(self, key: str, expiration_time: int | None = None) -> Any:
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
        expiration_time: int | None = None,
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
        expiration_time: int | None = None,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> NullRegion:
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

"""Configuration classes for dogpile.cache integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ("CacheConfig",)


def _default_arguments() -> dict[str, Any]:
    return {}


@dataclass
class CacheConfig:
    """Configuration for a dogpile.cache region.

    This dataclass holds configuration options for setting up a cache region
    using dogpile.cache. It supports multiple backends (Redis, Memcached, file, memory)
    and provides sensible defaults for getting started quickly.

    Example:
        Basic memory cache configuration::

            config = CacheConfig(
                backend="dogpile.cache.memory",
                expiration_time=300,
            )

        Redis cache configuration::

            config = CacheConfig(
                backend="dogpile.cache.redis",
                expiration_time=3600,
                arguments={
                    "host": "localhost",
                    "port": 6379,
                    "db": 0,
                },
            )
    """

    backend: str = "dogpile.cache.null"
    """Cache backend identifier.

    Common backends:
    - ``dogpile.cache.null``: No-op cache (default, for development)
    - ``dogpile.cache.memory``: In-process memory cache
    - ``dogpile.cache.redis``: Redis backend
    - ``dogpile.cache.memcached``: Memcached backend
    - ``dogpile.cache.dbm``: DBM file-based cache
    """

    expiration_time: int = 3600
    """Default TTL (time-to-live) in seconds for cached items.

    Set to ``-1`` for no expiration. Default is 3600 (1 hour).
    """

    arguments: dict[str, Any] = field(default_factory=_default_arguments)
    """Backend-specific configuration arguments.

    These are passed directly to the dogpile.cache backend.
    See dogpile.cache documentation for backend-specific options.

    Example for Redis::

        {"host": "localhost", "port": 6379, "db": 0}

    Example for Memcached::

        {"url": ["127.0.0.1:11211"]}
    """

    key_prefix: str = "aa:"
    """Prefix for all cache keys.

    This helps avoid key collisions when sharing a cache backend
    with other applications. Default is ``aa:`` (advanced-alchemy).
    """

    enabled: bool = True
    """Enable or disable caching globally.

    When ``False``, all cache operations are bypassed and
    data is always fetched from the database. Useful for
    debugging or testing.
    """

    serializer: Callable[[Any], bytes] | None = None
    """Custom serializer function.

    If ``None``, uses the default JSON serializer which handles
    SQLAlchemy models, datetime objects, and UUIDs.

    The function should accept any value and return bytes.
    """

    deserializer: Callable[[bytes, type[Any]], Any] | None = None
    """Custom deserializer function.

    If ``None``, uses the default JSON deserializer.

    The function should accept bytes and a model class,
    returning an instance of that class.
    """

    region_factory: Callable[[CacheConfig], Any] | None = None
    """Optional hook to construct a cache region instance.

    This exists to keep the repository/service integration stable even if
    Advanced Alchemy swaps the underlying cache backend in the future.

    If provided, :class:`~advanced_alchemy.cache.CacheManager` will call this
    factory instead of using ``dogpile.cache.make_region()``.

    The returned object must implement the subset of dogpile's region API that
    AA relies on (e.g. ``get()``, ``set()``, ``delete()``, ``invalidate()``,
    and optionally ``get_or_create()``).
    """

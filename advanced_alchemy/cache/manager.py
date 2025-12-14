"""Cache manager for dogpile.cache integration with SQLAlchemy repositories."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from advanced_alchemy.cache._null import NO_VALUE, NullRegion
from advanced_alchemy.cache.serializers import default_deserializer, default_serializer
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from dogpile.cache import CacheRegion

    from advanced_alchemy.cache.config import CacheConfig

__all__ = (
    "DOGPILE_CACHE_INSTALLED",
    "CacheManager",
)

logger = logging.getLogger("advanced_alchemy.cache")

T = TypeVar("T")

# Check if dogpile.cache is installed
try:
    from dogpile.cache import make_region
    from dogpile.cache.api import NO_VALUE as DOGPILE_NO_VALUE

    DOGPILE_CACHE_INSTALLED = True
except ImportError:
    DOGPILE_NO_VALUE = NO_VALUE
    DOGPILE_CACHE_INSTALLED = False


class CacheManager:
    """Manages dogpile.cache regions with model-aware invalidation.

    This class provides a high-level interface for caching SQLAlchemy model
    instances using dogpile.cache. It handles serialization, cache key
    generation, and model-version-based invalidation for list queries.

    All cache operations are available in both sync and async variants:
    - Sync methods end with ``_sync`` (e.g., ``get_sync``, ``set_sync``)
    - Async methods end with ``_async`` (e.g., ``get_async``, ``set_async``)

    Async methods use ``asyncio.to_thread()`` with capacity limiting to
    prevent blocking the event loop when using network-based backends
    like Redis or Memcached.

    Features:
    - Lazy initialization of cache regions
    - Model-aware cache key generation
    - Version-based invalidation for list queries
    - Graceful degradation when dogpile.cache is not installed
    - Support for custom serializers
    - Both sync and async operation support

    Example:
        Sync usage::

            from advanced_alchemy.cache import CacheConfig, CacheManager

            config = CacheConfig(
                backend="dogpile.cache.memory",
                expiration_time=300,
            )
            manager = CacheManager(config)

            # Cache a value (sync)
            result = manager.get_or_create_sync(
                "users:1",
                lambda: fetch_user_from_db(1),
            )

        Async usage::

            # Cache a value (async)
            result = await manager.get_or_create_async(
                "users:1",
                lambda: fetch_user_from_db(1),
            )
    """

    __slots__ = (
        "_model_versions",
        "_region",
        "config",
    )

    def __init__(self, config: CacheConfig) -> None:
        """Initialize the cache manager.

        Args:
            config: Configuration for the cache region.
        """
        self.config = config
        self._region: CacheRegion | NullRegion | None = None
        self._model_versions: dict[str, int] = {}

    @property
    def region(self) -> CacheRegion | NullRegion:
        """Get the cache region, creating it if necessary.

        The region is lazily initialized on first access. If dogpile.cache
        is not installed or initialization fails, returns a NullRegion that
        provides the same interface but doesn't actually cache anything.

        Returns:
            The configured cache region or a NullRegion fallback.
        """
        if self._region is None:
            self._region = self._create_region()
        return self._region

    def _create_region(self) -> CacheRegion | NullRegion:
        """Create and configure the dogpile.cache region.

        Returns:
            A configured CacheRegion or NullRegion if dogpile.cache
            is not installed or configuration fails.
        """
        if not DOGPILE_CACHE_INSTALLED:
            logger.info("dogpile.cache is not installed, using NullRegion")
            return NullRegion()

        if not self.config.enabled:
            logger.debug("Caching is disabled, using NullRegion")
            return NullRegion()

        try:
            region: CacheRegion = make_region().configure(
                self.config.backend,
                expiration_time=self.config.expiration_time,
                arguments=self.config.arguments,
            )
        except Exception:
            logger.exception("Failed to configure cache region, using NullRegion")
            return NullRegion()
        else:
            logger.debug("Configured cache region with backend: %s", self.config.backend)
            return region

    def _make_key(self, key: str) -> str:
        """Generate a full cache key with the configured prefix.

        Args:
            key: The base cache key.

        Returns:
            The prefixed cache key.
        """
        return f"{self.config.key_prefix}{key}"

    # =========================================================================
    # Sync Methods (canonical implementations)
    # =========================================================================

    def get_sync(self, key: str) -> Any:
        """Get a value from the cache (sync).

        Args:
            key: The cache key (without prefix).

        Returns:
            The cached value or NO_VALUE if not found.
        """
        if not self.config.enabled:
            return DOGPILE_NO_VALUE
        return self.region.get(self._make_key(key))

    def set_sync(self, key: str, value: Any) -> None:
        """Set a value in the cache (sync).

        Args:
            key: The cache key (without prefix).
            value: The value to cache.
        """
        if not self.config.enabled:
            return
        self.region.set(self._make_key(key), value)

    def delete_sync(self, key: str) -> None:
        """Delete a value from the cache (sync).

        Args:
            key: The cache key (without prefix).
        """
        self.region.delete(self._make_key(key))

    def get_or_create_sync(
        self,
        key: str,
        creator: Callable[[], T],
        expiration_time: int | None = None,
    ) -> T:
        """Get a value from cache or create it using the creator function (sync).

        This method uses dogpile.cache's get_or_create which provides
        mutex-based protection against the "thundering herd" problem
        when multiple requests try to create the same value simultaneously.

        Note:
            The creator function must be synchronous. For async creators,
            you must await them before passing to this method.

        Args:
            key: The cache key (without prefix).
            creator: A synchronous callable that returns the value to cache on miss.
            expiration_time: Optional override for the default TTL.

        Returns:
            The cached or newly created value.
        """
        if not self.config.enabled:
            return creator()
        return self.region.get_or_create(
            self._make_key(key),
            creator,
            expiration_time=expiration_time or self.config.expiration_time,
        )

    def get_entity_sync(
        self,
        model_name: str,
        entity_id: Any,
        model_class: type[T],
    ) -> T | None:
        """Get a cached entity by model name and ID (sync).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            model_class: The SQLAlchemy model class for deserialization.

        Returns:
            The cached model instance or None if not found.
        """
        key = f"{model_name}:get:{entity_id}"
        cached = self.get_sync(key)

        if cached is DOGPILE_NO_VALUE or cached is NO_VALUE:
            return None

        deserializer = self.config.deserializer or default_deserializer
        try:
            result: T = deserializer(cached, model_class)
        except Exception:
            logger.exception("Failed to deserialize cached entity %s:%s", model_name, entity_id)
            # Remove corrupted cache entry
            self.delete_sync(key)
            return None
        else:
            return result

    def set_entity_sync(
        self,
        model_name: str,
        entity_id: Any,
        entity: Any,
    ) -> None:
        """Cache an entity (sync).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            entity: The SQLAlchemy model instance to cache.
        """
        key = f"{model_name}:get:{entity_id}"
        serializer = self.config.serializer or default_serializer

        try:
            serialized = serializer(entity)
            self.set_sync(key, serialized)
        except Exception:
            logger.exception("Failed to serialize entity %s:%s", model_name, entity_id)

    def invalidate_entity_sync(self, model_name: str, entity_id: Any) -> None:
        """Invalidate the cache for a specific entity (sync).

        This should be called after an entity is created, updated, or deleted
        to ensure the cache doesn't serve stale data.

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
        """
        key = f"{model_name}:get:{entity_id}"
        self.delete_sync(key)
        logger.debug("Invalidated cache for %s:%s", model_name, entity_id)

    def bump_model_version_sync(self, model_name: str) -> int:
        """Increment the version number for a model (sync).

        This is used for version-based invalidation of list queries.
        When a model is created, updated, or deleted, the version is
        bumped, which effectively invalidates all list query caches
        that include that model's version in their cache key.

        Args:
            model_name: The model/table name.

        Returns:
            The new version number.
        """
        self._model_versions[model_name] = self._model_versions.get(model_name, 0) + 1
        version = self._model_versions[model_name]

        # Store in cache for distributed consistency
        self.set_sync(f"{model_name}:version", version)
        logger.debug("Bumped version for %s to %d", model_name, version)
        return version

    def get_model_version_sync(self, model_name: str) -> int:
        """Get the current version number for a model (sync).

        This is used to include the version in list query cache keys,
        ensuring that list caches are invalidated when models change.

        Args:
            model_name: The model/table name.

        Returns:
            The current version number (0 if not set).
        """
        # Check local cache first
        if model_name in self._model_versions:
            return self._model_versions[model_name]

        # Check distributed cache
        cached = self.get_sync(f"{model_name}:version")
        if cached is not DOGPILE_NO_VALUE and cached is not NO_VALUE:
            self._model_versions[model_name] = int(cached)
            return self._model_versions[model_name]

        return 0

    def invalidate_all_sync(self) -> None:
        """Invalidate all cached values (sync).

        Warning:
            This invalidates the entire region, not just keys with
            the configured prefix. Use with caution in shared cache
            environments.
        """
        self.region.invalidate()
        self._model_versions.clear()
        logger.info("Invalidated entire cache region")

    # =========================================================================
    # Async Methods (thin wrappers using async_() for thread offloading)
    # =========================================================================

    async def get_async(self, key: str) -> Any:
        """Get a value from the cache (async).

        Args:
            key: The cache key (without prefix).

        Returns:
            The cached value or NO_VALUE if not found.
        """
        return await async_(self.get_sync)(key)

    async def set_async(self, key: str, value: Any) -> None:
        """Set a value in the cache (async).

        Args:
            key: The cache key (without prefix).
            value: The value to cache.
        """
        await async_(self.set_sync)(key, value)

    async def delete_async(self, key: str) -> None:
        """Delete a value from the cache (async).

        Args:
            key: The cache key (without prefix).
        """
        await async_(self.delete_sync)(key)

    async def get_or_create_async(
        self,
        key: str,
        creator: Callable[[], T],
        expiration_time: int | None = None,
    ) -> T:
        """Get a value from cache or create it using the creator function (async).

        This method uses dogpile.cache's get_or_create which provides
        mutex-based protection against the "thundering herd" problem
        when multiple requests try to create the same value simultaneously.

        Note:
            The creator function must be synchronous since dogpile.cache
            runs in a thread pool. For async creators, you must await
            them and wrap the result before passing to this method.

        Args:
            key: The cache key (without prefix).
            creator: A synchronous callable that returns the value to cache on miss.
            expiration_time: Optional override for the default TTL.

        Returns:
            The cached or newly created value.
        """
        return await async_(self.get_or_create_sync)(key, creator, expiration_time)

    async def get_entity_async(
        self,
        model_name: str,
        entity_id: Any,
        model_class: type[T],
    ) -> T | None:
        """Get a cached entity by model name and ID (async).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            model_class: The SQLAlchemy model class for deserialization.

        Returns:
            The cached model instance or None if not found.
        """
        return await async_(self.get_entity_sync)(model_name, entity_id, model_class)

    async def set_entity_async(
        self,
        model_name: str,
        entity_id: Any,
        entity: Any,
    ) -> None:
        """Cache an entity (async).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            entity: The SQLAlchemy model instance to cache.
        """
        await async_(self.set_entity_sync)(model_name, entity_id, entity)

    async def invalidate_entity_async(self, model_name: str, entity_id: Any) -> None:
        """Invalidate the cache for a specific entity (async).

        This should be called after an entity is created, updated, or deleted
        to ensure the cache doesn't serve stale data.

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
        """
        await async_(self.invalidate_entity_sync)(model_name, entity_id)

    async def bump_model_version_async(self, model_name: str) -> int:
        """Increment the version number for a model (async).

        This is used for version-based invalidation of list queries.
        When a model is created, updated, or deleted, the version is
        bumped, which effectively invalidates all list query caches
        that include that model's version in their cache key.

        Args:
            model_name: The model/table name.

        Returns:
            The new version number.
        """
        return await async_(self.bump_model_version_sync)(model_name)

    async def get_model_version_async(self, model_name: str) -> int:
        """Get the current version number for a model (async).

        This is used to include the version in list query cache keys,
        ensuring that list caches are invalidated when models change.

        Args:
            model_name: The model/table name.

        Returns:
            The current version number (0 if not set).
        """
        return await async_(self.get_model_version_sync)(model_name)

    async def invalidate_all_async(self) -> None:
        """Invalidate all cached values (async).

        Warning:
            This invalidates the entire region, not just keys with
            the configured prefix. Use with caution in shared cache
            environments.
        """
        await async_(self.invalidate_all_sync)()

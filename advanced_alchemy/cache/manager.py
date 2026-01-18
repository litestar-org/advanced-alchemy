"""Cache manager for dogpile.cache integration with SQLAlchemy repositories."""

import asyncio
import base64
import concurrent.futures
import logging
import threading
import uuid
from collections.abc import Coroutine
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, cast

from advanced_alchemy.cache._null import NO_VALUE, NullRegion, SyncCacheRegionProtocol
from advanced_alchemy.cache.serializers import default_deserializer, default_serializer
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from advanced_alchemy.cache.config import CacheConfig

__all__ = (
    "DOGPILE_CACHE_INSTALLED",
    "DOGPILE_NO_VALUE",
    "CacheManager",
)

logger = logging.getLogger("advanced_alchemy.cache")

T = TypeVar("T")

# Type alias for the make_region factory function
MakeRegionFunc = Callable[[], SyncCacheRegionProtocol]


# Stub implementations for when dogpile.cache is not installed
def _make_region_stub() -> SyncCacheRegionProtocol:
    """Stub make_region that returns a NullRegion when dogpile.cache is not installed."""
    return NullRegion()


_dogpile_no_value_stub: object = NO_VALUE
"""Stub NO_VALUE sentinel when dogpile.cache is not installed."""


# Try to import real dogpile.cache implementation at runtime
_make_region: MakeRegionFunc
_dogpile_no_value: object
try:
    from dogpile.cache import (  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]
        make_region as _make_region_real,  # pyright: ignore[reportUnknownVariableType]
    )
    from dogpile.cache.api import (  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]
        NO_VALUE as _dogpile_no_value_real,  # noqa: N811  # pyright: ignore[reportUnknownVariableType]
    )

    _make_region = cast("MakeRegionFunc", _make_region_real)
    _dogpile_no_value = cast("object", _dogpile_no_value_real)
    DOGPILE_CACHE_INSTALLED = True  # pyright: ignore[reportConstantRedefinition]

except ImportError:  # pragma: no cover
    _make_region = _make_region_stub
    _dogpile_no_value = _dogpile_no_value_stub
    DOGPILE_CACHE_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

DOGPILE_NO_VALUE: object = _dogpile_no_value
"""Sentinel value indicating a cache miss (from dogpile or NullRegion)."""


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
        "_async_inflight",
        "_async_inflight_lock",
        "_model_versions",
        "_region",
        "_sync_inflight",
        "_sync_inflight_lock",
        "config",
    )

    def __init__(self, config: "CacheConfig") -> None:
        """Initialize the cache manager.

        Args:
            config: Configuration for the cache region.

        Note:
            Model version tokens are stored in-cache for cross-process consistency.
            A random token is used per commit to avoid lost updates without requiring
            backend-specific atomic increment support.

            Per-process singleflight registries (async and sync) are best-effort;
            they reduce stampedes within a single process but do not provide
            cross-process locking.
        """
        self.config = config
        # Model version tokens are stored in-cache for cross-process consistency.
        # Use a random token per commit to avoid lost updates without requiring
        # backend-specific atomic increment support.
        self._region: Optional[SyncCacheRegionProtocol] = None
        self._model_versions: dict[str, str] = {}
        self._async_inflight: dict[str, asyncio.Task[Any]] = {}
        self._async_inflight_lock: Optional[asyncio.Lock] = None
        self._sync_inflight: dict[str, concurrent.futures.Future[Any]] = {}
        self._sync_inflight_lock = threading.Lock()

    @property
    def _inflight_lock_async(self) -> asyncio.Lock:
        """Lazily create the asyncio lock used for async singleflight."""
        if self._async_inflight_lock is None:
            self._async_inflight_lock = asyncio.Lock()
        return self._async_inflight_lock

    @property
    def region(self) -> SyncCacheRegionProtocol:
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

    def _create_region(self) -> SyncCacheRegionProtocol:
        """Create and configure the dogpile.cache region.

        Returns:
            A configured CacheRegion or NullRegion if dogpile.cache
            is not installed or configuration fails.
        """
        if self.config.region_factory is not None:
            try:
                created_region = cast("SyncCacheRegionProtocol", self.config.region_factory(self.config))
            except Exception:
                logger.exception("Failed to construct cache region via region_factory, using NullRegion")
                return NullRegion()
            else:
                logger.debug("Configured cache region via region_factory")
                return created_region

        if not DOGPILE_CACHE_INSTALLED:
            logger.info("dogpile.cache is not installed, using NullRegion")
            return NullRegion()

        if not self.config.enabled:
            logger.debug("Caching is disabled, using NullRegion")
            return NullRegion()

        try:
            region: SyncCacheRegionProtocol = _make_region().configure(
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

    def _singleflight_async_cleanup(self, key: str, task: asyncio.Task[Any], *_: Any) -> None:
        """Cleanup callback for async singleflight tasks.

        This runs in the event loop thread; we can safely mutate the in-flight
        dict directly without scheduling another task.
        """
        if self._async_inflight.get(key) is task:
            self._async_inflight.pop(key, None)

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

    def get_sync(self, key: str) -> object:
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
        expiration_time: Optional[int] = None,
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
        region = self.region
        full_key = self._make_key(key)
        if hasattr(region, "get_or_create"):
            return region.get_or_create(
                full_key,
                creator,
                expiration_time=expiration_time or self.config.expiration_time,
            )
        cached = region.get(full_key)
        if cached is not DOGPILE_NO_VALUE and cached is not NO_VALUE:
            return cast("T", cached)
        value = creator()
        region.set(full_key, value)
        return value

    def get_entity_sync(
        self,
        model_name: str,
        entity_id: Any,
        model_class: type[T],
        bind_group: Optional[str] = None,
    ) -> Optional[T]:
        """Get a cached entity by model name and ID (sync).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            model_class: The SQLAlchemy model class for deserialization.
            bind_group: Optional routing group for multi-master configurations.
                When provided, entity caches are namespaced by bind_group to
                prevent data leaks between database shards/replicas.

        Returns:
            The cached model instance or None if not found.
        """
        key = f"{model_name}:{bind_group}:get:{entity_id}" if bind_group else f"{model_name}:get:{entity_id}"
        cached = self.get_sync(key)

        if cached is DOGPILE_NO_VALUE or cached is NO_VALUE:
            return None
        if not isinstance(cached, (bytes, bytearray)):
            self.delete_sync(key)
            return None

        deserializer = self.config.deserializer or default_deserializer
        try:
            payload = bytes(cached) if isinstance(cached, bytearray) else cached
            result: T = deserializer(payload, model_class)
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
        bind_group: Optional[str] = None,
    ) -> None:
        """Cache an entity (sync).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            entity: The SQLAlchemy model instance to cache.
            bind_group: Optional routing group for multi-master configurations.
                When provided, entity caches are namespaced by bind_group to
                prevent data leaks between database shards/replicas.
        """
        key = f"{model_name}:{bind_group}:get:{entity_id}" if bind_group else f"{model_name}:get:{entity_id}"
        serializer = self.config.serializer or default_serializer

        try:
            serialized = serializer(entity)
            self.set_sync(key, serialized)
        except Exception:
            logger.exception("Failed to serialize entity %s:%s", model_name, entity_id)

    def invalidate_entity_sync(self, model_name: str, entity_id: Any, bind_group: Optional[str] = None) -> None:
        """Invalidate the cache for a specific entity (sync).

        This should be called after an entity is created, updated, or deleted
        to ensure the cache doesn't serve stale data.

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            bind_group: Optional routing group for multi-master configurations.
                When provided, only the cache entry for that bind_group is
                invalidated.
        """
        key = f"{model_name}:{bind_group}:get:{entity_id}" if bind_group else f"{model_name}:get:{entity_id}"
        self.delete_sync(key)
        logger.debug("Invalidated cache for %s:%s (bind_group=%s)", model_name, entity_id, bind_group)

    def bump_model_version_sync(self, model_name: str) -> str:
        """Bump the version token for a model (sync).

        This is used for version-based invalidation of list queries.
        When a model is created, updated, or deleted, the version is
        bumped to a new random token, which effectively invalidates all
        list query caches that include that token in their cache key.

        Args:
            model_name: The model/table name.

        Returns:
            The new version token.
        """
        token = uuid.uuid4().hex
        self._model_versions[model_name] = token

        # Store in cache for distributed consistency
        self.set_sync(f"{model_name}:version", token)
        logger.debug("Bumped version token for %s to %s", model_name, token)
        return token

    def get_model_version_sync(self, model_name: str) -> str:
        """Get the current version token for a model (sync).

        This is used to include the version in list query cache keys,
        ensuring that list caches are invalidated when models change.

        Args:
            model_name: The model/table name.

        Returns:
            The current version token ("0" if not set).
        """
        # Check local cache first
        if model_name in self._model_versions:
            return self._model_versions[model_name]

        # Check distributed cache
        cached = self.get_sync(f"{model_name}:version")
        if cached is not DOGPILE_NO_VALUE and cached is not NO_VALUE and isinstance(cached, str):
            self._model_versions[model_name] = cached
            return cached

        return "0"

    def get_list_sync(self, key: str, model_class: type[T]) -> Optional[list[T]]:
        """Get a cached list of entities (sync).

        The list is stored as base64-encoded serialized entity payloads.

        Args:
            key: Cache key (without prefix).
            model_class: Model class for deserialization.

        Returns:
            A list of detached model instances or None if not found.
        """
        cached = self.get_sync(key)
        if cached is DOGPILE_NO_VALUE or cached is NO_VALUE:
            return None
        if not isinstance(cached, list):
            return None

        cached_list = cast("list[Any]", cached)  # type: ignore[redundant-cast]
        deserializer = self.config.deserializer or default_deserializer
        results: list[T] = []
        try:
            for item in cached_list:
                if not isinstance(item, str):
                    return None
                raw = base64.b64decode(item.encode("ascii"))
                results.append(deserializer(raw, model_class))
        except Exception:
            logger.exception("Failed to deserialize cached list for key %s", key)
            self.delete_sync(key)
            return None
        return results

    def set_list_sync(self, key: str, items: list[Any]) -> None:
        """Cache a list of entities (sync).

        Args:
            key: Cache key (without prefix).
            items: List of entities to cache.
        """
        serializer = self.config.serializer or default_serializer
        try:
            payload = [base64.b64encode(serializer(item)).decode("ascii") for item in items]
            self.set_sync(key, payload)
        except Exception:
            logger.exception("Failed to serialize cached list for key %s", key)

    def get_list_and_count_sync(self, key: str, model_class: type[T]) -> Optional[tuple[list[T], int]]:
        """Get a cached list+count payload (sync)."""
        cached = self.get_sync(key)
        if cached is DOGPILE_NO_VALUE or cached is NO_VALUE:
            return None
        if not isinstance(cached, dict):
            return None

        cached_payload: dict[str, Any] = cast("dict[str, Any]", cached)
        items_raw = cached_payload.get("items")
        count_raw = cached_payload.get("count")
        if not isinstance(items_raw, list) or not isinstance(count_raw, int):
            return None

        items_list = cast("list[Any]", items_raw)  # type: ignore[redundant-cast]
        deserializer = self.config.deserializer or default_deserializer
        results: list[T] = []
        try:
            for item in items_list:
                if not isinstance(item, str):
                    return None
                raw = base64.b64decode(item.encode("ascii"))
                results.append(deserializer(raw, model_class))
        except Exception:
            logger.exception("Failed to deserialize cached list_and_count for key %s", key)
            self.delete_sync(key)
            return None
        return results, count_raw

    def set_list_and_count_sync(self, key: str, items: list[Any], count: int) -> None:
        """Cache a list+count payload (sync)."""
        serializer = self.config.serializer or default_serializer
        try:
            payload = {
                "items": [base64.b64encode(serializer(item)).decode("ascii") for item in items],
                "count": count,
            }
            self.set_sync(key, payload)
        except Exception:
            logger.exception("Failed to serialize cached list_and_count for key %s", key)

    def singleflight_sync(self, key: str, creator: Callable[[], T]) -> T:
        """Coalesce concurrent sync cache misses per-process.

        This reduces stampedes in thread-based sync apps. It does not provide
        cross-process locking.
        """
        with self._sync_inflight_lock:
            future: Optional[concurrent.futures.Future[Any]] = self._sync_inflight.get(key)
            if future is None:
                future = concurrent.futures.Future()
                self._sync_inflight[key] = future
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            return cast("T", future.result())

        try:
            result = creator()
        except Exception as e:
            future.set_exception(e)
            raise
        else:
            future.set_result(result)
            return result
        finally:
            with self._sync_inflight_lock:
                if self._sync_inflight.get(key) is future:
                    self._sync_inflight.pop(key, None)

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

    async def get_async(self, key: str) -> object:
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
        expiration_time: Optional[int] = None,
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
        bind_group: Optional[str] = None,
    ) -> Optional[T]:
        """Get a cached entity by model name and ID (async).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            model_class: The SQLAlchemy model class for deserialization.
            bind_group: Optional routing group for multi-master configurations.
                When provided, entity caches are namespaced by bind_group to
                prevent data leaks between database shards/replicas.

        Returns:
            The cached model instance or None if not found.
        """
        return await async_(self.get_entity_sync)(model_name, entity_id, model_class, bind_group)

    async def set_entity_async(
        self,
        model_name: str,
        entity_id: Any,
        entity: Any,
        bind_group: Optional[str] = None,
    ) -> None:
        """Cache an entity (async).

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            entity: The SQLAlchemy model instance to cache.
            bind_group: Optional routing group for multi-master configurations.
                When provided, entity caches are namespaced by bind_group to
                prevent data leaks between database shards/replicas.
        """
        await async_(self.set_entity_sync)(model_name, entity_id, entity, bind_group)

    async def invalidate_entity_async(self, model_name: str, entity_id: Any, bind_group: Optional[str] = None) -> None:
        """Invalidate the cache for a specific entity (async).

        This should be called after an entity is created, updated, or deleted
        to ensure the cache doesn't serve stale data.

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            bind_group: Optional routing group for multi-master configurations.
                When provided, only the cache entry for that bind_group is
                invalidated.
        """
        await async_(self.invalidate_entity_sync)(model_name, entity_id, bind_group)

    async def bump_model_version_async(self, model_name: str) -> str:
        """Bump the version token for a model (async).

        This is used for version-based invalidation of list queries.
        When a model is created, updated, or deleted, the version is
        bumped, which effectively invalidates all list query caches
        that include that model's version in their cache key.

        Args:
            model_name: The model/table name.

        Returns:
            The new version token.
        """
        return await async_(self.bump_model_version_sync)(model_name)

    async def get_model_version_async(self, model_name: str) -> str:
        """Get the current version token for a model (async).

        This is used to include the version in list query cache keys,
        ensuring that list caches are invalidated when models change.

        Args:
            model_name: The model/table name.

        Returns:
            The current version token ("0" if not set).
        """
        return await async_(self.get_model_version_sync)(model_name)

    async def get_list_async(self, key: str, model_class: type[T]) -> Optional[list[T]]:
        """Get a cached list of entities (async)."""
        return await async_(self.get_list_sync)(key, model_class)

    async def set_list_async(self, key: str, items: list[Any]) -> None:
        """Cache a list of entities (async)."""
        await async_(self.set_list_sync)(key, items)

    async def get_list_and_count_async(self, key: str, model_class: type[T]) -> Optional[tuple[list[T], int]]:
        """Get a cached list+count payload (async)."""
        return await async_(self.get_list_and_count_sync)(key, model_class)

    async def set_list_and_count_async(self, key: str, items: list[Any], count: int) -> None:
        """Cache a list+count payload (async)."""
        await async_(self.set_list_and_count_sync)(key, items, count)

    async def singleflight_async(self, key: str, creator: Callable[[], Coroutine[Any, Any, T]]) -> T:
        """Coalesce concurrent async cache misses per-process.

        The creator is invoked once per key at a time; concurrent callers
        await the same in-flight task. This does not provide cross-process
        locking.
        """
        async with self._inflight_lock_async:
            task = self._async_inflight.get(key)
            if task is None:
                task = asyncio.create_task(creator())
                self._async_inflight[key] = task
                task.add_done_callback(partial(self._singleflight_async_cleanup, key))

        return await asyncio.shield(task)

    async def invalidate_all_async(self) -> None:
        """Invalidate all cached values (async).

        Warning:
            This invalidates the entire region, not just keys with
            the configured prefix. Use with caution in shared cache
            environments.
        """
        await async_(self.invalidate_all_sync)()

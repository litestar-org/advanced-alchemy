=======
Caching
=======

.. py:module:: advanced_alchemy.cache

Dogpile L2 caching integration for SQLAlchemy repositories with commit-aware
invalidation and per-process singleflight protection.

Configuration & Region Management
---------------------------------

.. autoclass:: advanced_alchemy.cache.CacheConfig
    :members: backend, expiration_time, key_prefix, enabled
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.cache.CacheManager
    :members: region, config, get_async, set_async, delete_async, get_entity_async, set_entity_async, invalidate_entity_async, invalidate_all_async, get_sync, set_sync, delete_sync
    :no-inherited-members:
    :show-inheritance:

Custom Regions
--------------

Types for building a custom region supplied through
``CacheConfig(region_factory=...)``.

.. autoclass:: advanced_alchemy.cache.SyncCacheRegionProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.cache.AsyncCacheRegionProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

    .. note::

        ``CacheManager`` currently requires a synchronous region, even for its
        async methods, which run the sync operations in a worker thread.

.. autoclass:: advanced_alchemy.cache.NullRegion
    :no-inherited-members:
    :show-inheritance:

.. py:data:: NO_VALUE
    :type: Any

    Cache-miss sentinel. A custom region returns it from ``get`` on a miss.

Serialization & Listeners
-------------------------

.. autofunction:: advanced_alchemy.cache.default_serializer

.. autofunction:: advanced_alchemy.cache.default_deserializer

.. autofunction:: advanced_alchemy.cache.setup_cache_listeners

.. py:data:: DOGPILE_CACHE_INSTALLED
    :type: bool

    Boolean flag indicating whether ``dogpile.cache`` is installed.

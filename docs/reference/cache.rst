=====
cache
=====

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

Serialization & Listeners
-------------------------

.. autofunction:: advanced_alchemy.cache.default_serializer

.. autofunction:: advanced_alchemy.cache.default_deserializer

.. autofunction:: advanced_alchemy.cache.setup_cache_listeners

.. py:data:: DOGPILE_CACHE_INSTALLED
    :type: bool

    Boolean flag indicating whether ``dogpile.cache`` is installed.

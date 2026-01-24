=====
Cache
=====

.. module:: advanced_alchemy.cache

The cache module provides optional integration with `dogpile.cache`_ for caching
SQLAlchemy model instances. It supports multiple backends and provides automatic
cache invalidation when models are modified.

.. _dogpile.cache: https://dogpilecache.sqlalchemy.org/

Installation
------------

The cache module requires the optional ``dogpile.cache`` dependency:

.. code-block:: bash

    pip install advanced-alchemy[dogpile]

Without this dependency, the cache manager will use a ``NullRegion`` that provides
the same interface but doesn't actually cache anything.

Configuration
-------------

.. autoclass:: advanced_alchemy.cache.CacheConfig
    :members:
    :show-inheritance:

Cache Manager
-------------

.. autoclass:: advanced_alchemy.cache.CacheManager
    :members:
    :show-inheritance:

Serialization
-------------

.. autofunction:: advanced_alchemy.cache.default_serializer

.. autofunction:: advanced_alchemy.cache.default_deserializer

Setup
-----

.. autofunction:: advanced_alchemy._listeners.setup_cache_listeners

Constants
---------

.. autodata:: advanced_alchemy.cache.DOGPILE_CACHE_INSTALLED
    :annotation:

"""Dogpile.cache integration for Advanced Alchemy.

This module provides optional caching support for SQLAlchemy repositories
using dogpile.cache. It supports multiple cache backends (Redis, Memcached,
file, memory) and provides automatic cache invalidation on model changes.

Features:
    - Multiple backend support (Redis, Memcached, file, memory, null)
    - Commit-aware cache invalidation via SQLAlchemy events
    - Version-based invalidation for list queries
    - JSON serialization for cached models (configurable)
    - Graceful degradation when dogpile.cache is not installed
    - Per-process singleflight to reduce stampedes on cache miss

Example:
    Using the config system (recommended)::

        from advanced_alchemy.cache import CacheConfig
        from advanced_alchemy.config import SQLAlchemyAsyncConfig
        from advanced_alchemy.repository import (
            SQLAlchemyAsyncRepository,
        )

        # Configure database with caching
        db_config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///app.db",
            cache_config=CacheConfig(
                backend="dogpile.cache.memory",
                expiration_time=300,
            ),
        )

        # Cache listeners are auto-registered, cache_manager is stored
        # in session.info and auto-retrieved by repositories.


        class UserRepository(SQLAlchemyAsyncRepository[User]):
            model_type = User


        async with db_config.get_session() as session:
            repo = UserRepository(session=session)
            user = await repo.get(
                1
            )  # First call hits DB and caches
            user = await repo.get(
                1
            )  # Second call returns cached result

    Redis configuration::

        cache_config = CacheConfig(
            backend="dogpile.cache.redis",
            expiration_time=3600,
            arguments={
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "distributed_lock": True,
            },
        )

Note:
    This module requires the optional ``dogpile.cache`` dependency.
    Install with: ``pip install advanced-alchemy[dogpile]``

    Without dogpile.cache installed, the cache manager will use a
    NullRegion that provides the same interface but doesn't cache.

Manual Setup:
    If not using the config system, call ``setup_cache_listeners()``
    during application initialization and pass cache_manager explicitly::

        from advanced_alchemy.cache import (
            CacheConfig,
            CacheManager,
            setup_cache_listeners,
        )

        cache_manager = CacheManager(
            CacheConfig(backend="dogpile.cache.memory")
        )
        setup_cache_listeners()

        repo = UserRepository(
            session=session, cache_manager=cache_manager
        )
"""

from advanced_alchemy._listeners import setup_cache_listeners
from advanced_alchemy.cache.config import CacheConfig
from advanced_alchemy.cache.manager import DOGPILE_CACHE_INSTALLED, CacheManager
from advanced_alchemy.cache.serializers import default_deserializer, default_serializer

__all__ = (
    "DOGPILE_CACHE_INSTALLED",
    "CacheConfig",
    "CacheManager",
    "default_deserializer",
    "default_serializer",
    "setup_cache_listeners",
)

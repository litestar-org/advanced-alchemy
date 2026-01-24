=======
Caching
=======

Advanced Alchemy provides optional caching support through integration with
`dogpile.cache`_. This allows you to cache SQLAlchemy model instances using
various backends (Redis, Memcached, file, memory) with automatic cache
invalidation when models are modified.

.. _dogpile.cache: https://dogpilecache.sqlalchemy.org/

Installation
------------

Install the optional caching dependency:

.. code-block:: bash

    pip install advanced-alchemy[dogpile]

Quick Start
-----------

Basic setup with in-memory caching using the config system:

.. code-block:: python

    from advanced_alchemy.cache import CacheConfig
    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    # Configure caching via SQLAlchemy config
    db_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///app.db",
        cache_config=CacheConfig(
            backend="dogpile.cache.memory",
            expiration_time=300,  # 5 minutes
        ),
    )

    # Cache listeners are automatically registered when cache_config is set.
    # The cache_manager is stored in session.info and auto-retrieved by repositories.


    class UserRepository(SQLAlchemyAsyncRepository[User]):
        model_type = User


    # Repository automatically uses cache_manager from session.info
    async with db_config.get_session() as session:
        repo = UserRepository(session=session)

        # First call hits database and caches the result
        user = await repo.get(user_id)

        # Second call returns cached result
        user = await repo.get(user_id)

Configuration Options
---------------------

The ``CacheConfig`` dataclass provides several configuration options:

.. code-block:: python

    from advanced_alchemy.cache import CacheConfig

    config = CacheConfig(
        # Cache backend (see Backend Configuration below)
        backend="dogpile.cache.redis",

        # Default TTL in seconds (default: 3600)
        expiration_time=3600,

        # Backend-specific arguments
        arguments={
            "host": "localhost",
            "port": 6379,
            "db": 0,
        },

        # Key prefix to avoid collisions (default: "aa:")
        key_prefix="myapp:",

        # Enable/disable caching globally (default: True)
        enabled=True,
    )

Backend Configuration
---------------------

Memory Backend
~~~~~~~~~~~~~~

Best for development and testing:

.. code-block:: python

    config = CacheConfig(
        backend="dogpile.cache.memory",
        expiration_time=300,
    )

Redis Backend
~~~~~~~~~~~~~

Recommended for production with distributed systems:

.. code-block:: python

    config = CacheConfig(
        backend="dogpile.cache.redis",
        expiration_time=3600,
        arguments={
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "distributed_lock": True,  # Enable distributed locking
        },
    )

Memcached Backend
~~~~~~~~~~~~~~~~~

Alternative for high-performance caching:

.. code-block:: python

    config = CacheConfig(
        backend="dogpile.cache.memcached",
        expiration_time=3600,
        arguments={
            "url": ["127.0.0.1:11211"],
        },
    )

Null Backend
~~~~~~~~~~~~

Disables caching (useful for testing):

.. code-block:: python

    config = CacheConfig(
        backend="dogpile.cache.null",
    )

    # Or simply disable caching
    config = CacheConfig(enabled=False)

Repository Integration
----------------------

The cache manager integrates with repositories through the ``cache_manager`` parameter:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository

    class UserRepository(SQLAlchemyAsyncRepository[User]):
        model_type = User


    # Create repository with caching
    repo = UserRepository(
        session=session,
        cache_manager=cache_manager,
        auto_expunge=True,  # Recommended with caching
    )

    # These methods support caching:
    user = await repo.get(user_id)  # Cached by entity ID
    users = await repo.list()  # Cached with version-based invalidation
    users, count = await repo.list_and_count()  # Cached with version-based invalidation

Bypassing the Cache
~~~~~~~~~~~~~~~~~~~

You can bypass the cache for specific queries:

.. code-block:: python

    # Force database fetch, skip cache
    user = await repo.get(user_id, use_cache=False)
    users = await repo.list(use_cache=False)

Automatic Cache Invalidation
----------------------------

When using the config system with ``cache_config``, cache listeners are
automatically registered (controlled by ``enable_cache_listener=True``, the default).
Cache entries are automatically invalidated when models are created, updated, or deleted.

The invalidation is transaction-aware:

- Invalidations are deferred until the transaction commits
- If the transaction rolls back, invalidations are discarded
- Entity caches are invalidated by ID
- List caches use version-based invalidation (bumps a version token)

Version-Based List Invalidation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

List queries use version-based invalidation. When any entity of a model type
is modified, a version token is bumped, which invalidates all list caches
for that model:

.. code-block:: python

    # First call caches with version token "abc123"
    users = await repo.list()

    # Modify any user
    user.name = "New Name"
    await repo.update(user)
    await session.commit()  # Version token bumped to "def456"

    # Next call sees new version, fetches fresh data
    users = await repo.list()

Singleflight (Stampede Protection)
----------------------------------

The cache manager includes per-process singleflight to prevent cache stampedes.
When multiple concurrent requests try to fetch the same uncached data, only
one request hits the database:

.. code-block:: python

    import asyncio

    # All 10 concurrent calls result in only 1 database query
    results = await asyncio.gather(*[
        repo.get(user_id) for _ in range(10)
    ])

Custom Serialization
--------------------

By default, models are serialized to JSON. You can provide custom serializers
for different serialization formats:

.. code-block:: python

    import msgpack

    def msgpack_serializer(model):
        # Convert model to dict and serialize with msgpack
        from sqlalchemy import inspect
        mapper = inspect(model.__class__)
        data = {col.key: getattr(model, col.key) for col in mapper.columns}
        return msgpack.packb(data)

    def msgpack_deserializer(data, model_class):
        unpacked = msgpack.unpackb(data)
        return model_class(**unpacked)

    config = CacheConfig(
        backend="dogpile.cache.redis",
        serializer=msgpack_serializer,
        deserializer=msgpack_deserializer,
    )

.. warning::

    The default JSON serializer only serializes column values, not relationships.
    Cached instances are detached and accessing lazy-loaded relationships will
    raise ``DetachedInstanceError``. Use ``session.merge()`` if you need
    relationship access.

Performance Considerations
--------------------------

1. **Use auto_expunge=True**: When using caching, set ``auto_expunge=True`` on
   your repository to ensure cached entities are properly detached.

2. **Choose the right backend**: Use Redis or Memcached for production with
   multiple application instances. Memory backend is only suitable for
   single-instance deployments or development.

3. **Set appropriate TTLs**: Balance between cache hit rate and data freshness.
   Shorter TTLs mean more database queries but fresher data.

4. **Key prefix**: Use unique key prefixes when sharing a cache backend with
   other applications to avoid key collisions.

5. **Graceful degradation**: If dogpile.cache is not installed, the cache
   manager automatically falls back to a no-op implementation.

Example: Full Application Setup
-------------------------------

.. code-block:: python

    from litestar import Litestar
    from litestar.contrib.sqlalchemy.plugins import SQLAlchemyPlugin

    from advanced_alchemy.cache import CacheConfig
    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository


    # Configure database with caching
    db_config = SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://user:pass@localhost/db",
        cache_config=CacheConfig(
            backend="dogpile.cache.redis",
            expiration_time=3600,
            arguments={"host": "localhost", "port": 6379, "db": 0},
            key_prefix="myapp:",
        ),
    )


    class UserRepository(SQLAlchemyAsyncRepository[User]):
        model_type = User


    async def get_user(session: AsyncSession, user_id: int) -> User:
        # Repository auto-retrieves cache_manager from session.info
        repo = UserRepository(session=session, auto_expunge=True)
        return await repo.get(user_id)


    app = Litestar(
        plugins=[SQLAlchemyPlugin(config=db_config)],
        ...
    )

Manual Setup (Without Config)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you're not using the config system, you can set up caching manually:

.. code-block:: python

    from advanced_alchemy.cache import CacheConfig, CacheManager, setup_cache_listeners

    # Create cache manager
    cache_manager = CacheManager(CacheConfig(backend="dogpile.cache.memory"))

    # Register listeners once at startup
    setup_cache_listeners()

    # Pass cache_manager explicitly to repositories
    repo = UserRepository(session=session, cache_manager=cache_manager)

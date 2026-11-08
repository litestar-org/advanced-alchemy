=======
Caching
=======

Advanced Alchemy integrates with `dogpile.cache <https://dogpilecache.sqlalchemy.org/>`__ to provide second-level (L2) entity and query caching with transaction-aware invalidation and singleflight stampede protection.

Installation
------------

Install the optional ``dogpile`` extra:

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[dogpile]"

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[dogpile]"

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[dogpile]"

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[dogpile]"

Quick Start
-----------

Attach :class:`~advanced_alchemy.cache.CacheConfig` to :class:`~advanced_alchemy.config.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.config.SQLAlchemySyncConfig`. Repositories automatically retrieve the configured :class:`~advanced_alchemy.cache.CacheManager` from ``session.info``:

.. code-block:: python

    from sqlalchemy.orm import Mapped

    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.cache import CacheConfig
    from advanced_alchemy.config import SQLAlchemySyncConfig
    from advanced_alchemy.repository import SQLAlchemySyncRepository


    class CachedAuthor(BigIntAuditBase):
        __tablename__ = "cached_author_example"

        name: Mapped[str]


    class CachedAuthorRepository(SQLAlchemySyncRepository[CachedAuthor]):
        model_type = CachedAuthor


    db_config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        create_all=True,
        cache_config=CacheConfig(
            backend="dogpile.cache.memory",
            expiration_time=300,
            key_prefix="authors:",
        ),
    )

    with db_config.get_session() as session:
        repo = CachedAuthorRepository(session=session, auto_expunge=True)
        created = repo.add(CachedAuthor(name="Ada Lovelace"), auto_commit=True)
        first_fetch = repo.get(created.id)
        cached_fetch = repo.get(created.id)
        bypassed_fetch = repo.get(created.id, use_cache=False)
        assert first_fetch.id == cached_fetch.id == bypassed_fetch.id

Backend Configurations
----------------------

Configure ``backend``, ``expiration_time``, ``arguments``, and ``key_prefix`` on :class:`~advanced_alchemy.cache.CacheConfig`:

.. code-block:: python

    from advanced_alchemy.cache import CacheConfig

    memory_cache = CacheConfig(
        backend="dogpile.cache.memory",
        expiration_time=300,
    )

    redis_cache = CacheConfig(
        backend="dogpile.cache.redis",
        expiration_time=3600,
        arguments={
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "distributed_lock": True,
        },
        key_prefix="myapp:",
    )

    memcached_cache = CacheConfig(
        backend="dogpile.cache.memcached",
        expiration_time=3600,
        arguments={"url": ["127.0.0.1:11211"]},
    )

    disabled_cache = CacheConfig(enabled=False)

Transaction-Aware Invalidation and Singleflight
-----------------------------------------------

When ``enable_cache_listener=True`` (the default on SQLAlchemy config classes), Advanced Alchemy registers session listeners that track entity mutations:

- **Commit-bound invalidation**: Cache invalidations are queued during flush and executed only after the transaction commits. Rollbacks discard pending invalidations.
- **Entity vs. list invalidation**: ``repo.get()`` caches by primary key and invalidates individual keys, while ``repo.get_many()`` and ``repo.get_many_and_count()`` bump a per-model version token on any model mutation.
- **Singleflight**: Concurrent in-process misses for the same cache key coalesce into a single database query.

Custom Serialization and Manual Setup
-------------------------------------

Provide custom ``serializer`` and ``deserializer`` callables on :class:`~advanced_alchemy.cache.CacheConfig`, or instantiate :class:`~advanced_alchemy.cache.CacheManager` directly when not using a config class:

.. code-block:: python

    from typing import Any

    from sqlalchemy import inspect

    from advanced_alchemy.cache import CacheConfig, CacheManager, setup_cache_listeners
    from advanced_alchemy.utils.serialization import decode_json, encode_json


    def custom_serializer(model: Any) -> bytes:
        mapper = inspect(model.__class__)
        payload = {col.key: getattr(model, col.key) for col in mapper.columns}
        return encode_json(payload).encode("utf-8")


    def custom_deserializer(raw: bytes, model_class: type[Any]) -> Any:
        return model_class(**decode_json(raw.decode("utf-8")))


    custom_cache_config = CacheConfig(
        backend="dogpile.cache.memory",
        serializer=custom_serializer,
        deserializer=custom_deserializer,
    )
    cache_manager = CacheManager(custom_cache_config)
    setup_cache_listeners()

.. warning::

    The default serializer persists column attributes only, not ORM relationships. Set ``auto_expunge=True`` on cached repositories and call ``session.merge(instance)`` before lazy-loading relationships.

See Also
--------

- :doc:`/reference/cache`
- :doc:`/usage/repositories/index`

=============
API Reference
=============

.. py:module:: advanced_alchemy

Complete class, function, and module reference for Advanced Alchemy. Browse any module in the left sidebar or select a section below.

Models, Types & Configuration
-----------------------------

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`table` Declarative Base
      :link: base
      :link-type: doc

      ``UUIDBase``, ``UUIDAuditBase``, ``BigIntBase``, ``BigIntAuditBase``, ``NanoIDBase``, and custom registry helpers.

    .. grid-item-card:: :octicon:`stack` Mixins
      :link: mixins/index
      :link-type: doc

      Primary key, audit timestamp, soft-delete, slug, optimistic locking sentinel, and unique key mixins.

    .. grid-item-card:: :octicon:`code-square` Custom Types
      :link: types
      :link-type: doc

      ``GUID``, ``DateTimeUTC``, ``JsonB``, ``EncryptedString``, ``PasswordHash``, ``FileObject``, and ``StoredObject``.

    .. grid-item-card:: :octicon:`gear` Configuration
      :link: config/index
      :link-type: doc

      ``SQLAlchemyAsyncConfig``, ``SQLAlchemySyncConfig``, ``EngineConfig``, ``AsyncSessionConfig``, and ``AlembicAsyncConfig``.

Repositories, Services & Scaling
--------------------------------

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`database` Repositories
      :link: repository
      :link-type: doc

      Async and sync SQLAlchemy repositories, slug repositories, and raw SQL query repositories.

    .. grid-item-card:: :octicon:`beaker` Memory Repositories
      :link: repository_memory
      :link-type: doc

      In-memory mock repositories (``SQLAlchemyAsyncMockRepository``, ``SQLAlchemySyncMockRepository``) for unit tests.

    .. grid-item-card:: :octicon:`package` Services
      :link: service
      :link-type: doc

      ``SQLAlchemyAsyncRepositoryService``, ``OffsetPagination``, and schema conversion utilities.

    .. grid-item-card:: :octicon:`filter` Filters & Bulk Operations
      :link: filters
      :link-type: doc

      Pagination, date range, collection, search, and ordering filters plus cross-dialect :doc:`bulk upserts <operations>`.

    .. grid-item-card:: :octicon:`git-branch` Replica Routing
      :link: routing
      :link-type: doc

      Read/write session routing, replica selectors, and primary stickiness.

    .. grid-item-card:: :octicon:`zap` Caching
      :link: cache
      :link-type: doc

      ``CacheConfig``, ``CacheManager``, and Dogpile L2 query caching.

Frameworks, CLI & Utilities
---------------------------

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`plug` Framework Extensions
      :link: extensions/index
      :link-type: doc

      Plugin, middleware, provider, DTO, and session store references for Litestar, FastAPI, Starlette, Flask, Sanic, and :doc:`Google ADK <adk-compatibility-matrix>`.

    .. grid-item-card:: :octicon:`terminal` CLI & Alembic
      :link: cli
      :link-type: doc

      Standalone ``alchemy`` CLI commands and programmatic :doc:`Alembic migration commands <alembic/index>`.

    .. grid-item-card:: :octicon:`alert` Exceptions
      :link: exceptions
      :link-type: doc

      ``RepositoryError``, ``IntegrityError``, ``DuplicateKeyError``, ``ForeignKeyError``, ``NotFoundError``, and error wrappers.

    .. grid-item-card:: :octicon:`tools` Utilities
      :link: utils
      :link-type: doc

      Dataclass sentinels, dependency caches, fixture loaders, sync-to-async portals, and text helpers.

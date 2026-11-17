===================
FastAPI Integration
===================

Advanced Alchemy integrates with FastAPI through the ``AdvancedAlchemy`` extension, managing engine startup and disposal via ASGI lifespan hooks and providing ``Depends(...)`` callables for sessions, services, and OpenAPI query filters.

What's Included for FastAPI
---------------------------

.. list-table::
   :header-rows: 1
   :widths: 26 48 26

   * - Feature
     - Capabilities
     - Guide & API
   * - **Lifespan & Sessions**
     - Starts and disposes engines automatically and opens a fresh database session per request.
     - :doc:`API </reference/extensions/fastapi/index>`
   * - **Depends Helpers**
     - ``provide_session``, ``provide_service``, and ``provide_filters`` (with automatic OpenAPI query parameters).
     - :doc:`Guide <fastapi_dependencies>` · :doc:`API </reference/extensions/fastapi/index>`
   * - **Uploads & Multi-Binds**
     - Multipart ``UploadFile`` persistence via ``StoredObject`` and multi-database bind configurations.
     - :doc:`Guide <fastapi_storage>` · :doc:`API </reference/types>`
   * - **Migrations CLI**
     - Works directly with the ``alchemy`` CLI to generate and run Alembic migrations.
     - :doc:`CLI Guide </usage/cli>`

Installation
------------

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[fastapi,aiosqlite]"

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[fastapi,aiosqlite]"

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[fastapi,aiosqlite]"

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[fastapi,aiosqlite]"

Building a FastAPI Service Step by Step
---------------------------------------

.. tab-set::

    .. tab-item:: 1. Quick Extension Setup

        .. code-block:: python

            from fastapi import FastAPI
            from advanced_alchemy.extensions.fastapi import (
                AdvancedAlchemy,
                AsyncSessionConfig,
                SQLAlchemyAsyncConfig,
            )

            app = FastAPI()
            alchemy = AdvancedAlchemy(
                config=SQLAlchemyAsyncConfig(
                    connection_string="sqlite+aiosqlite:///:memory:",
                    session_config=AsyncSessionConfig(expire_on_commit=False),
                    create_all=True,
                    commit_mode="autocommit",
                ),
                app=app,
            )

    .. tab-item:: 2. Models, Schemas & Service

        .. literalinclude:: /examples/fastapi/service_di.py
            :language: python
            :start-at: class AuthorModel
            :end-before: def create_app

    .. tab-item:: 3. Routes & Filter Depends

        .. literalinclude:: /examples/fastapi/service_di.py
            :language: python
            :pyobject: create_app

.. tip::

    For multi-database configurations, pass the target bind key to ``alchemy.provide_session("reporting")`` or ``alchemy.provide_service(ReportService, key="reporting")``.

Cursor Pagination
-----------------

Pass ``pagination_type="cursor"`` to ``alchemy.provide_filters`` and return a ``CursorPagination``. Clients pass ``next_cursor`` back as ``?cursor=``; invalid tokens and sort fields return 422:

.. literalinclude:: /examples/fastapi/cursor_pagination.py
    :language: python
    :start-at: @router.get("/events")
    :end-before: app.include_router

See :doc:`/usage/repositories/cursor_pagination` for ordering keys, token signing, and indexing.

Complete Runnable App
---------------------

.. dropdown:: View Complete FastAPI Application
    :icon: code

    .. literalinclude:: /examples/fastapi/service_di.py
        :language: python

Related Guides
--------------

* :doc:`fastapi_dependencies`: Injecting services and OpenAPI search, sort, and pagination filters with ``Depends``.
* :doc:`fastapi_storage`: File uploads with ``UploadFile`` and multi-database setups.
* :doc:`/reference/extensions/fastapi/index`: FastAPI extension API reference.

.. toctree::
    :titlesonly:
    :hidden:

    Services & Filter Depends <fastapi_dependencies>
    File Storage & Multi-Binds <fastapi_storage>

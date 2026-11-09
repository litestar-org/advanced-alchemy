===================
FastAPI Integration
===================

Advanced Alchemy plugs into FastAPI through the ``AdvancedAlchemy`` extension, managing database startup/shutdown automatically and giving your routes clean ``Depends(...)`` helpers for sessions, services, and OpenAPI-documented search/pagination filters.

What's Included for FastAPI
---------------------------

.. list-table::
   :header-rows: 1
   :widths: 26 48 26

   * - Feature
     - What It Gives You
     - Guide & API
   * - **Lifespan & Sessions**
     - Starts and disposes engines automatically and opens a fresh database session per request.
     - :doc:`API </reference/extensions/fastapi/index>`
   * - **Depends Helpers**
     - ``provide_session``, ``provide_service``, and ``provide_filters`` (with automatic Swagger UI query params).
     - :doc:`API </reference/extensions/fastapi/index>`
   * - **Uploads & Multi-Binds**
     - Multipart ``UploadFile`` storage columns and support for multiple databases in one app.
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

            uv add advanced-alchemy fastapi aiosqlite

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install advanced-alchemy fastapi aiosqlite

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add advanced-alchemy fastapi aiosqlite

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add advanced-alchemy fastapi aiosqlite

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

    Using multiple databases? Pass the bind key to ``alchemy.provide_session("reporting")`` or ``alchemy.provide_service(ReportService, key="reporting")``.

Complete Runnable App
---------------------

.. dropdown:: View Complete FastAPI Application
    :icon: code

    .. literalinclude:: /examples/fastapi/service_di.py
        :language: python

Related Guides
--------------

* :doc:`fastapi_storage` — File uploads with ``UploadFile`` and multi-database setups.
* :doc:`/reference/extensions/fastapi/index` — FastAPI extension API reference.

.. toctree::
    :titlesonly:
    :hidden:

    File Storage & Multi-Binds <fastapi_storage>

===================
FastAPI Integration
===================

Advanced Alchemy integrates with FastAPI through :class:`~advanced_alchemy.extensions.fastapi.AdvancedAlchemy`, providing engine lifecycle management, request-scoped SQLAlchemy sessions, service and filter dependency generators, and CLI migration commands.

Installation
------------

Install Advanced Alchemy with FastAPI and an async database driver:

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

Extension Initialization
------------------------

Configure :class:`~advanced_alchemy.extensions.fastapi.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.extensions.fastapi.SQLAlchemySyncConfig` and bind :class:`~advanced_alchemy.extensions.fastapi.AdvancedAlchemy` to your FastAPI application:

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

Models, Schemas, and Services
-----------------------------

Define declarative SQLAlchemy models, Pydantic schemas, and repository services:

.. literalinclude:: /examples/fastapi/service_di.py
    :language: python
    :start-at: class AuthorModel
    :end-before: def create_app

Dependency Injection and Filters
--------------------------------

Use ``alchemy.provide_session()``, ``alchemy.provide_service(...)``, and ``alchemy.provide_filters(...)`` with FastAPI's ``Depends(...)`` to inject database sessions, services, and OpenAPI-documented query filters (IDs, search strings, boolean flags, enum choices, date ranges, and pagination) into route handlers:

.. literalinclude:: /examples/fastapi/service_di.py
    :language: python
    :pyobject: create_app

When multiple database configurations are registered, pass the target ``bind_key`` to ``alchemy.provide_session("reporting")`` or ``alchemy.provide_service(ReportService, key="reporting")``.

Complete Runnable Example
-------------------------

The complete runnable example in ``docs/examples/fastapi/service_di.py`` exercises service and filter dependency injection in-process using FastAPI's ``TestClient``:

.. literalinclude:: /examples/fastapi/service_di.py
    :language: python

Related Guides
--------------

- :doc:`fastapi_storage` — Declarative file storage, signed URLs, and multipart uploads in FastAPI.
- :doc:`/reference/extensions/fastapi/index` — FastAPI extension API reference.

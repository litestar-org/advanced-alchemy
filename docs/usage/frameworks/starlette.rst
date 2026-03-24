======================
Starlette Integration
======================

Advanced Alchemy integrates with Starlette through an application helper that initializes SQLAlchemy configs,
manages request-scoped sessions, and exposes engine/session accessors for route handlers.

Basic Setup
-----------

Initialize the extension with a Starlette app and one or more SQLAlchemy configs:

.. code-block:: python

    from starlette.applications import Starlette

    from advanced_alchemy.extensions.starlette import (
        AdvancedAlchemy,
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
    )

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        commit_mode="autocommit",
    )

    app = Starlette()
    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)

Working with Sessions in Routes
-------------------------------

Use the helper methods to access request-scoped sessions and the configured engine:

.. code-block:: python

    from sqlalchemy import text
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def healthcheck(request: Request) -> JSONResponse:
        session = alchemy.get_async_session(request)
        await session.execute(text("SELECT 1"))

        engine = alchemy.get_async_engine()
        return JSONResponse({"dialect": engine.dialect.name, "status": "ok"})

    app.router.routes.append(Route("/health", endpoint=healthcheck))

Commit Modes
------------

Starlette integration supports the same commit strategies as the core SQLAlchemy configs:

.. code-block:: python

    write_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        commit_mode="autocommit_include_redirect",
    )

    alchemy = AdvancedAlchemy(config=write_config, app=app)

Multiple Binds
--------------

Provide a sequence of configs when you need more than one bind key:

.. code-block:: python

    from advanced_alchemy.extensions.starlette import SQLAlchemySyncConfig

    alchemy = AdvancedAlchemy(
        config=[
            SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
            SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", bind_key="reporting"),
        ],
        app=app,
    )

    async_session = alchemy.get_async_config()
    reporting_session = alchemy.get_sync_config("reporting")

Notes
-----

- ``AdvancedAlchemy(config=..., app=app)`` calls ``init_app()`` for you.
- Sessions are stored on ``request.state`` and are reused within the same request.
- Use ``get_session(request)`` when your code should support either sync or async configs.

==================
Sanic Integration
==================

Advanced Alchemy integrates with Sanic through an extension that manages engines, request-scoped sessions,
and bind-key lookups for both async and sync SQLAlchemy configurations.

Basic Setup
-----------

Configure a Sanic app with ``SQLAlchemyAsyncConfig`` or ``SQLAlchemySyncConfig`` and register the extension:

.. code-block:: python

    from sanic import Sanic

    from advanced_alchemy.extensions.sanic import (
        AdvancedAlchemy,
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
    )

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
    )

    app = Sanic("advanced-alchemy-example")
    alchemy = AdvancedAlchemy(sqlalchemy_config=alchemy_config)
    alchemy.register(app)

Accessing the Engine and Session
--------------------------------

The extension stores configured engines on ``app.ctx`` and provides helpers for request-scoped sessions:

.. code-block:: python

    from sanic import HTTPResponse, Request
    from sqlalchemy import text

    @app.get("/health")
    async def healthcheck(request: Request) -> HTTPResponse:
        engine = getattr(request.app.ctx, alchemy.get_config().engine_key)
        session = alchemy.get_async_session(request)

        await session.execute(text("SELECT 1"))
        assert engine is alchemy.get_async_engine()
        return HTTPResponse(status=200)

Use ``alchemy.get_session(request)`` when you want the same code path to support either sync or async configs.

Multiple Binds
--------------

You can register more than one SQLAlchemy configuration and select them by bind key:

.. code-block:: python

    from advanced_alchemy.extensions.sanic import SQLAlchemySyncConfig

    alchemy = AdvancedAlchemy(
        sqlalchemy_config=[
            SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
            SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", bind_key="reporting"),
        ],
        sanic_app=app,
    )

    default_config = alchemy.get_config()
    reporting_config = alchemy.get_config("reporting")

    assert default_config.bind_key == "default"
    assert reporting_config.bind_key == "reporting"

Notes
-----

- Register the extension once per application with ``alchemy.register(app)`` or by passing ``sanic_app=app``.
- Request sessions are created lazily through ``get_session()`` / ``get_async_session()`` and tracked on ``request.ctx``.
- Engine objects are stored on ``app.ctx`` using each config's ``engine_key``.

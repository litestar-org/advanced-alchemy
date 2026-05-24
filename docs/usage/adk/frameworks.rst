==========
Frameworks
==========

Framework integrations adapt the same ``ADKServiceConfig`` into each framework's
dependency mechanism. They compose with the existing Advanced Alchemy extension
for that framework; they do not create database engines or sessions themselves.

Litestar
--------

.. code-block:: python

    from advanced_alchemy.extensions.adk import ADKServiceConfig
    from advanced_alchemy.extensions.adk.plugins.litestar import ADKPlugin
    from advanced_alchemy.extensions.litestar import SQLAlchemyInitPlugin

    adk_config = ADKServiceConfig(
        session_model_config=adk_models,
        memory_model=ADKMemory,
    )

    app = Litestar(
        route_handlers=[...],
        plugins=[
            SQLAlchemyInitPlugin(config=alchemy_config),
            ADKPlugin(adk_config),
        ],
    )

For vector memory, pass ``memory_embedding_provider`` to ``ADKServiceConfig`` and
use a memory model with an ``embedding`` column. The framework helpers pass that
provider through to ``ADKAsyncMemoryService``.

FastAPI
-------

.. code-block:: python

    from typing import Annotated

    from fastapi import Depends, FastAPI

    from advanced_alchemy.extensions.adk.plugins.fastapi import setup_adk

    app = FastAPI()
    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
    adk = setup_adk(app, config=ADKServiceConfig(session_model_config=adk_models))

    SessionService = Annotated[
        ADKAsyncSessionService,
        Depends(adk.provide_session_service(alchemy.provide_async_session())),
    ]

Flask
-----

.. code-block:: python

    from advanced_alchemy.extensions.adk.plugins.flask import ADKFlaskExtension

    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
    adk = ADKFlaskExtension(ADKServiceConfig(session_model_config=adk_models), app=app)

    @app.get("/sessions/<session_id>")
    def get_session(session_id: str) -> dict[str, str]:
        service = adk.get_adk_session_service()
        session = service.get_session(app_name="support-bot", user_id="user-123", session_id=session_id)
        return {"id": session.id} if session else {"id": ""}

Starlette
---------

.. code-block:: python

    from advanced_alchemy.extensions.adk.plugins.starlette import setup_adk

    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
    setup_adk(
        app,
        config=ADKServiceConfig(session_model_config=adk_models),
        alchemy=alchemy,
    )

    async def handler(request: Request) -> JSONResponse:
        service = request.state.adk_session_service
        session = await service.create_session(app_name="support-bot", user_id="user-123")
        return JSONResponse({"id": session.id})

Sanic
-----

.. code-block:: python

    from advanced_alchemy.extensions.adk.plugins.sanic import ADKSanicExtension

    alchemy = AdvancedAlchemy(sqlalchemy_config=alchemy_config, sanic_app=app)
    ADKSanicExtension(
        config=ADKServiceConfig(session_model_config=adk_models),
        sanic_app=app,
        alchemy=alchemy,
    )

    @app.get("/sessions")
    async def create_session(request: Request) -> HTTPResponse:
        service = request.ctx.adk_session_service
        session = await service.create_session(app_name="support-bot", user_id="user-123")
        return json({"id": session.id})

All framework helpers register a ``StaleSessionError`` handler that maps stale
session appends to HTTP 409 responses.

Runnable minimal examples are available under ``examples/litestar/adk_example.py``,
``examples/fastapi/adk_example.py``, ``examples/flask/adk_example.py``,
``examples/starlette/adk_example.py``, and ``examples/sanic_adk_example.py``.

==========
Frameworks
==========

Framework integrations adapt the same ``ADKServiceConfig`` into each framework's
dependency mechanism. They compose with the existing Advanced Alchemy extension
for that framework; they do not create database engines or sessions themselves.

Litestar
--------

.. code-block:: python

    from litestar import Litestar

    from advanced_alchemy.extensions.adk import (
        ADKAppStateModelMixin,
        ADKArtifactModelMixin,
        ADKEventModelMixin,
        ADKMemoryModelMixin,
        ADKServiceConfig,
        ADKSessionModelConfig,
        ADKSessionModelMixin,
        ADKUserStateModelMixin,
    )
    from advanced_alchemy.extensions.adk.plugins.litestar import ADKPlugin
    from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyInitPlugin


    class ADKSession(ADKSessionModelMixin):
        __tablename__ = "fw_adk_sessions"


    class ADKEvent(ADKEventModelMixin):
        __tablename__ = "fw_adk_events"


    class ADKAppState(ADKAppStateModelMixin):
        __tablename__ = "fw_adk_app_states"


    class ADKUserState(ADKUserStateModelMixin):
        __tablename__ = "fw_adk_user_states"


    class ADKArtifact(ADKArtifactModelMixin):
        __tablename__ = "fw_adk_artifacts"


    class ADKMemory(ADKMemoryModelMixin):
        __tablename__ = "fw_adk_memories"


    adk_models = ADKSessionModelConfig(
        session_model=ADKSession,
        event_model=ADKEvent,
        app_state_model=ADKAppState,
        user_state_model=ADKUserState,
        artifact_model=ADKArtifact,
    )
    adk_config = ADKServiceConfig(
        session_model_config=adk_models,
        memory_model=ADKMemory,
    )
    litestar_app = Litestar(
        route_handlers=[],
        plugins=[
            SQLAlchemyInitPlugin(config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")),
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

    from advanced_alchemy.extensions.adk import ADKAsyncSessionService
    from advanced_alchemy.extensions.adk.plugins.fastapi import setup_adk
    from advanced_alchemy.extensions.fastapi import AdvancedAlchemy as FastAPIAlchemy
    from advanced_alchemy.extensions.fastapi import SQLAlchemyAsyncConfig as FastAPIAsyncConfig

    fastapi_app = FastAPI()
    fastapi_alchemy = FastAPIAlchemy(
        config=FastAPIAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
        app=fastapi_app,
    )
    fastapi_adk = setup_adk(fastapi_app, config=ADKServiceConfig(session_model_config=adk_models))
    SessionService = Annotated[
        ADKAsyncSessionService,
        Depends(fastapi_adk.provide_session_service(fastapi_alchemy.provide_async_session())),
    ]

Flask
-----

.. code-block:: python

    from flask import Flask

    from advanced_alchemy.extensions.adk.plugins.flask import ADKFlaskExtension
    from advanced_alchemy.extensions.flask import AdvancedAlchemy as FlaskAlchemy
    from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig as FlaskSyncConfig

    flask_app = Flask(__name__)
    flask_alchemy = FlaskAlchemy(
        config=FlaskSyncConfig(connection_string="sqlite:///:memory:"),
        app=flask_app,
    )
    flask_adk = ADKFlaskExtension(ADKServiceConfig(session_model_config=adk_models), app=flask_app)

Starlette
---------

.. code-block:: python

    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from advanced_alchemy.extensions.adk.plugins.starlette import setup_adk as setup_starlette_adk
    from advanced_alchemy.extensions.starlette import AdvancedAlchemy as StarletteAlchemy
    from advanced_alchemy.extensions.starlette import SQLAlchemyAsyncConfig as StarletteAsyncConfig

    starlette_app = Starlette()
    starlette_alchemy = StarletteAlchemy(
        config=StarletteAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
        app=starlette_app,
    )
    setup_starlette_adk(
        starlette_app,
        config=ADKServiceConfig(session_model_config=adk_models),
        alchemy=starlette_alchemy,
    )


    async def starlette_handler(request: Request) -> JSONResponse:
        service = request.state.adk_session_service
        session = await service.create_session(app_name="support-bot", user_id="user-123")
        return JSONResponse({"id": session.id})

Sanic
-----

.. code-block:: python

    from sanic import Sanic

    from advanced_alchemy.extensions.adk.plugins.sanic import ADKSanicExtension
    from advanced_alchemy.extensions.sanic import AdvancedAlchemy as SanicAlchemy
    from advanced_alchemy.extensions.sanic import SQLAlchemyAsyncConfig as SanicAsyncConfig

    sanic_app = Sanic("ADKDocsApp")
    sanic_alchemy = SanicAlchemy(
        sqlalchemy_config=SanicAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
        sanic_app=sanic_app,
    )
    ADKSanicExtension(
        config=ADKServiceConfig(session_model_config=adk_models),
        sanic_app=sanic_app,
        alchemy=sanic_alchemy,
    )

All framework helpers register a ``StaleSessionError`` handler that maps stale
session appends to HTTP 409 responses.

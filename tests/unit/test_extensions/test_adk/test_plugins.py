import sys
from types import SimpleNamespace
from typing import Annotated, Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

if sys.version_info < (3, 10):
    pytest.skip("google-adk v2 requires Python 3.10+", allow_module_level=True)

from advanced_alchemy.extensions.adk import ADKServiceConfig, StaleSessionError
from tests.unit.test_extensions.test_adk.fixtures import SESSION_MODEL_CONFIG, SampleADKMemory


def test_service_config_resolves_optional_service_models() -> None:
    def embed_text(text: str) -> list[float]:
        return [float(len(text))]

    config = ADKServiceConfig(
        session_model_config=SESSION_MODEL_CONFIG,
        memory_model=SampleADKMemory,
        memory_embedding_provider=embed_text,
        use_vector_memory=False,
        vector_distance_metric="l2",
    )

    assert config.resolved_artifact_model is SESSION_MODEL_CONFIG.artifact_model
    assert config.resolved_session_model_config.artifact_model is SESSION_MODEL_CONFIG.artifact_model
    assert config.memory_model is SampleADKMemory
    service = config.create_async_memory_service(AsyncSession())
    assert service.embedding_provider is embed_text
    assert service.use_vector is False
    assert service.vector_distance_metric == "l2"


async def test_litestar_plugin_registers_dependencies_encoders_and_handler() -> None:
    from litestar.config.app import AppConfig

    from advanced_alchemy.extensions.adk.plugins.litestar import ADKPlugin

    app_config = ADKPlugin(
        ADKServiceConfig(session_model_config=SESSION_MODEL_CONFIG, memory_model=SampleADKMemory),
    ).on_app_init(AppConfig())

    assert {"adk_session_service", "adk_artifact_service", "adk_memory_service"} <= set(app_config.dependencies)
    assert StaleSessionError in app_config.exception_handlers
    assert app_config.type_encoders
    assert "ADKAsyncSessionService" in app_config.signature_namespace

    provider = app_config.dependencies["adk_session_service"].dependency
    assert list(provider.__signature__.parameters) == ["db_session"]  # type: ignore[attr-defined]

    db_session = AsyncSession()
    service = await provider(db_session=db_session)
    assert service.session is db_session
    assert service.session_model is SESSION_MODEL_CONFIG.session_model
    await db_session.close()


def test_fastapi_setup_registers_exception_handler_and_dependencies() -> None:
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    from fastapi import Depends

    from advanced_alchemy.extensions.adk.plugins.fastapi import setup_adk

    app = fastapi.FastAPI()
    adk = setup_adk(app, config=ADKServiceConfig(session_model_config=SESSION_MODEL_CONFIG))
    db_session = AsyncSession()

    async def provide_db_session() -> AsyncSession:
        return db_session

    @app.get("/service")
    async def get_service(
        service: Annotated[Any, Depends(adk.provide_session_service(provide_db_session))],
    ) -> dict[str, str]:
        return {"service": type(service).__name__}

    @app.get("/stale")
    async def get_stale() -> None:
        raise StaleSessionError("stale")

    with testclient.TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/service").json() == {"service": "ADKAsyncSessionService"}
        response = client.get("/stale")
        assert response.status_code == 409
        assert response.json()["error"] == "stale_session"


def test_flask_extension_registers_exception_handler() -> None:
    flask = pytest.importorskip("flask")

    from advanced_alchemy.extensions.adk.plugins.flask import ADKFlaskExtension

    app = flask.Flask(__name__)
    extension = ADKFlaskExtension(ADKServiceConfig(session_model_config=SESSION_MODEL_CONFIG), app=app)

    assert app.extensions["advanced_alchemy_adk"] is extension

    @app.route("/stale")
    def stale() -> None:
        raise StaleSessionError("stale")

    response = app.test_client().get("/stale")
    assert response.status_code == 409
    assert response.json["error"] == "stale_session"


def test_starlette_setup_attaches_services_to_request_state() -> None:
    starlette = pytest.importorskip("starlette.applications")
    responses = pytest.importorskip("starlette.responses")
    routing = pytest.importorskip("starlette.routing")
    testclient = pytest.importorskip("starlette.testclient")

    from advanced_alchemy.extensions.adk.plugins.starlette import setup_adk

    db_session = AsyncSession()

    class Alchemy:
        def get_async_session(self, request: object, key: object = None) -> AsyncSession:
            return db_session

    async def service_route(request: object) -> object:
        service = request.state.adk_session_service  # type: ignore[attr-defined]
        return responses.JSONResponse({"service": type(service).__name__})

    async def stale_route(request: object) -> None:
        raise StaleSessionError("stale")

    app = starlette.Starlette(
        routes=[
            routing.Route("/service", service_route),
            routing.Route("/stale", stale_route),
        ],
    )
    setup_adk(app, config=ADKServiceConfig(session_model_config=SESSION_MODEL_CONFIG), alchemy=Alchemy())

    with testclient.TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/service").json() == {"service": "ADKAsyncSessionService"}
        response = client.get("/stale")
        assert response.status_code == 409
        assert response.json()["error"] == "stale_session"


def test_sanic_extension_injects_services_from_request_context() -> None:
    pytest.importorskip("sanic_ext")

    from advanced_alchemy.extensions.adk.plugins.sanic import ADKSanicExtension

    db_session = AsyncSession()
    extension = ADKSanicExtension(
        config=ADKServiceConfig(session_model_config=SESSION_MODEL_CONFIG, memory_model=SampleADKMemory),
        session_context_key="db_session",
    )
    request = SimpleNamespace(ctx=SimpleNamespace(db_session=db_session), app=SimpleNamespace(ctx=SimpleNamespace()))

    extension.inject_services(request)

    assert type(request.ctx.adk_session_service).__name__ == "ADKAsyncSessionService"
    assert type(request.ctx.adk_artifact_service).__name__ == "ADKAsyncArtifactService"
    assert type(request.ctx.adk_memory_service).__name__ == "ADKAsyncMemoryService"

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from advanced_alchemy.extensions.adk import ADKServiceConfig
from advanced_alchemy.extensions.adk.plugins.starlette import setup_adk
from advanced_alchemy.extensions.starlette import AdvancedAlchemy, SQLAlchemyAsyncConfig
from examples.adk_models import ADK_METADATA, ADK_MODELS, ExampleADKMemory


async def create_session(request: Request) -> JSONResponse:
    service = request.state.adk_session_service
    session = await service.create_session(
        app_name="adk-example",
        user_id="user-123",
        state={"source": "starlette"},
    )
    return JSONResponse({"id": session.id, "state": session.state})


alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///adk-starlette.sqlite",
    metadata=ADK_METADATA,
    create_all=True,
)
app = Starlette(routes=[Route("/sessions", create_session, methods=["POST"])])
alchemy = AdvancedAlchemy(alchemy_config, app=app)
setup_adk(
    app,
    config=ADKServiceConfig(session_model_config=ADK_MODELS, memory_model=ExampleADKMemory),
    alchemy=alchemy,
)

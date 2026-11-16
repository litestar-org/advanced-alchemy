from sanic import Request, Sanic
from sanic.response import HTTPResponse, json

from advanced_alchemy.extensions.adk import ADKServiceConfig
from advanced_alchemy.extensions.adk.plugins.sanic import ADKSanicExtension
from advanced_alchemy.extensions.sanic import AdvancedAlchemy, SQLAlchemyAsyncConfig
from examples.adk_models import ADK_METADATA, ADK_MODELS, ExampleADKMemory

app = Sanic("adk-example")
alchemy = AdvancedAlchemy(
    sqlalchemy_config=SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///adk-sanic.sqlite",
        metadata=ADK_METADATA,
        create_all=True,
    ),
    sanic_app=app,
)
ADKSanicExtension(
    config=ADKServiceConfig(session_model_config=ADK_MODELS, memory_model=ExampleADKMemory),
    sanic_app=app,
    alchemy=alchemy,
)


@app.post("/sessions")
async def create_session(request: Request) -> HTTPResponse:
    service = request.ctx.adk_session_service
    session = await service.create_session(
        app_name="adk-example",
        user_id="user-123",
        state={"source": "sanic"},
    )
    return json({"id": session.id, "state": session.state})

from typing import Any

from litestar import Litestar, post

from advanced_alchemy.extensions.adk import ADKAsyncSessionService, ADKServiceConfig
from advanced_alchemy.extensions.adk.plugins.litestar import ADKPlugin
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyInitPlugin
from examples.adk_models import ADK_METADATA, ADK_MODELS, ExampleADKMemory


@post("/sessions")
async def create_session(adk_session_service: ADKAsyncSessionService) -> dict[str, Any]:
    session = await adk_session_service.create_session(
        app_name="adk-example",
        user_id="user-123",
        state={"source": "litestar"},
    )
    return {"id": session.id, "state": session.state}


alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///adk-litestar.sqlite",
    metadata=ADK_METADATA,
    create_all=True,
)
adk_config = ADKServiceConfig(session_model_config=ADK_MODELS, memory_model=ExampleADKMemory)

app = Litestar(
    route_handlers=[create_session],
    plugins=[
        SQLAlchemyInitPlugin(config=alchemy_config),
        ADKPlugin(adk_config),
    ],
)

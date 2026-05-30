from typing import Annotated, Any

from fastapi import Depends, FastAPI

from advanced_alchemy.extensions.adk import ADKAsyncSessionService, ADKServiceConfig
from advanced_alchemy.extensions.adk.plugins.fastapi import setup_adk
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig
from examples.adk_models import ADK_METADATA, ADK_MODELS, ExampleADKMemory

alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///adk-fastapi.sqlite",
    metadata=ADK_METADATA,
    create_all=True,
)
app = FastAPI()
alchemy = AdvancedAlchemy(alchemy_config, app=app)
adk = setup_adk(
    app,
    config=ADKServiceConfig(session_model_config=ADK_MODELS, memory_model=ExampleADKMemory),
)

SessionService = Annotated[
    ADKAsyncSessionService,
    Depends(adk.provide_session_service(alchemy.provide_async_session())),
]


@app.post("/sessions")
async def create_session(adk_session_service: SessionService) -> dict[str, Any]:
    session = await adk_session_service.create_session(
        app_name="adk-example",
        user_id="user-123",
        state={"source": "fastapi"},
    )
    return {"id": session.id, "state": session.state}

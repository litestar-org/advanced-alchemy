from typing import Any

from flask import Flask

from advanced_alchemy.extensions.adk import ADKServiceConfig
from advanced_alchemy.extensions.adk.plugins.flask import ADKFlaskExtension
from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig
from examples.adk_models import ADK_METADATA, ADK_MODELS, ExampleADKMemory

app = Flask(__name__)
alchemy = AdvancedAlchemy(
    SQLAlchemySyncConfig(
        connection_string="sqlite:///adk-flask.sqlite",
        metadata=ADK_METADATA,
        create_all=True,
    ),
    app=app,
)
adk = ADKFlaskExtension(
    ADKServiceConfig(session_model_config=ADK_MODELS, memory_model=ExampleADKMemory),
    app=app,
)


@app.post("/sessions")
def create_session() -> dict[str, Any]:
    service = adk.get_adk_session_service()
    session = service.create_session(
        app_name="adk-example",
        user_id="user-123",
        state={"source": "flask"},
    )
    return {"id": session.id, "state": session.state}

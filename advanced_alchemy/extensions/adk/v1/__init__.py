"""ADK v1 schema models."""

from advanced_alchemy.extensions.adk._types import ADKSchemaVersion, SchemaModels, register_schema
from advanced_alchemy.extensions.adk.v1._factories import with_owner_column
from advanced_alchemy.extensions.adk.v1.metadata import metadata
from advanced_alchemy.extensions.adk.v1.models import ADKAppState, ADKEvent, ADKMetadata, ADKSession, ADKUserState

register_schema(
    ADKSchemaVersion.V1,
    SchemaModels(
        metadata=metadata,
        session_model=ADKSession,
        event_model=ADKEvent,
        app_state_model=ADKAppState,
        user_state_model=ADKUserState,
        metadata_model=ADKMetadata,
    ),
)

__all__ = (
    "ADKAppState",
    "ADKEvent",
    "ADKMetadata",
    "ADKSession",
    "ADKUserState",
    "metadata",
    "with_owner_column",
)

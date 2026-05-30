from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.extensions.adk import (
    ADKAppStateModelMixin,
    ADKArtifactModelMixin,
    ADKEventModelMixin,
    ADKMemoryModelMixin,
    ADKSessionModelConfig,
    ADKSessionModelMixin,
    ADKUserStateModelMixin,
)


class ExampleADKSession(ADKSessionModelMixin):
    __tablename__ = "example_adk_sessions"

    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class ExampleADKEvent(ADKEventModelMixin):
    __tablename__ = "example_adk_events"


class ExampleADKAppState(ADKAppStateModelMixin):
    __tablename__ = "example_adk_app_states"


class ExampleADKUserState(ADKUserStateModelMixin):
    __tablename__ = "example_adk_user_states"


class ExampleADKArtifact(ADKArtifactModelMixin):
    __tablename__ = "example_adk_artifacts"


class ExampleADKMemory(ADKMemoryModelMixin):
    __tablename__ = "example_adk_memory_entries"


ADK_MODELS = ADKSessionModelConfig(
    session_model=ExampleADKSession,
    event_model=ExampleADKEvent,
    app_state_model=ExampleADKAppState,
    user_state_model=ExampleADKUserState,
    artifact_model=ExampleADKArtifact,
)
ADK_METADATA = ExampleADKSession.metadata

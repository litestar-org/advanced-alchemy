import sys
from typing import Optional

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

if sys.version_info < (3, 10):
    pytest.skip("google-adk v2 requires Python 3.10+", allow_module_level=True)

from advanced_alchemy.extensions.adk import (
    ADKAppStateModelMixin,
    ADKArtifactModelMixin,
    ADKEventModelMixin,
    ADKMemoryModelMixin,
    ADKSessionModelConfig,
    ADKSessionModelMixin,
    ADKUserStateModelMixin,
)


class SampleADKSession(ADKSessionModelMixin):
    __tablename__ = "test_adk_sessions"

    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class SampleADKEvent(ADKEventModelMixin):
    __tablename__ = "test_adk_events"


class SampleADKAppState(ADKAppStateModelMixin):
    __tablename__ = "test_adk_app_states"


class SampleADKUserState(ADKUserStateModelMixin):
    __tablename__ = "test_adk_user_states"


class SampleADKArtifact(ADKArtifactModelMixin):
    __tablename__ = "test_adk_artifacts"


class SampleADKMemory(ADKMemoryModelMixin):
    __tablename__ = "test_adk_memory_entries"


SESSION_MODEL_CONFIG = ADKSessionModelConfig(
    session_model=SampleADKSession,
    event_model=SampleADKEvent,
    app_state_model=SampleADKAppState,
    user_state_model=SampleADKUserState,
    artifact_model=SampleADKArtifact,
)

metadata = SampleADKSession.metadata

"""Shared configuration for ADK framework integrations."""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.adk._sync import ADKSyncSessionService
from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService
from advanced_alchemy.extensions.adk.memory import (
    ADKAsyncMemoryService,
    ADKMemoryEmbeddingProvider,
    ADKVectorDistanceMetric,
)
from advanced_alchemy.extensions.adk.models import (
    DEFAULT_ARTIFACT_BACKEND_KEY,
    ADKArtifactModelMixin,
    ADKMemoryModelMixin,
    ADKSessionModelConfig,
)
from advanced_alchemy.extensions.adk.service import ADKAsyncSessionService


@dataclass(frozen=True)
class ADKServiceConfig:
    """Framework integration configuration for ADK persistence services.

    The mapped models are user-owned classes that subclass the ADK model mixins.
    This mirrors the server-side session extension pattern and lets applications
    add their own columns, constraints, and metadata.
    """

    session_model_config: ADKSessionModelConfig
    memory_model: Optional[type[ADKMemoryModelMixin]] = None
    artifact_model: Optional[type[ADKArtifactModelMixin]] = None
    artifact_backend_key: str = DEFAULT_ARTIFACT_BACKEND_KEY
    memory_embedding_provider: Optional[ADKMemoryEmbeddingProvider] = None
    use_vector_memory: Optional[bool] = None
    vector_distance_metric: ADKVectorDistanceMetric = "cosine"
    session_dependency_key: str = "adk_session_service"
    artifact_dependency_key: str = "adk_artifact_service"
    memory_dependency_key: str = "adk_memory_service"

    @property
    def resolved_artifact_model(self) -> Optional[type[ADKArtifactModelMixin]]:
        """Return the artifact model configured for artifact persistence."""
        return self.artifact_model or self.session_model_config.artifact_model

    @property
    def resolved_session_model_config(self) -> ADKSessionModelConfig:
        """Return a session config that includes the configured artifact model."""
        artifact_model = self.resolved_artifact_model
        if artifact_model is self.session_model_config.artifact_model:
            return self.session_model_config
        return ADKSessionModelConfig(
            session_model=self.session_model_config.session_model,
            event_model=self.session_model_config.event_model,
            app_state_model=self.session_model_config.app_state_model,
            user_state_model=self.session_model_config.user_state_model,
            artifact_model=artifact_model,
        )

    def create_async_session_service(self, session: AsyncSession) -> ADKAsyncSessionService:
        """Create an async ADK session service for a database session."""
        return ADKAsyncSessionService(session, model_config=self.resolved_session_model_config)

    def create_sync_session_service(self, session: Session) -> ADKSyncSessionService:
        """Create a sync ADK session helper for a database session."""
        return ADKSyncSessionService(session, model_config=self.resolved_session_model_config)

    def create_async_artifact_service(self, session: AsyncSession) -> ADKAsyncArtifactService:
        """Create an async ADK artifact service for a database session."""
        artifact_model = self.resolved_artifact_model
        if artifact_model is None:
            msg = "Configure an artifact model subclassing ADKArtifactModelMixin to use ADK artifact services."
            raise ImproperConfigurationError(msg)
        return ADKAsyncArtifactService(
            session,
            artifact_model=artifact_model,
            backend_key=self.artifact_backend_key,
        )

    def create_async_memory_service(self, session: AsyncSession) -> ADKAsyncMemoryService:
        """Create an async ADK memory service for a database session."""
        if self.memory_model is None:
            msg = "Configure a memory model subclassing ADKMemoryModelMixin to use ADK memory services."
            raise ImproperConfigurationError(msg)
        return ADKAsyncMemoryService(
            session,
            memory_model=self.memory_model,
            embedding_provider=self.memory_embedding_provider,
            use_vector=self.use_vector_memory,
            vector_distance_metric=self.vector_distance_metric,
        )


__all__ = ("ADKServiceConfig",)

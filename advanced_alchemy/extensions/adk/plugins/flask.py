"""Flask integration for Google ADK persistence services."""

from typing import TYPE_CHECKING, Any, Optional, Union, cast

from flask import current_app, g, jsonify
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.adk._exceptions import StaleSessionError
from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService
from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService
from advanced_alchemy.extensions.adk.plugins._config import ADKServiceConfig
from advanced_alchemy.extensions.adk.service import ADKAsyncSessionService, ADKSyncSessionService

if TYPE_CHECKING:
    from flask import Flask, Response

    from advanced_alchemy.extensions.flask.extension import AdvancedAlchemy


def stale_session_exception_handler(exc: Any) -> "tuple[Response, int]":
    """Convert ADK optimistic concurrency failures into HTTP 409 responses."""
    return jsonify({"error": "stale_session", "detail": str(exc)}), 409


class ADKFlaskExtension:
    """Flask extension that exposes ADK services from Advanced Alchemy sessions."""

    def __init__(self, config: ADKServiceConfig, app: 'Optional["Flask"]' = None) -> None:
        self.config = config
        if app is not None:
            self.init_app(app)

    def init_app(self, app: "Flask") -> None:
        """Register ADK helpers on a Flask application."""
        if "advanced_alchemy_adk" in app.extensions:
            msg = "ADK extension is already registered on this Flask application."
            raise ImproperConfigurationError(msg)
        app.extensions["advanced_alchemy_adk"] = self
        app.register_error_handler(StaleSessionError, stale_session_exception_handler)

    @staticmethod
    def _alchemy_extension() -> "AdvancedAlchemy":
        alchemy = current_app.extensions.get("advanced_alchemy")
        if alchemy is None:
            msg = "Advanced Alchemy Flask extension must be registered before ADK services can be created."
            raise ImproperConfigurationError(msg)
        return cast("AdvancedAlchemy", alchemy)

    def get_adk_session_service(
        self,
        bind_key: str = "default",
    ) -> Union[ADKAsyncSessionService, ADKSyncSessionService]:
        """Return a request-cached ADK session service."""
        cache_key = f"advanced_alchemy_adk_session_service_{bind_key}"
        if hasattr(g, cache_key):
            return cast("Union[ADKAsyncSessionService, ADKSyncSessionService]", getattr(g, cache_key))

        db_session = self._alchemy_extension().get_session(bind_key)
        service: Union[ADKAsyncSessionService, ADKSyncSessionService]
        if isinstance(db_session, AsyncSession):
            service = self.config.create_async_session_service(db_session)
        else:
            service = self.config.create_sync_session_service(db_session)
        setattr(g, cache_key, service)
        return service

    def get_adk_artifact_service(self, bind_key: str = "default") -> ADKAsyncArtifactService:
        """Return a request-cached ADK artifact service."""
        cache_key = f"advanced_alchemy_adk_artifact_service_{bind_key}"
        if hasattr(g, cache_key):
            return cast("ADKAsyncArtifactService", getattr(g, cache_key))

        db_session = self._alchemy_extension().get_session(bind_key)
        if not isinstance(db_session, AsyncSession):
            msg = "ADK artifact service requires an async SQLAlchemy session."
            raise ImproperConfigurationError(msg)
        service = self.config.create_async_artifact_service(db_session)
        setattr(g, cache_key, service)
        return service

    def get_adk_memory_service(self, bind_key: str = "default") -> ADKAsyncMemoryService:
        """Return a request-cached ADK memory service."""
        cache_key = f"advanced_alchemy_adk_memory_service_{bind_key}"
        if hasattr(g, cache_key):
            return cast("ADKAsyncMemoryService", getattr(g, cache_key))

        db_session = self._alchemy_extension().get_session(bind_key)
        if not isinstance(db_session, AsyncSession):
            msg = "ADK memory service requires an async SQLAlchemy session."
            raise ImproperConfigurationError(msg)
        service = self.config.create_async_memory_service(db_session)
        setattr(g, cache_key, service)
        return service


__all__ = ("ADKFlaskExtension", "stale_session_exception_handler")

"""FastAPI integration helpers for Google ADK persistence services."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.extensions.adk._exceptions import StaleSessionError
from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService
from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService
from advanced_alchemy.extensions.adk.plugins._config import ADKServiceConfig
from advanced_alchemy.extensions.adk.service import ADKAsyncSessionService


async def stale_session_exception_handler(_: Request, exc: StaleSessionError) -> JSONResponse:
    """Convert ADK optimistic concurrency failures into HTTP 409 responses."""
    return JSONResponse(
        status_code=409,
        content={"error": "stale_session", "detail": str(exc)},
    )


def create_adk_session_dependency(
    config: ADKServiceConfig,
    db_session_dependency: Callable[..., AsyncSession],
) -> Callable[..., Awaitable[ADKAsyncSessionService]]:
    """Create a FastAPI dependency for ``ADKAsyncSessionService``."""

    async def provide_adk_session_service(
        db_session: Annotated[AsyncSession, Depends(db_session_dependency)],
    ) -> ADKAsyncSessionService:
        return config.create_async_session_service(db_session)

    return provide_adk_session_service


def create_adk_artifact_dependency(
    config: ADKServiceConfig,
    db_session_dependency: Callable[..., AsyncSession],
) -> Callable[..., Awaitable[ADKAsyncArtifactService]]:
    """Create a FastAPI dependency for ``ADKAsyncArtifactService``."""

    async def provide_adk_artifact_service(
        db_session: Annotated[AsyncSession, Depends(db_session_dependency)],
    ) -> ADKAsyncArtifactService:
        return config.create_async_artifact_service(db_session)

    return provide_adk_artifact_service


def create_adk_memory_dependency(
    config: ADKServiceConfig,
    db_session_dependency: Callable[..., AsyncSession],
) -> Callable[..., Awaitable[ADKAsyncMemoryService]]:
    """Create a FastAPI dependency for ``ADKAsyncMemoryService``."""

    async def provide_adk_memory_service(
        db_session: Annotated[AsyncSession, Depends(db_session_dependency)],
    ) -> ADKAsyncMemoryService:
        return config.create_async_memory_service(db_session)

    return provide_adk_memory_service


class ADKFastAPI:
    """FastAPI helper that registers ADK exception handling and dependency factories."""

    def __init__(self, config: ADKServiceConfig, app: Optional[object] = None) -> None:
        self.config = config
        if app is not None:
            self.init_app(app)

    def init_app(self, app: object) -> None:
        """Register ADK state and exception handlers with a FastAPI app."""
        app.state.advanced_alchemy_adk = self  # type: ignore[attr-defined]
        app.add_exception_handler(StaleSessionError, stale_session_exception_handler)  # type: ignore[attr-defined]

    def provide_session_service(
        self, db_session_dependency: Callable[..., AsyncSession]
    ) -> Callable[..., Awaitable[ADKAsyncSessionService]]:
        """Return a FastAPI dependency for ``ADKAsyncSessionService``."""
        return create_adk_session_dependency(self.config, db_session_dependency)

    def provide_artifact_service(
        self,
        db_session_dependency: Callable[..., AsyncSession],
    ) -> Callable[..., Awaitable[ADKAsyncArtifactService]]:
        """Return a FastAPI dependency for ``ADKAsyncArtifactService``."""
        return create_adk_artifact_dependency(self.config, db_session_dependency)

    def provide_memory_service(
        self, db_session_dependency: Callable[..., AsyncSession]
    ) -> Callable[..., Awaitable[ADKAsyncMemoryService]]:
        """Return a FastAPI dependency for ``ADKAsyncMemoryService``."""
        return create_adk_memory_dependency(self.config, db_session_dependency)


def setup_adk(app: object, *, config: ADKServiceConfig) -> ADKFastAPI:
    """Configure ADK support for a FastAPI app."""
    return ADKFastAPI(config, app=app)


__all__ = (
    "ADKFastAPI",
    "create_adk_artifact_dependency",
    "create_adk_memory_dependency",
    "create_adk_session_dependency",
    "setup_adk",
    "stale_session_exception_handler",
)

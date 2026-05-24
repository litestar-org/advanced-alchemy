"""Starlette integration for Google ADK persistence services."""

from typing import TYPE_CHECKING, Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.adk._exceptions import StaleSessionError
from advanced_alchemy.extensions.adk.plugins._config import ADKServiceConfig

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.types import ASGIApp, ExceptionHandler, Receive, Scope, Send

    from advanced_alchemy.extensions.starlette.extension import AdvancedAlchemy


async def stale_session_exception_handler(_: Request, exc: StaleSessionError) -> JSONResponse:
    """Convert ADK optimistic concurrency failures into HTTP 409 responses."""
    return JSONResponse(
        status_code=409,
        content={"error": "stale_session", "detail": str(exc)},
    )


class ADKStarletteMiddleware:
    """Attach ADK services to ``request.state`` from an Advanced Alchemy session."""

    def __init__(
        self,
        app: "ASGIApp",
        *,
        config: ADKServiceConfig,
        alchemy: 'Optional["AdvancedAlchemy"]' = None,
        bind_key: Optional[str] = None,
        session_state_key: Optional[str] = None,
    ) -> None:
        self.app = app
        self.config = config
        self.alchemy = alchemy
        self.bind_key = bind_key
        self.session_state_key = session_state_key

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        session = self._get_async_session(request)
        setattr(request.state, self.config.session_dependency_key, self.config.create_async_session_service(session))
        if self.config.resolved_artifact_model is not None:
            setattr(
                request.state, self.config.artifact_dependency_key, self.config.create_async_artifact_service(session)
            )
        if self.config.memory_model is not None:
            setattr(request.state, self.config.memory_dependency_key, self.config.create_async_memory_service(session))
        await self.app(scope, receive, send)

    def _get_async_session(self, request: Request) -> AsyncSession:
        if self.session_state_key is not None:
            session = getattr(request.state, self.session_state_key, None)
            if isinstance(session, AsyncSession):
                return session
        alchemy: Optional[AdvancedAlchemy] = self.alchemy or getattr(request.app.state, "advanced_alchemy", None)
        if alchemy is None:
            msg = "Advanced Alchemy Starlette extension must be registered or passed to ADKStarletteMiddleware."
            raise ImproperConfigurationError(msg)
        return alchemy.get_async_session(request, self.bind_key)


def setup_adk(
    app: "Starlette",
    *,
    config: ADKServiceConfig,
    alchemy: 'Optional["AdvancedAlchemy"]' = None,
    bind_key: Optional[str] = None,
    session_state_key: Optional[str] = None,
) -> None:
    """Register ADK middleware and exception handling on a Starlette app."""
    app.state.advanced_alchemy_adk = config
    app.add_exception_handler(StaleSessionError, cast("ExceptionHandler", stale_session_exception_handler))
    app.add_middleware(
        ADKStarletteMiddleware,
        config=config,
        alchemy=alchemy,
        bind_key=bind_key,
        session_state_key=session_state_key,
    )


__all__ = ("ADKStarletteMiddleware", "setup_adk", "stale_session_exception_handler")

"""Sanic integration for Google ADK persistence services."""
# pyright: reportMissingTypeArgument=false, reportUnnecessaryIsInstance=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnusedFunction=false

from typing import TYPE_CHECKING, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.exceptions import ImproperConfigurationError, MissingDependencyError
from advanced_alchemy.extensions.adk._exceptions import StaleSessionError
from advanced_alchemy.extensions.adk.plugins._config import ADKServiceConfig

try:
    from sanic.response import json
    from sanic_ext import Extend
    from sanic_ext.extensions.base import Extension

    SANIC_INSTALLED = True
except ModuleNotFoundError:  # pragma: no cover
    SANIC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]
    Extension = object  # type: ignore
    Extend = object  # type: ignore
    json = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from sanic import Request, Sanic
    from sanic.response import HTTPResponse
    from sanic_ext import Extend as SanicExtend

    from advanced_alchemy.extensions.sanic.extension import AdvancedAlchemy


async def stale_session_exception_handler(_: "Request", exc: StaleSessionError) -> "HTTPResponse":
    """Convert ADK optimistic concurrency failures into HTTP 409 responses."""
    return json({"error": "stale_session", "detail": str(exc)}, status=409)  # type: ignore[misc]


class ADKSanicExtension(Extension):  # type: ignore[no-untyped-call, misc, valid-type]
    """Sanic extension that attaches ADK services to ``request.ctx``."""

    name = "ADK"

    def __init__(
        self,
        *,
        config: ADKServiceConfig,
        sanic_app: Optional["Sanic"] = None,
        alchemy: 'Optional["AdvancedAlchemy"]' = None,
        bind_key: Optional[str] = None,
        session_context_key: Optional[str] = None,
    ) -> None:
        if not SANIC_INSTALLED:  # pragma: no cover
            msg = "Could not locate Sanic Extensions. Try: pip install sanic[ext]"
            raise MissingDependencyError(msg)
        self.config = config
        self.alchemy = alchemy
        self.bind_key = bind_key
        self.session_context_key = session_context_key
        self._app = sanic_app
        if self._app is not None:
            self.register(self._app)

    @property
    def sanic_app(self) -> "Sanic":
        """Return the configured Sanic app."""
        if self._app is None:  # pragma: no cover
            msg = "ADKSanicExtension has not been initialized with a Sanic app."
            raise ImproperConfigurationError(msg)
        return self._app

    def register(self, sanic_app: "Sanic") -> None:
        """Register the extension with a Sanic app."""
        self._app = sanic_app
        Extend.register(self)  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def startup(self, bootstrap: "SanicExtend") -> None:  # pyright: ignore[reportUnknownParameterType,reportInvalidTypeForm]
        """Register ADK request middleware and exception handling."""
        app = self.sanic_app
        app.ctx.advanced_alchemy_adk = self
        app.exception(StaleSessionError)(stale_session_exception_handler)

        @app.middleware("request")
        async def _advanced_alchemy_adk_request_middleware(request: "Request") -> None:
            self.inject_services(request)

    def inject_services(self, request: "Request") -> None:
        """Attach configured ADK services to a Sanic request context."""
        session = self._get_session(request)
        if isinstance(session, AsyncSession):
            setattr(request.ctx, self.config.session_dependency_key, self.config.create_async_session_service(session))
            if self.config.resolved_artifact_model is not None:
                setattr(
                    request.ctx, self.config.artifact_dependency_key, self.config.create_async_artifact_service(session)
                )
            if self.config.memory_model is not None:
                setattr(
                    request.ctx, self.config.memory_dependency_key, self.config.create_async_memory_service(session)
                )
        elif isinstance(session, Session):
            setattr(request.ctx, self.config.session_dependency_key, self.config.create_sync_session_service(session))
        else:  # pragma: no cover
            msg = f"Unsupported SQLAlchemy session type: {type(session).__name__}"
            raise ImproperConfigurationError(msg)

    def _get_session(self, request: "Request") -> Union[AsyncSession, Session]:
        if self.session_context_key is not None:
            session = getattr(request.ctx, self.session_context_key, None)
            if isinstance(session, (AsyncSession, Session)):
                return session
        alchemy: Optional[AdvancedAlchemy] = self.alchemy or getattr(request.app.ctx, "advanced_alchemy", None)
        if alchemy is None:
            msg = "Advanced Alchemy Sanic extension must be registered or passed to ADKSanicExtension."
            raise ImproperConfigurationError(msg)
        return alchemy.get_session(request, self.bind_key)


__all__ = ("ADKSanicExtension", "stale_session_exception_handler")

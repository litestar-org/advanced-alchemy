"""Litestar integration for Google ADK persistence services."""

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from litestar.di import Provide
from litestar.params import Dependency
from litestar.plugins import InitPluginProtocol
from litestar.response import Response
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.extensions.adk._exceptions import StaleSessionError
from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService
from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService
from advanced_alchemy.extensions.adk.plugins._config import ADKServiceConfig
from advanced_alchemy.extensions.adk.plugins._encoders import get_adk_type_encoders
from advanced_alchemy.extensions.adk.service import ADKAsyncSessionService
from advanced_alchemy.extensions.litestar.plugins import _slots_base

if TYPE_CHECKING:
    from litestar.config.app import AppConfig
    from litestar.connection import Request


def stale_session_exception_handler(_: "Request[Any, Any, Any]", exc: StaleSessionError) -> Response[dict[str, str]]:
    """Convert ADK optimistic concurrency failures into HTTP 409 responses."""
    return Response(
        content={"error": "stale_session", "detail": str(exc)},
        status_code=409,
    )


def _create_litestar_adk_provider(
    config: ADKServiceConfig,
    factory: Callable[[ADKServiceConfig, AsyncSession], Any],
    *,
    db_session_dependency_key: str,
    return_annotation: Any,
) -> Callable[..., Any]:
    async def provide_adk_service(*args: Any, **kwargs: Any) -> Any:
        db_session = cast("AsyncSession", args[0] if args else kwargs.get(db_session_dependency_key))
        return factory(config, db_session)

    session_param = inspect.Parameter(
        name=db_session_dependency_key,
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        default=Dependency(skip_validation=True),
        annotation="AsyncSession",
    )
    provider_signature = inspect.Signature(parameters=[session_param], return_annotation=return_annotation)
    provide_adk_service.__signature__ = provider_signature  # type: ignore[attr-defined]
    provide_adk_service.__annotations__ = {
        db_session_dependency_key: "AsyncSession",
        "return": return_annotation,
    }
    return provide_adk_service


def _session_service_factory(config: ADKServiceConfig, session: AsyncSession) -> ADKAsyncSessionService:
    return config.create_async_session_service(session)


def _artifact_service_factory(config: ADKServiceConfig, session: AsyncSession) -> ADKAsyncArtifactService:
    return config.create_async_artifact_service(session)


def _memory_service_factory(config: ADKServiceConfig, session: AsyncSession) -> ADKAsyncMemoryService:
    return config.create_async_memory_service(session)


class ADKPlugin(InitPluginProtocol, _slots_base.SlotsBase):
    """Litestar plugin that wires ADK services into Litestar dependency injection."""

    def __init__(
        self,
        config: ADKServiceConfig,
        *,
        db_session_dependency_key: str = "db_session",
        include_type_encoders: bool = True,
        set_stale_session_exception_handler: bool = True,
    ) -> None:
        """Initialize the ADK Litestar plugin.

        Args:
            config: Shared ADK service configuration.
            db_session_dependency_key: Litestar dependency key for the SQLAlchemy ``AsyncSession``.
            include_type_encoders: Register ADK/GenAI model type encoders.
            set_stale_session_exception_handler: Register a 409 handler for stale session writes.
        """
        self.config = config
        self.db_session_dependency_key = db_session_dependency_key
        self.include_type_encoders = include_type_encoders
        self.set_stale_session_exception_handler = set_stale_session_exception_handler

    def on_app_init(self, app_config: "AppConfig") -> "AppConfig":
        """Configure Litestar dependencies, encoders, and exception handlers."""
        dependencies = {
            self.config.session_dependency_key: Provide(
                _create_litestar_adk_provider(
                    self.config,
                    _session_service_factory,
                    db_session_dependency_key=self.db_session_dependency_key,
                    return_annotation=ADKAsyncSessionService,
                ),
            ),
        }
        if self.config.resolved_artifact_model is not None:
            dependencies[self.config.artifact_dependency_key] = Provide(
                _create_litestar_adk_provider(
                    self.config,
                    _artifact_service_factory,
                    db_session_dependency_key=self.db_session_dependency_key,
                    return_annotation=ADKAsyncArtifactService,
                ),
            )
        if self.config.memory_model is not None:
            dependencies[self.config.memory_dependency_key] = Provide(
                _create_litestar_adk_provider(
                    self.config,
                    _memory_service_factory,
                    db_session_dependency_key=self.db_session_dependency_key,
                    return_annotation=ADKAsyncMemoryService,
                ),
            )

        app_config.dependencies.update(dependencies)
        if self.include_type_encoders:
            app_config.type_encoders = {**get_adk_type_encoders(), **(app_config.type_encoders or {})}
        exception_handlers = cast("dict[Any, Any]", app_config.exception_handlers)  # pyright: ignore[reportUnknownMemberType]
        if self.set_stale_session_exception_handler and StaleSessionError not in exception_handlers:
            exception_handlers[StaleSessionError] = stale_session_exception_handler
        app_config.signature_namespace.update(
            {
                "ADKAsyncArtifactService": ADKAsyncArtifactService,
                "ADKAsyncMemoryService": ADKAsyncMemoryService,
                "ADKAsyncSessionService": ADKAsyncSessionService,
            },
        )
        return app_config


__all__ = ("ADKPlugin", "stale_session_exception_handler")

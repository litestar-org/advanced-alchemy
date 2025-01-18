from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable, Sequence, Union

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request  # noqa: TC002

from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session
    from starlette.applications import Starlette
    from starlette.responses import Response

    from advanced_alchemy.extensions.starlette.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig


class AdvancedAlchemy:
    """AdvancedAlchemy integration for Starlette applications.

    This class manages SQLAlchemy sessions and engine lifecycle within a Starlette application.
    It provides middleware for handling transactions based on commit strategies.

    Args:
        config (advanced_alchemy.config.asyncio.SQLAlchemyAsyncConfig | advanced_alchemy.config.sync.SQLAlchemySyncConfig):
            The SQLAlchemy configuration.
        app (starlette.applications.Starlette | None):
            The Starlette application instance. Defaults to None.
    """

    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
        app: Starlette | None = None,
    ) -> None:
        self._config = config if isinstance(config, Sequence) else [config]
        self._session_makers: dict[str, Callable[..., Union[AsyncSession, Session]]] = {}  # noqa: UP007
        self._app: Starlette | None = None

        if app is not None:
            self.init_app(app)

    @property
    def config(self) -> Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig]:
        """Current Advanced Alchemy configuration."""

        return self._config

    def init_app(self, app: Starlette) -> None:
        """Initializes the Starlette application with SQLAlchemy engine and sessionmaker.

        Sets up middleware and shutdown handlers for managing the database engine.

        Args:
            app (starlette.applications.Starlette): The Starlette application instance.
        """
        unique_sessions_keys = {config.session_key for config in self.config}
        if len(unique_sessions_keys) != len(self.config):
            msg = "Please ensure that each config has a unique name for the `session_key` attribute.  The default is `db_session` and can only be bound to a single engine."
            raise ImproperConfigurationError(msg)

        for config in self.config:
            config.init_app(app)

        app.add_middleware(BaseHTTPMiddleware, dispatch=self.middleware_dispatch)
        app.add_event_handler("shutdown", self.on_shutdown)  # pyright: ignore[reportUnknownMemberType]

        self._app = app

    @property
    def app(self) -> Starlette:
        """Returns the Starlette application instance.

        Raises:
            advanced_alchemy.exceptions.ImproperConfigurationError:
                If the application is not initialized.

        Returns:
            starlette.applications.Starlette: The Starlette application instance.
        """
        if self._app is None:
            msg = "Application not initialized. Did you forget to call init_app?"
            raise ImproperConfigurationError(msg)

        return self._app

    async def middleware_dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Middleware dispatch function to handle requests and responses.

        Processes the request, invokes the next middleware or route handler, and
        applies the session handler after the response is generated.

        Args:
            request (starlette.requests.Request): The incoming HTTP request.
            call_next (starlette.middleware.base.RequestResponseEndpoint):
                The next middleware or route handler.

        Returns:
            starlette.responses.Response: The HTTP response.
        """
        response = await call_next(request)
        _ = await asyncio.gather(
            *(config.middleware_dispatch(request, call_next) for config in self.config), return_exceptions=True
        )

        return response

    async def on_shutdown(self) -> None:
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.

        Returns:
            None
        """
        _ = await asyncio.gather(*(config.on_shutdown() for config in self.config), return_exceptions=True)

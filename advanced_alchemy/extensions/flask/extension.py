"""Flask extension for Advanced Alchemy."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator, Sequence

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask.cli import database_group
from advanced_alchemy.extensions.flask.config import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.flask.typing import BlockingPortal, BlockingPortalProvider

if TYPE_CHECKING:
    from flask import Flask
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    from advanced_alchemy.extensions.flask.config import SQLAlchemySyncConfig


class AdvancedAlchemy:
    """Flask extension for Advanced Alchemy.

    This extension provides integration between Flask and Advanced Alchemy, including:
    - Async and sync session management
    - Database migration commands via Click
    - Automatic async/sync session handling
    - Support for multiple database bindings
    """

    __slots__ = ("_config", "_has_async_config", "_portal_provider", "_session_makers")

    def __init__(
        self,
        config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig | Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig],
        app: Flask | None = None,
    ) -> None:
        """Initialize the extension.

        Args:
            config: SQLAlchemy configuration(s) for the extension
            app: Optional Flask application instance
        """
        self._portal_provider = BlockingPortalProvider()
        self._config: Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig] = (
            [config] if not isinstance(config, Sequence) else config
        )
        self._has_async_config = any(isinstance(cfg, SQLAlchemyAsyncConfig) for cfg in self._config)
        if app is not None:
            self.init_app(app)

        self._session_makers = {cfg.bind_key or "default": cfg.create_session_maker() for cfg in self._config}

    @property
    def config(self) -> Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig]:
        """Get the SQLAlchemy configuration(s).

        Returns:
            The configured SQLAlchemy configuration(s)
        """
        return self._config

    @contextmanager
    def with_portal(self) -> Generator[BlockingPortal | None, None, None]:
        """Context manager for using the portal."""
        if self._has_async_config:
            with self._portal_provider as portal:
                yield portal
        else:
            yield None

    def init_app(self, app: Flask) -> None:
        """Initialize the Flask application.

        Args:
            app: The Flask app instance to initialize.

        Raises:
            ImproperConfigurationError: If this extension is already registered on the given Flask instance.
        """
        if "advanced_alchemy" in app.extensions:
            msg = "Advanced Alchemy extension is already registered on this Flask application."
            raise ImproperConfigurationError(msg)

        with self.with_portal() as portal:
            # Initialize each config with the app if it's a Flask config
            for config in self.config:
                config.init_app(app, portal)

        app.extensions["advanced_alchemy"] = self
        app.cli.add_command(database_group)

        self._register_teardown_handler(app)

    def get_session(self, bind_key: str = "default") -> Session | AsyncSession:
        """Get a new session from the configured session factory.

        Args:
            bind_key: Optional bind key to specify which database to use

        Returns:
            A new SQLAlchemy session
        """
        # If no bind key is specified and there is only one config, use its bind key
        if bind_key == "default" and len(self._config) == 1:
            bind_key = self._config[0].bind_key or "default"

        session_maker = self._session_makers.get(bind_key)
        if session_maker is None:
            msg = f'No session maker found for bind key "{bind_key}"'
            raise ValueError(msg)
        return session_maker()

    def _register_teardown_handler(self, app: Flask) -> None:
        """Register a teardown handler to close sessions after each request.

        Args:
            app: The Flask app instance to register the handler on.
        """

        @app.teardown_appcontext
        def close_sessions(error: Exception | None = None) -> None:
            """Close all sessions after each request.

            Args:
                error: Optional exception that occurred during the request.
            """
            for session_maker in self._session_makers.values():
                if hasattr(session_maker, "remove"):
                    session_maker.remove()

    @property
    def is_async_enabled(self) -> bool:
        """Return True if any of the database configs are async."""
        return self._has_async_config

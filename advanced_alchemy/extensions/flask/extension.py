from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from typing import TYPE_CHECKING, Any, Iterator, Sequence

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.cli import add_migration_commands
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask.cli import database_group
from advanced_alchemy.extensions.flask.typing import BlockingPortal, BlockingPortalProvider

if TYPE_CHECKING:
    from flask import Flask

    from advanced_alchemy.extensions.flask.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig


class AdvancedAlchemy:
    """Flask extension for Advanced Alchemy.

    This extension provides integration between Flask and Advanced Alchemy, including:
    - Async and sync session management
    - Database migration commands via Click
    - Automatic async/sync session handling
    - Support for multiple database bindings
    """

    __slots__ = ("_config", "_has_async_config", "_portal_provider")

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
        self._config: Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig] = (
            [config] if not isinstance(config, Sequence) else config
        )
        self._portal_provider: BlockingPortalProvider | None = None
        self._has_async_config = any(isinstance(cfg, SQLAlchemyAsyncConfig) for cfg in self._config)
        if app is not None:
            self.init_app(app)

    @contextmanager
    def with_portal(self) -> Iterator[BlockingPortal]:
        """Context manager fdatabase_groupprovider."""
        if self._portal_provider is None:
            msg = (
                "Please make sure that the `anyio` package is installed. "
                "Portal provider is not initialized. Call init_app() first."
            )
            raise ImproperConfigurationError(msg)
        with self._portal_provider as portal:
            yield portal

    @property
    def config(self) -> Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig]:
        """Get the SQLAlchemy configuration(s).

        Returns:
            The configured SQLAlchemy configuration(s)
        """
        return self._config

    def init_app(self, app: Flask) -> None:
        """Initialize the Flask application.

        Args:
            app: The Flask app instance to initialize.

        Raises:
            RuntimeError: If this extension is already registered on the given Flask instance.
        """
        if "advanced_alchemy" in app.extensions:
            msg = "Advanced Alchemy extension is already registered on this Flask application."
            raise ImproperConfigurationError(msg)

        app.extensions["alchemy"] = self
        add_migration_commands(app.cli)

        # Initialize each config with the app if it's a Flask config
        for config in self.config:
            if config.app is None:
                config.app = app

        app.extensions["advanced_alchemy"] = self
        app.cli.add_command(database_group)

    def get_session(self, bind_key: str | None = None) -> Any:
        """Get a new session from the configured session factory.

        Args:
            bind_key: Optional bind key to specify which database to use

        Returns:
            A new SQLAlchemy session
        """
        for config in self.config:
            if config.bind_key == bind_key:
                return config.get_session()
        return self.config[0].get_session()

    def get_engine(self, bind_key: str | None = None) -> Engine | AsyncEngine:
        """Get the SQLAlchemy engine.

        Args:
            bind_key: Optional bind key to specify which database to use

        Returns:
            The configured SQLAlchemy engine
        """
        for config in self.config:
            if config.bind_key == bind_key:
                return config.get_engine()
        return self.config[0].get_engine()

    @property
    def is_async_enabled(self) -> bool:
        """Return True if any of the database configs are async."""
        return self._has_async_config

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from advanced_alchemy.cli import add_migration_commands

if TYPE_CHECKING:
    from flask import Flask

    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig


class AdvancedAlchemy:
    """Flask extension for Advanced Alchemy."""

    __slots__ = ("_config",)

    def __init__(
        self,
        config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig | Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig],
        app: Flask | None = None,
    ) -> None:
        self._config: Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig] = (
            [config] if not isinstance(config, Sequence) else config
        )

        if app is not None:
            self.init_app(app)

    @property
    def config(self) -> Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig]:
        return self._config

    def init_app(self, app: Flask) -> None:
        """Initialize the extension with the Flask application.

        Args:
            app: The Flask application instance
        """
        if "alchemy" in app.extensions:
            msg = "AdvancedAlchemy is already initialized"
            raise RuntimeError(msg)

        app.extensions["alchemy"] = self
        add_migration_commands(app.cli)

        # Initialize each config with the app if it's a Flask config
        for config in self.config:
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

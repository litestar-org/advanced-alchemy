"""Alembic integration for Flask applications."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

from advanced_alchemy.alembic.commands import AlembicCommandConfig
from advanced_alchemy.alembic.commands import AlembicCommands as _AlembicCommands
from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from flask import Flask

    from advanced_alchemy.extensions.flask.extension import AdvancedAlchemy


def get_sqlalchemy_extension(app: Flask) -> AdvancedAlchemy:
    """Retrieve Advanced Alchemy extension from the Flask application.

    Args:
        app: The :class:`flask.Flask` application instance.

    Returns:
        :class:`AdvancedAlchemy`: The Advanced Alchemy extension instance.

    Raises:
        :exc:`advanced_alchemy.exceptions.ImproperConfigurationError`: If the extension is not found.
    """
    with suppress(KeyError):
        return cast("AdvancedAlchemy", app.extensions["advanced_alchemy"])
    msg = "Failed to initialize database migrations. The Advanced Alchemy extension is not properly configured."
    raise ImproperConfigurationError(msg)


class AlembicCommands(_AlembicCommands):
    """Flask-specific implementation of Alembic commands.

    Args:
        app: The :class:`flask.Flask` application instance.
    """

    def __init__(self, app: Flask) -> None:
        """Initialize the Alembic commands.

        Args:
            app: The Flask application instance.
        """
        self._app = app
        self.db = get_sqlalchemy_extension(self._app)
        self.config = self._get_alembic_command_config()

    def _get_alembic_command_config(self) -> AlembicCommandConfig:
        """Get the Alembic command configuration.

        Returns:
            :class:`AlembicCommandConfig`: The command configuration instance.
        """
        kwargs: dict[str, Any] = {}
        if self.sqlalchemy_config.alembic_config.script_config:
            kwargs["file_"] = self.sqlalchemy_config.alembic_config.script_config
        if self.sqlalchemy_config.alembic_config.template_path:
            kwargs["template_directory"] = self.sqlalchemy_config.alembic_config.template_path
        kwargs.update(
            {
                "engine": self.sqlalchemy_config.get_engine(),
                "version_table_name": self.sqlalchemy_config.alembic_config.version_table_name,
            },
        )
        self.config = AlembicCommandConfig(**kwargs)
        self.config.set_main_option("script_location", self.sqlalchemy_config.alembic_config.script_location)
        return self.config

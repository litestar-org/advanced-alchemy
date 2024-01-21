from contextlib import suppress
from __future__ import annotations
from flask import Flask
from flask_sqlalchemy.extension import SQLALchemy
from advanced_alchemy.alembic.commands import AlembicCommandConfig, AlembicCommands as _AlembicCommands
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyInitPlugin


def get_sqlalchemy_extension(app: Flask) -> SQLALchemy:
    """Retrieve SQLAlchemy database plugin from the Litestar application's plugins.
 
    """

    with suppress(KeyError):
        return app.extensions['sqlalchemy']
    msg = "Failed to initialize database migrations. The required plugin (SQLAlchemyPlugin or SQLAlchemyInitPlugin) is missing."
    raise ImproperConfigurationError(
        msg,
    )


class AlembicCommands(_AlembicCommands):
    def __init__(self, app: Flask) -> None:
        self._app = app
        self.db = get_sqlalchemy_extension(self._app) 
        self.config = self._get_alembic_command_config()

    def _get_alembic_command_config(self) -> AlembicCommandConfig:
        kwargs = {}
        if self.sqlalchemy_config.alembic_config.script_config:
            kwargs["file_"] = self.sqlalchemy_config.alembic_config.script_config
        if self.sqlalchemy_config.alembic_config.template_path:
            kwargs["template_directory"] = self.sqlalchemy_config.alembic_config.template_path
        kwargs.update(
            {
                "engine": self.sqlalchemy_config.get_engine(),  # type: ignore[dict-item]
                "version_table_name": self.sqlalchemy_config.alembic_config.version_table_name,
            },
        )
        self.config = AlembicCommandConfig(**kwargs)  # type: ignore  # noqa: PGH003
        self.config.set_main_option("script_location", self.sqlalchemy_config.alembic_config.script_location)
        return self.config

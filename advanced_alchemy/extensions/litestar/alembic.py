from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Sequence

from advanced_alchemy.alembic.commands import AlembicCommands as _AlembicCommands

if TYPE_CHECKING:
    from litestar import Litestar

    from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyInitPlugin


def get_database_migration_plugin(app: Litestar) -> SQLAlchemyInitPlugin:
    """Retrieve a database migration plugin from the Litestar application's plugins.

    This function attempts to find and return either the SQLAlchemyPlugin or SQLAlchemyInitPlugin.
    If neither plugin is found, it raises an ImproperlyConfiguredException.
    """
    from advanced_alchemy.exceptions import ImproperConfigurationError
    from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyInitPlugin

    with suppress(KeyError):
        return app.plugins.get(SQLAlchemyInitPlugin)
    msg = "Failed to initialize database migrations. The required plugin (SQLAlchemyPlugin or SQLAlchemyInitPlugin) is missing."
    raise ImproperConfigurationError(
        msg,
    )


class AlembicCommands(_AlembicCommands):
    def __init__(self, app: Litestar) -> None:
        self._app = app
        config = get_database_migration_plugin(self._app).config
        if isinstance(config, Sequence):
            self.sqlalchemy_config = config[0]
        else:
            self.sqlalchemy_config = config
        self.config = self._get_alembic_command_config()

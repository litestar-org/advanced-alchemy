from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from click import Context, group, pass_context
from litestar.cli._utils import LitestarGroup

from advanced_alchemy.cli.builder import add_migration_commands

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
    raise ImproperConfigurationError(msg)


@group(cls=LitestarGroup, name="database")
@pass_context
def database_group(ctx: Context) -> None:
    """Manage SQLAlchemy database components."""
    ctx.obj = get_database_migration_plugin(ctx.obj.app).config


add_migration_commands(database_group)

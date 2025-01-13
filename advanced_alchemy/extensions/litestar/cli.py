from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from advanced_alchemy.cli import add_migration_commands

try:
    import rich_click as click
except ImportError:
    import click  # type: ignore[no-redef]
from litestar.cli._utils import LitestarGroup

if TYPE_CHECKING:
    from litestar import Litestar

    from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyInitPlugin


def get_database_migration_plugin(app: Litestar) -> SQLAlchemyInitPlugin:
    """Retrieve a database migration plugin from the Litestar application's plugins."""
    from advanced_alchemy.exceptions import ImproperConfigurationError
    from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyInitPlugin

    with suppress(KeyError):
        return app.plugins.get(SQLAlchemyInitPlugin)
    msg = "Failed to initialize database migrations. The required plugin (SQLAlchemyPlugin or SQLAlchemyInitPlugin) is missing."
    raise ImproperConfigurationError(msg)


@click.group(cls=LitestarGroup, name="database")
@click.pass_context
def database_group(ctx: click.Context) -> None:
    """Manage SQLAlchemy database components."""
    ctx.ensure_object(dict)
    plugin = get_database_migration_plugin(ctx.obj["app"])
    if "configs" not in ctx.obj:
        ctx.obj["configs"] = plugin.config


add_migration_commands(database_group)

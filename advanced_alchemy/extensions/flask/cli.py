from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from click import Context, group, pass_context

from advanced_alchemy.cli.builder import add_migration_commands

if TYPE_CHECKING:
    from flask import Flask

    from advanced_alchemy.extensions.flask.extension import AdvancedAlchemy


def get_database_extension(app: Flask) -> AdvancedAlchemy:
    """Retrieve the Advanced Alchemy extension from the Flask application.

    Args:
        app: The Flask application instance

    Returns:
        The Advanced Alchemy extension instance

    Raises:
        ImproperConfigurationError: If the extension is not found in the application
    """
    from advanced_alchemy.exceptions import ImproperConfigurationError

    with suppress(KeyError):
        return app.extensions["advanced_alchemy"]
    msg = "Failed to initialize database migrations. The Advanced Alchemy extension is not properly configured."
    raise ImproperConfigurationError(msg)


@group(name="database")
@pass_context
def database_group(ctx: Context) -> None:
    """Manage SQLAlchemy database components."""
    ctx.ensure_object(dict)
    ctx.obj = get_database_extension(ctx.obj["app"]).config


add_migration_commands(database_group)

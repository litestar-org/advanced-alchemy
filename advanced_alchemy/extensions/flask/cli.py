"""Command-line interface utilities for Flask integration.

This module provides CLI commands for database management in Flask applications.
"""

from contextlib import suppress
from typing import TYPE_CHECKING, cast

from flask.cli import with_appcontext

from advanced_alchemy.cli import add_migration_commands
from advanced_alchemy.utils.cli_tools import click, group

if TYPE_CHECKING:
    from flask import Flask

    from advanced_alchemy.extensions.flask.extension import AdvancedAlchemy


def get_database_migration_plugin(app: "Flask") -> "AdvancedAlchemy":
    """Retrieve the Advanced Alchemy extension from the Flask application.

    Args:
        app: The :class:`flask.Flask` application instance.

    Returns:
        :class:`AdvancedAlchemy`: The Advanced Alchemy extension instance.

    Raises:
        :exc:`advanced_alchemy.exceptions.ImproperConfigurationError`: If the extension is not found.
    """
    from advanced_alchemy.exceptions import ImproperConfigurationError

    with suppress(KeyError):
        return cast("AdvancedAlchemy", app.extensions["advanced_alchemy"])
    msg = "Failed to initialize database migrations. The Advanced Alchemy extension is not properly configured."
    raise ImproperConfigurationError(msg)


@group(name="database", aliases=["db"])  # pyright: ignore
@with_appcontext
def database_group() -> None:
    """Manage SQLAlchemy database components.

    This command group provides database management commands like migrations.
    """
    ctx = cast("click.Context", click.get_current_context())
    app = ctx.obj.load_app()
    ctx.obj = {"app": app, "configs": get_database_migration_plugin(app).config}


add_migration_commands(database_group)  # pyright: ignore

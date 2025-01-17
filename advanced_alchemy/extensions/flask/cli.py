"""Command-line interface utilities for Flask integration.

This module provides CLI commands for database management in Flask applications.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, cast

from flask import current_app

from advanced_alchemy.cli import add_migration_commands

try:
    import rich_click as click
except ImportError:
    import click  # type: ignore[no-redef]


if TYPE_CHECKING:
    from flask import Flask

    from advanced_alchemy.extensions.flask.extension import AdvancedAlchemy


def get_database_migration_plugin(app: Flask) -> AdvancedAlchemy:
    """Retrieve the Advanced Alchemy extension from the Flask application.

    Args:
        app: The :class:`flask.Flask` application instance.

    Returns:
        :class:`AdvancedAlchemy`: The Advanced Alchemy extension instance.

    Raises:
        :exc:`advanced_alchemy.exceptions.ImproperConfigurationError`: If the extension is not found.

    Example:
        ```python
        from flask import Flask
        from advanced_alchemy.extensions.flask import (
            get_database_migration_plugin,
        )

        app = Flask(__name__)
        db = get_database_migration_plugin(app)
        ```
    """
    from advanced_alchemy.exceptions import ImproperConfigurationError

    with suppress(KeyError):
        return cast("AdvancedAlchemy", app.extensions["advanced_alchemy"])
    msg = "Failed to initialize database migrations. The Advanced Alchemy extension is not properly configured."
    raise ImproperConfigurationError(msg)


@click.group(name="database")
@click.pass_context
def database_group(ctx: click.Context) -> None:
    """Manage SQLAlchemy database components.

    This command group provides database management commands like migrations.
    """
    ctx.ensure_object(dict)
    ctx.obj["configs"] = get_database_migration_plugin(current_app).config


add_migration_commands(database_group)

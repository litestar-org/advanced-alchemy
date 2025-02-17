from typing import TYPE_CHECKING, Optional, cast

try:
    import rich_click as click
except ImportError:
    import click  # type: ignore[no-redef]

from advanced_alchemy.cli import add_migration_commands

if TYPE_CHECKING:
    from fastapi import FastAPI

    from advanced_alchemy.extensions.fastapi.extension import AdvancedAlchemy


def get_database_migration_plugin(app: "FastAPI") -> "AdvancedAlchemy":  # pragma: no cover
    """Retrieve the Advanced Alchemy extension from a FastAPI application instance."""
    from advanced_alchemy.exceptions import ImproperConfigurationError

    extension = cast("Optional[AdvancedAlchemy]", getattr(app.state, "advanced_alchemy", None))
    if extension is None:
        msg = "Failed to initialize database CLI. The Advanced Alchemy extension is not properly configured."
        raise ImproperConfigurationError(msg)
    return extension


def register_database_commands(app: "FastAPI") -> click.Group:  # pragma: no cover
    @click.group(name="database")
    @click.pass_context
    def database_group(ctx: click.Context) -> None:
        """Manage SQLAlchemy database components."""
        ctx.ensure_object(dict)
        ctx.obj["configs"] = get_database_migration_plugin(app).config

    add_migration_commands(database_group)
    return database_group

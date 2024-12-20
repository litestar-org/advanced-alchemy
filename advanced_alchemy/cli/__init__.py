from __future__ import annotations

from click import Context, group, option, pass_context

from advanced_alchemy.cli.builder import add_migration_commands
from advanced_alchemy.utils import module_loader


@group(name="alchemy")
@option(
    "--config",
    help="Dotted path to SQLAlchemy config(s) (e.g. 'myapp.config:sqlalchemy_config')",
    required=True,
    type=str,
)
@pass_context
def alchemy_group(ctx: Context, config: str) -> None:
    """Advanced Alchemy CLI commands."""
    from rich import get_console

    console = get_console()
    ctx.ensure_object(dict)
    try:
        config_instance = module_loader.import_string(config)
        if isinstance(config_instance, (list, tuple)):
            ctx.obj["configs"] = config_instance
        else:
            ctx.obj["configs"] = [config_instance]
    except ImportError as e:
        console.print(f"[red]Error loading config: {e}[/]")
        ctx.exit(1)


add_migration_commands(alchemy_group)

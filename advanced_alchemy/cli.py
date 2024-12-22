from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Sequence, cast

if TYPE_CHECKING:
    from click import Group

    from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
    from alembic.migration import MigrationContext
    from alembic.operations.ops import MigrationScript, UpgradeOps

__all__ = ("add_migration_commands", "get_alchemy_group")


def get_alchemy_group() -> Group:
    """Get the Advanced Alchemy CLI group."""
    from advanced_alchemy.exceptions import MissingDependencyError

    try:
        import rich_click as click
    except ImportError:
        try:
            import click  # type: ignore[no-redef]
        except ImportError as e:
            raise MissingDependencyError(package="click", install_package="cli") from e

    @click.group(name="alchemy")
    @click.option(
        "--config",
        help="Dotted path to SQLAlchemy config(s) (e.g. 'myapp.config.alchemy_configs')",
        required=True,
        type=str,
    )
    @click.pass_context
    def alchemy_group(ctx: click.Context, config: str) -> None:
        """Advanced Alchemy CLI commands."""
        from rich import get_console

        from advanced_alchemy.utils import module_loader

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

    return alchemy_group


def add_migration_commands(database_group: Group | None = None) -> Group:  # noqa: C901, PLR0915
    """Add migration commands to the database group."""
    from advanced_alchemy.exceptions import MissingDependencyError

    try:
        import rich_click as click
    except ImportError:
        try:
            import click  # type: ignore[no-redef]
        except ImportError as e:
            raise MissingDependencyError(package="click", install_package="cli") from e
    from rich import get_console

    console = get_console()

    if database_group is None:
        database_group = get_alchemy_group()

    @database_group.command(
        name="show-current-revision",
        help="Shows the current revision for the database.",
    )
    @click.option("--verbose", type=bool, help="Enable verbose output.", default=False, is_flag=True)
    @click.pass_context
    def show_database_revision(ctx: click.Context, verbose: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Show current database revision."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        console.rule("[yellow]Listing current revision[/]", align="left")
        sqlalchemy_config = ctx.obj["configs"][0]
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.current(verbose=verbose)

    @database_group.command(
        name="downgrade",
        help="Downgrade database to a specific revision.",
    )
    @click.option("--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True)
    @click.option(
        "--tag",
        help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
        type=str,
        default=None,
    )
    @click.option(
        "--no-prompt",
        help="Do not prompt for confirmation before downgrading.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    @click.argument(
        "revision",
        type=str,
        default="-1",
    )
    @click.pass_context
    def downgrade_database(ctx: click.Context, revision: str, sql: bool, tag: str | None, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Downgrade the database to the latest revision."""
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.commands import AlembicCommands

        console.rule("[yellow]Starting database downgrade process[/]", align="left")
        input_confirmed = (
            True
            if no_prompt
            else Confirm.ask(f"Are you sure you want to downgrade the database to the `{revision}` revision?")
        )
        if input_confirmed:
            sqlalchemy_config = ctx.obj["configs"][0]
            alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
            alembic_commands.downgrade(revision=revision, sql=sql, tag=tag)

    @database_group.command(
        name="upgrade",
        help="Upgrade database to a specific revision.",
    )
    @click.option("--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True)
    @click.option(
        "--tag",
        help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
        type=str,
        default=None,
    )
    @click.option(
        "--no-prompt",
        help="Do not prompt for confirmation before upgrading.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    @click.argument(
        "revision",
        type=str,
        default="head",
    )
    @click.pass_context
    def upgrade_database(ctx: click.Context, revision: str, sql: bool, tag: str | None, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Upgrade the database to the latest revision."""
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.commands import AlembicCommands

        console.rule("[yellow]Starting database upgrade process[/]", align="left")
        input_confirmed = (
            True
            if no_prompt
            else Confirm.ask(f"[bold]Are you sure you want migrate the database to the `{revision}` revision?[/]")
        )
        if input_confirmed:
            sqlalchemy_config = ctx.obj["configs"][0]
            alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
            alembic_commands.upgrade(revision=revision, sql=sql, tag=tag)

    @database_group.command(
        name="init",
        help="Initialize migrations for the project.",
    )
    @click.argument("directory", default=None)
    @click.option("--multidb", is_flag=True, default=False, help="Support multiple databases")
    @click.option("--package", is_flag=True, default=True, help="Create `__init__.py` for created folder")
    @click.option(
        "--no-prompt",
        help="Do not prompt for confirmation before initializing.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    @click.pass_context
    def init_alembic(ctx: click.Context, directory: str | None, multidb: bool, package: bool, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Initialize the database migrations."""
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.commands import AlembicCommands

        console.rule("[yellow]Initializing database migrations.", align="left")
        input_confirmed = (
            True
            if no_prompt
            else Confirm.ask(f"[bold]Are you sure you want initialize the project in `{directory}`?[/]")
        )
        if input_confirmed:
            for config in ctx.obj["configs"]:
                directory = config.alembic_config.script_location if directory is None else directory
                alembic_commands = AlembicCommands(sqlalchemy_config=config)
                alembic_commands.init(directory=cast("str", directory), multidb=multidb, package=package)

    @database_group.command(
        name="make-migrations",
        help="Create a new migration revision.",
    )
    @click.option("-m", "--message", default=None, help="Revision message")
    @click.option(
        "--autogenerate/--no-autogenerate", default=True, help="Automatically populate revision with detected changes"
    )
    @click.option("--sql", is_flag=True, default=False, help="Export to `.sql` instead of writing to the database.")
    @click.option("--head", default="head", help="Specify head revision to use as base for new revision.")
    @click.option(
        "--splice", is_flag=True, default=False, help='Allow a non-head revision as the "head" to splice onto'
    )
    @click.option("--branch-label", default=None, help="Specify a branch label to apply to the new revision")
    @click.option("--version-path", default=None, help="Specify specific path from config for version file")
    @click.option("--rev-id", default=None, help="Specify a ID to use for revision.")
    @click.option(
        "--no-prompt",
        help="Do not prompt for a migration message.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    @click.pass_context
    def create_revision(  # pyright: ignore[reportUnusedFunction]
        ctx: click.Context,
        message: str | None,
        autogenerate: bool,
        sql: bool,
        head: str,
        splice: bool,
        branch_label: str | None,
        version_path: str | None,
        rev_id: str | None,
        no_prompt: bool,
    ) -> None:
        """Create a new database revision."""
        from rich.prompt import Prompt

        from advanced_alchemy.alembic.commands import AlembicCommands

        def process_revision_directives(
            context: MigrationContext,  # noqa: ARG001
            revision: tuple[str],  # noqa: ARG001
            directives: list[MigrationScript],
        ) -> None:
            """Handle revision directives."""
            if autogenerate and cast("UpgradeOps", directives[0].upgrade_ops).is_empty():
                console.rule(
                    "[magenta]The generation of a migration file is being skipped because it would result in an empty file.",
                    style="magenta",
                    align="left",
                )
                console.rule(
                    "[magenta]More information can be found here. https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect",
                    style="magenta",
                    align="left",
                )
                console.rule(
                    "[magenta]If you intend to create an empty migration file, use the --no-autogenerate option.",
                    style="magenta",
                    align="left",
                )
                directives.clear()

        console.rule("[yellow]Starting database upgrade process[/]", align="left")
        if message is None:
            message = "autogenerated" if no_prompt else Prompt.ask("Please enter a message describing this revision")

        sqlalchemy_config = ctx.obj["configs"][0]
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.revision(
            message=message,
            autogenerate=autogenerate,
            sql=sql,
            head=head,
            splice=splice,
            branch_label=branch_label,
            version_path=version_path,
            rev_id=rev_id,
            process_revision_directives=process_revision_directives,  # type: ignore[arg-type]
        )

    @database_group.command(name="drop-all", help="Drop all tables from the database.")
    @click.option(
        "--no-prompt",
        help="Do not prompt for confirmation before upgrading.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    @click.pass_context
    def drop_all(ctx: click.Context, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Drop all tables from the database."""
        from anyio import run
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.utils import drop_all
        from advanced_alchemy.base import metadata_registry

        console.rule("[yellow]Dropping all tables from the database[/]", align="left")
        input_confirmed = no_prompt or Confirm.ask(
            "[bold red]Are you sure you want to drop all tables from the database?"
        )

        async def _drop_all(
            configs: Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
        ) -> None:
            for config in configs:
                engine = config.get_engine()
                await drop_all(engine, config.alembic_config.version_table_name, metadata_registry.get(config.bind_key))

        if input_confirmed:
            run(_drop_all, ctx.obj["configs"])

    @database_group.command(name="dump-data", help="Dump specified tables from the database to JSON files.")
    @click.option(
        "--table",
        "table_names",
        help="Name of the table to dump. Multiple tables can be specified. Use '*' to dump all tables.",
        type=str,
        required=True,
        multiple=True,
    )
    @click.option(
        "--dir",
        "dump_dir",
        help="Directory to save the JSON files. Defaults to WORKDIR/fixtures",
        type=click.Path(path_type=Path),
        default=Path.cwd() / "fixtures",
        required=False,
    )
    @click.pass_context
    def dump_table_data(ctx: click.Context, table_names: tuple[str, ...], dump_dir: Path) -> None:  # pyright: ignore[reportUnusedFunction]
        """Dump table data to JSON files."""
        from anyio import run
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.utils import dump_tables
        from advanced_alchemy.base import metadata_registry, orm_registry

        all_tables = "*" in table_names

        if all_tables and not Confirm.ask(
            "[yellow bold]You have specified '*'. Are you sure you want to dump all tables from the database?",
        ):
            return console.rule("[red bold]No data was dumped.", style="red", align="left")

        async def _dump_tables() -> None:
            for config in ctx.obj["configs"]:
                target_tables = set(metadata_registry.get(config.bind_key).tables)

                if not all_tables:
                    for table_name in set(table_names) - target_tables:
                        console.rule(
                            f"[red bold]Skipping table '{table_name}' because it is not available in the default registry",
                            style="red",
                            align="left",
                        )
                    target_tables.intersection_update(table_names)
                else:
                    console.rule("[yellow bold]Dumping all tables", style="yellow", align="left")

                models = [
                    mapper.class_ for mapper in orm_registry.mappers if mapper.class_.__table__.name in target_tables
                ]
                await dump_tables(dump_dir, config.get_session(), models)
                console.rule("[green bold]Data dump complete", align="left")

        return run(_dump_tables)

    return database_group

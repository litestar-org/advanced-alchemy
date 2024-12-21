from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Sequence, cast

from anyio import run
from click import Context, Group, argument, option
from click import Path as ClickPath
from rich import get_console

if TYPE_CHECKING:
    from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
    from alembic.migration import MigrationContext
    from alembic.operations.ops import MigrationScript, UpgradeOps


def add_migration_commands(database_group: Group | None = None) -> Group:  # noqa: C901, PLR0915
    """Add migration commands to the database group."""
    console = get_console()

    if database_group is None:
        database_group = Group(name="database")

    @database_group.command(
        name="show-current-revision",
        help="Shows the current revision for the database.",
    )
    @option("--verbose", type=bool, help="Enable verbose output.", default=False, is_flag=True)
    def show_database_revision(ctx: Context, verbose: bool) -> None:  # pyright: ignore[reportUnusedFunction]
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
    @option("--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True)
    @option(
        "--tag",
        help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
        type=str,
        default=None,
    )
    @option(
        "--no-prompt",
        help="Do not prompt for confirmation before downgrading.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    @argument(
        "revision",
        type=str,
        default="-1",
    )
    def downgrade_database(ctx: Context, revision: str, sql: bool, tag: str | None, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
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
    @option("--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True)
    @option(
        "--tag",
        help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
        type=str,
        default=None,
    )
    @option(
        "--no-prompt",
        help="Do not prompt for confirmation before upgrading.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    @argument(
        "revision",
        type=str,
        default="head",
    )
    def upgrade_database(ctx: Context, revision: str, sql: bool, tag: str | None, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
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
    @argument("directory", default=None)
    @option("--multidb", is_flag=True, default=False, help="Support multiple databases")
    @option("--package", is_flag=True, default=True, help="Create `__init__.py` for created folder")
    @option(
        "--no-prompt",
        help="Do not prompt for confirmation before initializing.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    def init_alembic(ctx: Context, directory: str | None, multidb: bool, package: bool, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
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
    @option("-m", "--message", default=None, help="Revision message")
    @option(
        "--autogenerate/--no-autogenerate", default=True, help="Automatically populate revision with detected changes"
    )
    @option("--sql", is_flag=True, default=False, help="Export to `.sql` instead of writing to the database.")
    @option("--head", default="head", help="Specify head revision to use as base for new revision.")
    @option("--splice", is_flag=True, default=False, help='Allow a non-head revision as the "head" to splice onto')
    @option("--branch-label", default=None, help="Specify a branch label to apply to the new revision")
    @option("--version-path", default=None, help="Specify specific path from config for version file")
    @option("--rev-id", default=None, help="Specify a ID to use for revision.")
    @option(
        "--no-prompt",
        help="Do not prompt for a migration message.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    def create_revision(  # pyright: ignore[reportUnusedFunction]
        ctx: Context,
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
    @option(
        "--no-prompt",
        help="Do not prompt for confirmation before upgrading.",
        type=bool,
        default=False,
        required=False,
        show_default=True,
        is_flag=True,
    )
    def drop_all(ctx: Context, no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Drop all tables from the database."""
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
    @option(
        "--table",
        "table_names",
        help="Name of the table to dump. Multiple tables can be specified. Use '*' to dump all tables.",
        type=str,
        required=True,
        multiple=True,
    )
    @option(
        "--dir",
        "dump_dir",
        help="Directory to save the JSON files. Defaults to WORKDIR/fixtures",
        type=ClickPath(path_type=Path),
        default=Path.cwd() / "fixtures",
        required=False,
    )
    def dump_table_data(ctx: Context, table_names: tuple[str, ...], dump_dir: Path) -> None:  # pyright: ignore[reportUnusedFunction]
        """Dump table data to JSON files."""
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

import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union, cast

if TYPE_CHECKING:
    from alembic.migration import MigrationContext
    from alembic.operations.ops import MigrationScript, UpgradeOps
    from click import Group

    from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

__all__ = ("add_migration_commands", "get_alchemy_group")

from rich import get_console

from advanced_alchemy.utils.cli_tools import click

_console = get_console()

bind_key_option = click.option(
    "--bind-key",
    help="Specify which SQLAlchemy config to use by bind key",
    type=str,
    default=None,
)
verbose_option = click.option(
    "--verbose",
    help="Enable verbose output.",
    type=bool,
    default=False,
    is_flag=True,
)
no_prompt_option = click.option(
    "--no-prompt",
    help="Do not prompt for confirmation before executing the command.",
    type=bool,
    default=False,
    required=False,
    show_default=True,
    is_flag=True,
)


def _get_config_by_bind_key(
    ctx: "click.Context",
    bind_key: Optional[str],
) -> "Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]":
    """Get the SQLAlchemy config for the specified bind key."""
    configs = ctx.obj["configs"]
    if bind_key is None:
        return cast("Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]", configs[0])

    for config in configs:
        if config.bind_key == bind_key:
            return cast("Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]", config)

    _console.print(f"[red]No config found for bind key: {bind_key}[/]")
    sys.exit(1)


def _register_command(
    group: "Group",
    name: Optional[str],
    help_text: str,
    handler: Callable[..., Any],
    *options: Callable[..., Any],
) -> None:
    """Register a Click command with its decorators."""
    cmd = group.command(name=name, help=help_text)(handler)
    for opt in options:
        cmd = opt(cmd)


# ── Command Handlers ────────────────────────────────────────────────


def _show_database_revision(bind_key: Optional[str], verbose: bool) -> None:
    """Show current database revision."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Listing current revision[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.current(verbose=verbose)


def _downgrade_database(
    bind_key: Optional[str],
    revision: str,
    sql: bool,
    tag: Optional[str],
    no_prompt: bool,
) -> None:
    """Downgrade the database to the latest revision."""
    from rich.prompt import Confirm

    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Starting database downgrade process[/]", align="left")
    input_confirmed = (
        True
        if no_prompt
        else Confirm.ask(f"Are you sure you want to downgrade the database to the `{revision}` revision?")
    )
    if input_confirmed:
        sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.downgrade(revision=revision, sql=sql, tag=tag)


def _upgrade_database(
    bind_key: Optional[str],
    revision: str,
    sql: bool,
    tag: Optional[str],
    no_prompt: bool,
) -> None:
    """Upgrade the database to the latest revision."""
    from rich.prompt import Confirm

    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Starting database upgrade process[/]", align="left")
    input_confirmed = (
        True
        if no_prompt
        else Confirm.ask(f"[bold]Are you sure you want migrate the database to the `{revision}` revision?[/]")
    )
    if input_confirmed:
        sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.upgrade(revision=revision, sql=sql, tag=tag)


def _stamp_database(
    bind_key: Optional[str],
    revision: str,
    sql: bool,
    tag: Optional[str],
    purge: bool,
) -> None:
    """Stamp the revision table with the given revision."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Stamping revision table[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.stamp(revision=revision, sql=sql, tag=tag, purge=purge)


def _check_revision(bind_key: Optional[str]) -> None:
    """Check for pending upgrade operations."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Checking for pending migrations[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.check()


def _edit_revision(bind_key: Optional[str], revision: str) -> None:
    """Edit revision script with system editor."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule(f"[yellow]Opening revision {revision} in editor[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.edit(revision=revision)


def _ensure_version_table(bind_key: Optional[str], sql: bool) -> None:
    """Ensure alembic version table exists."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Ensuring version table exists[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.ensure_version(sql=sql)


def _show_heads(
    bind_key: Optional[str],
    verbose: bool,
    resolve_dependencies: bool,
) -> None:
    """Show current heads."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Showing current heads[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.heads(verbose=verbose, resolve_dependencies=resolve_dependencies)


def _show_history(
    bind_key: Optional[str],
    verbose: bool,
    rev_range: Optional[str],
    indicate_current: bool,
) -> None:
    """Show revision history."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Showing revision history[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.history(
        rev_range=rev_range,
        verbose=verbose,
        indicate_current=indicate_current,
    )


def _merge_revisions(
    bind_key: Optional[str],
    revisions: str,
    message: Optional[str],
    branch_label: Optional[str],
    rev_id: Optional[str],
    no_prompt: bool,
) -> None:
    """Merge revisions (resolves multiple heads)."""
    from rich.prompt import Prompt

    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Merging revisions[/]", align="left")

    if message is None:
        message = "merge revisions" if no_prompt else Prompt.ask("Enter merge message")

    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.merge(
        revisions=revisions,
        message=message,
        branch_label=branch_label,
        rev_id=rev_id,
    )


def _show_revision(bind_key: Optional[str], revision: str) -> None:
    """Show details of a specific revision."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule(f"[yellow]Showing revision {revision}[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.show(rev=revision)


def _show_branches(bind_key: Optional[str], verbose: bool) -> None:
    """Show branch points."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Showing branch points[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.branches(verbose=verbose)


def _list_init_templates(bind_key: Optional[str]) -> None:
    """List available initialization templates."""
    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Available templates[/]", align="left")
    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
    alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
    alembic_commands.list_templates()


def _init_alembic(
    bind_key: Optional[str],
    directory: Optional[str],
    multidb: bool,
    package: bool,
    no_prompt: bool,
) -> None:
    """Initialize the database migrations."""
    from rich.prompt import Confirm

    from advanced_alchemy.alembic.commands import AlembicCommands

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Initializing database migrations.", align="left")
    input_confirmed = (
        True if no_prompt else Confirm.ask("[bold]Are you sure you want initialize migrations for the project?[/]")
    )
    if input_confirmed:
        configs = [_get_config_by_bind_key(ctx, bind_key)] if bind_key is not None else ctx.obj["configs"]
        for config in configs:
            directory = config.alembic_config.script_location if directory is None else directory
            alembic_commands = AlembicCommands(sqlalchemy_config=config)
            alembic_commands.init(directory=cast("str", directory), multidb=multidb, package=package)


def _create_revision(
    bind_key: Optional[str],
    message: Optional[str],
    autogenerate: bool,
    sql: bool,
    head: str,
    splice: bool,
    branch_label: Optional[str],
    version_path: Optional[str],
    rev_id: Optional[str],
    no_prompt: bool,
) -> None:
    """Create a new database revision."""
    from rich.prompt import Prompt

    from advanced_alchemy.alembic.commands import AlembicCommands

    def process_revision_directives(
        context: "MigrationContext",  # noqa: ARG001
        revision: tuple[str],  # noqa: ARG001
        directives: list["MigrationScript"],
    ) -> None:
        """Handle revision directives."""
        if autogenerate and cast("UpgradeOps", directives[0].upgrade_ops).is_empty():
            _console.rule(
                "[magenta]The generation of a migration file is being skipped because it would result in an empty file.",
                style="magenta",
                align="left",
            )
            _console.rule(
                "[magenta]More information can be found here. https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect",
                style="magenta",
                align="left",
            )
            _console.rule(
                "[magenta]If you intend to create an empty migration file, use the --no-autogenerate option.",
                style="magenta",
                align="left",
            )
            directives.clear()

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Starting database upgrade process[/]", align="left")
    if message is None:
        message = "autogenerated" if no_prompt else Prompt.ask("Please enter a message describing this revision")

    sqlalchemy_config = _get_config_by_bind_key(ctx, bind_key)
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


def _drop_all_tables(bind_key: Optional[str], no_prompt: bool) -> None:
    """Drop all tables from the database."""
    from anyio import run
    from rich.prompt import Confirm

    from advanced_alchemy.alembic.utils import drop_all
    from advanced_alchemy.base import metadata_registry

    ctx = cast("click.Context", click.get_current_context())
    _console.rule("[yellow]Dropping all tables from the database[/]", align="left")
    input_confirmed = no_prompt or Confirm.ask(
        "[bold red]Are you sure you want to drop all tables from the database?",
    )

    async def _drop_all(
        configs: "Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]",
    ) -> None:
        for config in configs:
            engine = config.get_engine()
            await drop_all(engine, config.alembic_config.version_table_name, metadata_registry.get(config.bind_key))

    if input_confirmed:
        configs = [_get_config_by_bind_key(ctx, bind_key)] if bind_key is not None else ctx.obj["configs"]
        run(_drop_all, configs)


def _dump_table_data(bind_key: Optional[str], table_names: tuple[str, ...], dump_dir: Path) -> None:
    """Dump table data to JSON files."""
    from anyio import run
    from rich.prompt import Confirm

    from advanced_alchemy.alembic.utils import dump_tables
    from advanced_alchemy.base import metadata_registry, orm_registry

    ctx = cast("click.Context", click.get_current_context())
    all_tables = "*" in table_names

    if all_tables and not Confirm.ask(
        "[yellow bold]You have specified '*'. Are you sure you want to dump all tables from the database?",
    ):
        _console.rule("[red bold]No data was dumped.", style="red", align="left")
        return None

    async def _dump_tables() -> None:
        configs = [_get_config_by_bind_key(ctx, bind_key)] if bind_key is not None else ctx.obj["configs"]
        for config in configs:
            target_tables = set(metadata_registry.get(config.bind_key).tables)

            if not all_tables:
                for table_name in set(table_names) - target_tables:
                    _console.rule(
                        f"[red bold]Skipping table '{table_name}' because it is not available in the default registry",
                        style="red",
                        align="left",
                    )
                target_tables.intersection_update(table_names)
            else:
                _console.rule("[yellow bold]Dumping all tables", style="yellow", align="left")

            models = [mapper.class_ for mapper in orm_registry.mappers if mapper.class_.__table__.name in target_tables]
            await dump_tables(dump_dir, config.get_session(), models)
            _console.rule("[green bold]Data dump complete", align="left")

    return run(_dump_tables)


# ── Public API ──────────────────────────────────────────────────────


def get_alchemy_group() -> "Group":
    """Get the Advanced Alchemy CLI group.

    Raises:
        MissingDependencyError: If the `click` package is not installed.

    Returns:
        The Advanced Alchemy CLI group.
    """
    from advanced_alchemy.exceptions import MissingDependencyError
    from advanced_alchemy.utils.cli_tools import click, group

    if click is None:  # pragma: no cover - defensive guard
        raise MissingDependencyError(package="click", install_package="cli")

    @group(name="alchemy")  # pyright: ignore
    @click.option(
        "--config",
        help="Dotted path to SQLAlchemy config(s) (e.g. 'myapp.config.alchemy_configs')",
        required=True,
        type=str,
    )
    @click.pass_context
    def alchemy_group(ctx: "click.Context", config: str) -> None:
        """Advanced Alchemy CLI commands."""
        from pathlib import Path

        from rich import get_console

        from advanced_alchemy.utils import module_loader

        console = get_console()
        ctx.ensure_object(dict)

        # Add current working directory to sys.path to allow loading local config modules
        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        try:
            config_instance = module_loader.import_string(config)
            if isinstance(config_instance, Sequence):
                ctx.obj["configs"] = config_instance
            else:
                ctx.obj["configs"] = [config_instance]
        except ImportError as e:
            console.print(f"[red]Error loading config: {e}[/]")
            ctx.exit(1)
        finally:
            # Clean up: remove the cwd from sys.path if we added it
            if cwd in sys.path and sys.path[0] == cwd:
                sys.path.remove(cwd)

    return alchemy_group


def add_migration_commands(database_group: Optional["Group"] = None) -> "Group":
    """Add migration commands to the database group.

    Args:
        database_group: The database group to add the commands to.

    Returns:
        The database group with the migration commands added.
    """
    if database_group is None:
        database_group = get_alchemy_group()

    _register_command(
        database_group,
        "show-current-revision",
        "Shows the current revision for the database.",
        _show_database_revision,
        bind_key_option,
        verbose_option,
    )

    _register_command(
        database_group,
        "downgrade",
        "Downgrade database to a specific revision.",
        _downgrade_database,
        click.argument("revision", type=str, default="-1"),
        bind_key_option,
        click.option(
            "--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True
        ),
        click.option(
            "--tag",
            help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
            type=str,
            default=None,
        ),
        no_prompt_option,
    )

    _register_command(
        database_group,
        "upgrade",
        "Upgrade database to a specific revision.",
        _upgrade_database,
        click.argument("revision", type=str, default="head"),
        bind_key_option,
        click.option(
            "--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True
        ),
        click.option(
            "--tag",
            help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
            type=str,
            default=None,
        ),
        no_prompt_option,
    )

    _register_command(
        database_group,
        "stamp",
        "Stamp the revision table with the given revision; don't run any migrations",
        _stamp_database,
        click.argument("revision", type=str),
        bind_key_option,
        click.option("--sql", is_flag=True, default=False, help="Generate SQL output for offline migrations"),
        click.option(
            "--tag",
            type=str,
            default=None,
            help="Arbitrary 'tag' that can be intercepted by custom env.py scripts",
        ),
        click.option(
            "--purge", is_flag=True, default=False, help="Delete all entries in version table before stamping"
        ),
    )

    _register_command(
        database_group,
        "check",
        "Check if the target database is up to date",
        _check_revision,
        bind_key_option,
    )

    _register_command(
        database_group,
        "edit",
        "Edit a revision file using $EDITOR",
        _edit_revision,
        click.argument("revision", type=str),
        bind_key_option,
    )

    _register_command(
        database_group,
        "ensure-version",
        "Create the alembic version table if it doesn't exist",
        _ensure_version_table,
        bind_key_option,
        click.option("--sql", is_flag=True, default=False, help="Generate SQL output instead of executing"),
    )

    _register_command(
        database_group,
        "heads",
        "Show current available heads in the script directory",
        _show_heads,
        bind_key_option,
        verbose_option,
        click.option("--resolve-dependencies", is_flag=True, default=False, help="Resolve dependencies between heads"),
    )

    _register_command(
        database_group,
        "history",
        "List changeset scripts in chronological order",
        _show_history,
        bind_key_option,
        verbose_option,
        click.option(
            "--rev-range",
            type=str,
            default=None,
            help="Revision range (e.g., 'base:head', 'abc:def')",
        ),
        click.option("--indicate-current", is_flag=True, default=False, help="Indicate the current revision"),
    )

    _register_command(
        database_group,
        "merge",
        "Merge two revisions together, creating a new migration file",
        _merge_revisions,
        click.argument("revisions", type=str),
        bind_key_option,
        click.option("-m", "--message", type=str, default=None, help="Merge message"),
        click.option("--branch-label", type=str, default=None, help="Branch label for merge revision"),
        click.option("--rev-id", type=str, default=None, help="Specify custom revision ID"),
        no_prompt_option,
    )

    _register_command(
        database_group,
        "show",
        "Show the revision denoted by the given symbol",
        _show_revision,
        click.argument("revision", type=str),
        bind_key_option,
    )

    _register_command(
        database_group,
        "branches",
        "Show current branch points in the migration history",
        _show_branches,
        bind_key_option,
        verbose_option,
    )

    _register_command(
        database_group,
        "list-templates",
        "List available Alembic migration templates",
        _list_init_templates,
        bind_key_option,
    )

    _register_command(
        database_group,
        "init",
        "Initialize migrations for the project.",
        _init_alembic,
        click.argument("directory", default=None, required=False),
        bind_key_option,
        click.option("--multidb", is_flag=True, default=False, help="Support multiple databases"),
        click.option("--package", is_flag=True, default=True, help="Create `__init__.py` for created folder"),
        no_prompt_option,
    )

    _register_command(
        database_group,
        "make-migrations",
        "Create a new migration revision.",
        _create_revision,
        bind_key_option,
        click.option("-m", "--message", default=None, help="Revision message"),
        click.option(
            "--autogenerate/--no-autogenerate",
            default=True,
            help="Automatically populate revision with detected changes",
        ),
        click.option("--sql", is_flag=True, default=False, help="Export to `.sql` instead of writing to the database."),
        click.option("--head", default="head", help="Specify head revision to use as base for new revision."),
        click.option(
            "--splice",
            is_flag=True,
            default=False,
            help='Allow a non-head revision as the "head" to splice onto',
        ),
        click.option("--branch-label", default=None, help="Specify a branch label to apply to the new revision"),
        click.option("--version-path", default=None, help="Specify specific path from config for version file"),
        click.option("--rev-id", default=None, help="Specify a ID to use for revision."),
        no_prompt_option,
    )

    _register_command(
        database_group,
        "drop-all",
        "Drop all tables from the database.",
        _drop_all_tables,
        bind_key_option,
        no_prompt_option,
    )

    _register_command(
        database_group,
        "dump-data",
        "Dump specified tables from the database to JSON files.",
        _dump_table_data,
        bind_key_option,
        click.option(
            "--table",
            "table_names",
            help="Name of the table to dump. Multiple tables can be specified. Use '*' to dump all tables.",
            type=str,
            required=True,
            multiple=True,
        ),
        click.option(
            "--dir",
            "dump_dir",
            help="Directory to save the JSON files. Defaults to WORKDIR/fixtures",
            type=click.Path(path_type=Path),
            default=Path.cwd() / "fixtures",
            required=False,
        ),
    )

    return database_group

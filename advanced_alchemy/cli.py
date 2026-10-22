"""Command-line interface utilities and migration commands for Advanced Alchemy."""

import asyncio
import inspect
import sys
from collections.abc import Callable, Coroutine, Sequence
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Optional, Union, cast

if TYPE_CHECKING:
    from alembic.migration import MigrationContext
    from alembic.operations.ops import MigrationScript, UpgradeOps
    from click import Group

    from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

__all__ = (
    "add_migration_commands",
    "discover_config_from_pyproject",
    "find_pyproject_toml",
    "get_alchemy_group",
    "parse_pyproject_config",
    "resolve_config_async",
    "resolve_config_sync",
)

_PYPROJECT_TOOL_SECTIONS = ("advanced-alchemy", "advanced_alchemy", "alchemy")


def discover_config_from_pyproject() -> Optional[str]:
    """Find and parse ``pyproject.toml`` for Advanced Alchemy CLI configuration.

    Walks upward from the current working directory to locate ``pyproject.toml``
    and parses ``[tool.advanced-alchemy]`` (or ``[tool.advanced_alchemy]`` /
    ``[tool.alchemy]``) for the ``config`` key.

    Returns:
        Configured path string (comma-separated when configured as a list), or
        ``None`` when not found.
    """
    pyproject_path = find_pyproject_toml()
    if pyproject_path is None:
        return None
    return parse_pyproject_config(pyproject_path)


def find_pyproject_toml() -> Optional[Path]:
    """Walk the filesystem upward from ``Path.cwd()`` to find ``pyproject.toml``.

    Stops at a ``.git`` directory boundary (repository root) or the filesystem root.

    Returns:
        Path to ``pyproject.toml``, or ``None`` if not found.
    """
    current = Path.cwd()
    while True:
        pyproject = current / "pyproject.toml"
        if pyproject.exists():
            return pyproject
        if (current / ".git").exists():
            return None
        if current == current.parent:
            return None
        current = current.parent


def parse_pyproject_config(pyproject_path: Path) -> Optional[str]:
    """Parse ``pyproject.toml`` for Advanced Alchemy CLI configuration.

    Checks ``[tool.advanced-alchemy]``, ``[tool.advanced_alchemy]``, and
    ``[tool.alchemy]`` in order for a ``config`` entry.

    Args:
        pyproject_path: Path to the ``pyproject.toml`` file.

    Returns:
        Config path(s) as a string (converting a list of strings to a
        comma-separated string), or ``None`` if no config is defined.

    Raises:
        ValueError: If the ``pyproject.toml`` file cannot be parsed or the
            ``config`` value is not a string or list of strings.
    """
    try:
        data = _load_toml(pyproject_path)
    except Exception as e:
        msg = f"Failed to parse {pyproject_path}: {e}"
        raise ValueError(msg) from e

    raw_tool_section = data.get("tool", {})
    if not isinstance(raw_tool_section, dict):
        return None
    tool_section = cast("dict[str, Any]", raw_tool_section)

    for section_name in _PYPROJECT_TOOL_SECTIONS:
        raw_alchemy_section = tool_section.get(section_name)
        if not isinstance(raw_alchemy_section, dict) or "config" not in raw_alchemy_section:
            continue
        alchemy_section = cast("dict[str, Any]", raw_alchemy_section)

        config: Any = alchemy_section.get("config")
        if config is None:
            return None

        if isinstance(config, str):
            return config

        if isinstance(config, list):
            config_items = cast("Sequence[Any]", config)
            if not all(isinstance(item, str) for item in config_items):
                msg = f"Invalid [tool.{section_name}].config in {pyproject_path}: list items must be strings"
                raise ValueError(msg)
            return ",".join(cast("Sequence[str]", config_items))

        config_type_name = type(cast("object", config)).__name__
        msg = (
            f"Invalid [tool.{section_name}].config in {pyproject_path}: "
            f"must be string or list of strings, got {config_type_name}"
        )
        raise ValueError(msg)

    return None


async def resolve_config_async(
    config_path: str,
) -> "Union[list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]], SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]":
    """Resolve configuration asynchronously from a dotted or colon-separated path.

    Supports direct config instances, sequences of configs, wrapper objects exposing
    ``.config`` (such as ``SQLAlchemyInitPlugin`` or ``AdvancedAlchemy``), synchronous
    factory callables, and asynchronous coroutine factories.

    Args:
        config_path: ``module.attribute`` or ``module:attribute`` path to a config
            object or factory callable.

    Returns:
        A resolved config instance or list of config instances.

    Raises:
        ImproperConfigurationError: If importing, executing, or validating the
            configuration fails.
    """
    from advanced_alchemy.exceptions import ImproperConfigurationError

    try:
        config_obj = _import_config_target(config_path)
    except ImportError as e:
        msg = f"Failed to import config from path '{config_path}': {e}"
        raise ImproperConfigurationError(msg) from e

    if not callable(config_obj) or isinstance(config_obj, type):
        return _validate_config_result(config_obj, config_path)

    try:
        if inspect.iscoroutinefunction(config_obj):
            result = await config_obj()
        else:
            result = await asyncio.to_thread(config_obj)
            if inspect.isawaitable(result):
                result = await result
    except Exception as e:
        msg = f"Failed to execute callable config '{config_path}': {e}"
        raise ImproperConfigurationError(msg) from e

    return _validate_config_result(result, config_path)


def resolve_config_sync(
    config_path: str,
) -> "Union[list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]], SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]":
    """Resolve configuration synchronously from a dotted or colon-separated path.

    Supports direct config instances, sequences of configs, wrapper objects exposing
    ``.config`` (such as ``SQLAlchemyInitPlugin`` or ``AdvancedAlchemy``), synchronous
    factory callables, and asynchronous coroutine factories.

    Args:
        config_path: ``module.attribute`` or ``module:attribute`` path to a config
            object or factory callable.

    Returns:
        A resolved config instance or list of config instances.

    Raises:
        ImproperConfigurationError: If importing, executing, or validating the
            configuration fails.
    """
    from advanced_alchemy.exceptions import ImproperConfigurationError

    try:
        config_obj = _import_config_target(config_path)
    except ImportError as e:
        msg = f"Failed to import config from path '{config_path}': {e}"
        raise ImproperConfigurationError(msg) from e

    if not callable(config_obj) or isinstance(config_obj, type):
        return _validate_config_result(config_obj, config_path)

    try:
        if inspect.iscoroutinefunction(config_obj):
            result = _run_coroutine_sync(config_obj())
        else:
            result = config_obj()
            if inspect.isawaitable(result):
                result = _run_coroutine_sync(cast("Coroutine[Any, Any, Any]", result))
    except Exception as e:
        msg = f"Failed to execute callable config '{config_path}': {e}"
        raise ImproperConfigurationError(msg) from e

    return _validate_config_result(result, config_path)


def get_alchemy_group() -> "Group":
    """Get the Advanced Alchemy CLI group.

    Raises:
        MissingDependencyError: If the ``click`` package is not installed.

    Returns:
        The Advanced Alchemy CLI group.
    """
    from advanced_alchemy.exceptions import MissingDependencyError
    from advanced_alchemy.utils.cli_tools import click, group

    if click is None:  # pragma: no cover
        raise MissingDependencyError(package="click", install_package="cli")

    config_option = _config_option(click)
    validate_config_option = _validate_config_option(click)

    @group(name="alchemy")  # pyright: ignore
    @config_option
    @validate_config_option
    @click.pass_context
    def alchemy_group(ctx: "click.Context") -> None:
        """Advanced Alchemy CLI commands."""
        ctx.ensure_object(dict)

    return alchemy_group


def add_migration_commands(database_group: Optional["Group"] = None) -> "Group":  # noqa: C901, PLR0915
    """Add migration commands to the database group.

    Args:
        database_group: The database group to add the commands to.

    Returns:
        The database group with the migration commands added.
    """
    from advanced_alchemy.utils.cli_tools import click

    console = _ConsoleProxy()

    if database_group is None:
        database_group = get_alchemy_group()

    config_option = _config_option(click)
    validate_config_option = _validate_config_option(click)
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

    def get_config_by_bind_key(
        ctx: "click.Context", bind_key: Optional[str]
    ) -> "Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]":
        """Get the SQLAlchemy config for the specified bind key.

        Args:
            ctx: The click context.
            bind_key: The bind key to get the config for.

        Returns:
            The SQLAlchemy config for the specified bind key.
        """
        configs = _resolve_alchemy_configs(ctx)
        if bind_key is None:
            return configs[0]

        for config in configs:
            if config.bind_key == bind_key:
                return config

        console.print(f"[red]No config found for bind key: {bind_key}[/]")
        sys.exit(1)

    @database_group.command(
        name="show-config",
        help="Show all configurations with migrations enabled.",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    def show_config(bind_key: Optional[str] = None) -> None:  # pyright: ignore[reportUnusedFunction]
        """Show and display all loaded configurations."""
        from rich.table import Table

        ctx = cast("click.Context", click.get_current_context())
        configs = [get_config_by_bind_key(ctx, bind_key)] if bind_key is not None else _resolve_alchemy_configs(ctx)

        if not configs:  # pragma: no cover
            console.print("[yellow]No configurations with migrations detected.[/]")
            return

        table = Table(title="Migration Configurations")
        table.add_column("Configuration Name", style="cyan")
        table.add_column("Migration Path", style="blue")
        table.add_column("Status", style="green")

        for cfg in configs:
            config_name = cfg.bind_key or "default"
            script_location = getattr(cfg.alembic_config, "script_location", "migrations")
            table.add_row(str(config_name), str(script_location), "Migration Enabled")

        console.print(table)
        console.print(f"[blue]Found {len(configs)} configuration(s) with migrations enabled.[/]")

    @database_group.command(
        name="show-current-revision",
        help="Shows the current revision for the database.",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @verbose_option
    def show_database_revision(bind_key: Optional[str], verbose: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Show current database revision."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Listing current revision[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.current(verbose=verbose)

    @database_group.command(
        name="downgrade",
        help="Downgrade database to a specific revision.",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @click.option("--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True)
    @click.option(
        "--tag",
        help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
        type=str,
        default=None,
    )
    @no_prompt_option
    @click.argument(
        "revision",
        type=str,
        default="-1",
    )
    def downgrade_database(  # pyright: ignore[reportUnusedFunction]
        bind_key: Optional[str], revision: str, sql: bool, tag: Optional[str], no_prompt: bool
    ) -> None:
        """Downgrade the database to the latest revision."""
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Starting database downgrade process[/]", align="left")
        input_confirmed = (
            True
            if no_prompt
            else Confirm.ask(f"Are you sure you want to downgrade the database to the `{revision}` revision?")
        )
        if input_confirmed:
            alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
            alembic_commands.downgrade(revision=revision, sql=sql, tag=tag)

    @database_group.command(
        name="upgrade",
        help="Upgrade database to a specific revision.",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @click.option("--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True)
    @click.option(
        "--tag",
        help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
        type=str,
        default=None,
    )
    @no_prompt_option
    @click.argument(
        "revision",
        type=str,
        default="head",
    )
    def upgrade_database(  # pyright: ignore[reportUnusedFunction]
        bind_key: Optional[str], revision: str, sql: bool, tag: Optional[str], no_prompt: bool
    ) -> None:
        """Upgrade the database to the latest revision."""
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Starting database upgrade process[/]", align="left")
        input_confirmed = (
            True
            if no_prompt
            else Confirm.ask(f"[bold]Are you sure you want migrate the database to the `{revision}` revision?[/]")
        )
        if input_confirmed:
            alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
            alembic_commands.upgrade(revision=revision, sql=sql, tag=tag)

    @database_group.command(
        help="Stamp the revision table with the given revision; don't run any migrations",
    )
    @config_option
    @validate_config_option
    @click.argument("revision", type=str)
    @bind_key_option
    @click.option("--sql", is_flag=True, default=False, help="Generate SQL output for offline migrations")
    @click.option(
        "--tag", type=str, default=None, help="Arbitrary 'tag' that can be intercepted by custom env.py scripts"
    )
    @click.option("--purge", is_flag=True, default=False, help="Delete all entries in version table before stamping")
    def stamp(bind_key: Optional[str], revision: str, sql: bool, tag: Optional[str], purge: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Stamp the revision table with the given revision."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Stamping revision table[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.stamp(revision=revision, sql=sql, tag=tag, purge=purge)

    @database_group.command(
        name="check",
        help="Check if the target database is up to date",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    def check_revision(bind_key: Optional[str]) -> None:  # pyright: ignore[reportUnusedFunction]
        """Check for pending upgrade operations."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Checking for pending migrations[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.check()

    @database_group.command(
        name="edit",
        help="Edit a revision file using $EDITOR",
    )
    @config_option
    @validate_config_option
    @click.argument("revision", type=str)
    @bind_key_option
    def edit_revision(bind_key: Optional[str], revision: str) -> None:  # pyright: ignore[reportUnusedFunction]
        """Edit revision script with system editor."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule(f"[yellow]Opening revision {revision} in editor[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.edit(revision=revision)

    @database_group.command(
        name="ensure-version",
        help="Create the alembic version table if it doesn't exist",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @click.option("--sql", is_flag=True, default=False, help="Generate SQL output instead of executing")
    def ensure_version_table(bind_key: Optional[str], sql: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Ensure alembic version table exists."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Ensuring version table exists[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.ensure_version(sql=sql)

    @database_group.command(
        name="heads",
        help="Show current available heads in the script directory",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @verbose_option
    @click.option(
        "--resolve-dependencies",
        is_flag=True,
        default=False,
        help="Resolve dependencies between heads",
    )
    def show_heads(bind_key: Optional[str], verbose: bool, resolve_dependencies: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Show current heads."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Showing current heads[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.heads(verbose=verbose, resolve_dependencies=resolve_dependencies)

    @database_group.command(
        name="history",
        help="List changeset scripts in chronological order",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @verbose_option
    @click.option(
        "--rev-range",
        type=str,
        default=None,
        help="Revision range (e.g., 'base:head', 'abc:def')",
    )
    @click.option(
        "--indicate-current",
        is_flag=True,
        default=False,
        help="Indicate the current revision",
    )
    def show_history(  # pyright: ignore[reportUnusedFunction]
        bind_key: Optional[str],
        verbose: bool,
        rev_range: Optional[str],
        indicate_current: bool,
    ) -> None:
        """Show revision history."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Showing revision history[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.history(
            rev_range=rev_range,
            verbose=verbose,
            indicate_current=indicate_current,
        )

    @database_group.command(
        name="merge",
        help="Merge two revisions together, creating a new migration file",
    )
    @config_option
    @validate_config_option
    @click.argument("revisions", type=str)
    @bind_key_option
    @click.option("-m", "--message", type=str, default=None, help="Merge message")
    @click.option("--branch-label", type=str, default=None, help="Branch label for merge revision")
    @click.option("--rev-id", type=str, default=None, help="Specify custom revision ID")
    @no_prompt_option
    def merge_revisions(  # pyright: ignore[reportUnusedFunction]
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
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Merging revisions[/]", align="left")

        if message is None:
            message = "merge revisions" if no_prompt else Prompt.ask("Enter merge message")

        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.merge(
            revisions=revisions,
            message=message,
            branch_label=branch_label,
            rev_id=rev_id,
        )

    @database_group.command(
        name="show",
        help="Show the revision denoted by the given symbol",
    )
    @config_option
    @validate_config_option
    @click.argument("revision", type=str)
    @bind_key_option
    def show_revision(bind_key: Optional[str], revision: str) -> None:  # pyright: ignore[reportUnusedFunction]
        """Show details of a specific revision."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule(f"[yellow]Showing revision {revision}[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.show(rev=revision)

    @database_group.command(
        name="branches",
        help="Show current branch points in the migration history",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @verbose_option
    def show_branches(bind_key: Optional[str], verbose: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Show branch points."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Showing branch points[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.branches(verbose=verbose)

    @database_group.command(
        name="list-templates",
        help="List available Alembic migration templates",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    def list_init_templates(bind_key: Optional[str]) -> None:  # pyright: ignore[reportUnusedFunction]
        """List available initialization templates."""
        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Available templates[/]", align="left")
        alembic_commands = AlembicCommands(sqlalchemy_config=sqlalchemy_config)
        alembic_commands.list_templates()

    @database_group.command(
        name="init",
        help="Initialize migrations for the project.",
    )
    @config_option
    @validate_config_option
    @bind_key_option
    @click.argument(
        "directory",
        default=None,
        required=False,
    )
    @click.option("--multidb", is_flag=True, default=False, help="Support multiple databases")
    @click.option("--package", is_flag=True, default=True, help="Create `__init__.py` for created folder")
    @no_prompt_option
    def init_alembic(  # pyright: ignore[reportUnusedFunction]
        bind_key: Optional[str], directory: Optional[str], multidb: bool, package: bool, no_prompt: bool
    ) -> None:
        """Initialize the database migrations."""
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.commands import AlembicCommands

        ctx = cast("click.Context", click.get_current_context())
        configs = [get_config_by_bind_key(ctx, bind_key)] if bind_key is not None else _resolve_alchemy_configs(ctx)
        console.rule("[yellow]Initializing database migrations.", align="left")
        input_confirmed = (
            True if no_prompt else Confirm.ask("[bold]Are you sure you want initialize migrations for the project?[/]")
        )
        if input_confirmed:
            for config in configs:
                target_directory = config.alembic_config.script_location if directory is None else directory
                alembic_commands = AlembicCommands(sqlalchemy_config=config)
                alembic_commands.init(directory=target_directory, multidb=multidb, package=package)

    @database_group.command(
        name="make-migrations",
        help="Create a new migration revision.",
    )
    @config_option
    @validate_config_option
    @bind_key_option
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
    @no_prompt_option
    def create_revision(  # pyright: ignore[reportUnusedFunction]
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

        ctx = cast("click.Context", click.get_current_context())
        sqlalchemy_config = get_config_by_bind_key(ctx, bind_key)
        console.rule("[yellow]Starting database upgrade process[/]", align="left")
        if message is None:
            message = "autogenerated" if no_prompt else Prompt.ask("Please enter a message describing this revision")

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
    @config_option
    @validate_config_option
    @bind_key_option
    @no_prompt_option
    def drop_all(bind_key: Optional[str], no_prompt: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        """Drop all tables from the database."""
        from anyio import run
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.utils import drop_all
        from advanced_alchemy.base import metadata_registry

        ctx = cast("click.Context", click.get_current_context())
        configs = [get_config_by_bind_key(ctx, bind_key)] if bind_key is not None else _resolve_alchemy_configs(ctx)
        console.rule("[yellow]Dropping all tables from the database[/]", align="left")
        input_confirmed = no_prompt or Confirm.ask(
            "[bold red]Are you sure you want to drop all tables from the database?"
        )

        async def _drop_all(
            configs: "Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]",
        ) -> None:
            for config in configs:
                engine = config.get_engine()
                await drop_all(engine, config.alembic_config.version_table_name, metadata_registry.get(config.bind_key))

        if input_confirmed:
            run(_drop_all, configs)

    @database_group.command(name="dump-data", help="Dump specified tables from the database to JSON files.")
    @config_option
    @validate_config_option
    @bind_key_option
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
    def dump_table_data(bind_key: Optional[str], table_names: tuple[str, ...], dump_dir: Path) -> None:  # pyright: ignore[reportUnusedFunction]
        """Dump table data to JSON files."""
        from anyio import run
        from rich.prompt import Confirm

        from advanced_alchemy.alembic.utils import dump_tables
        from advanced_alchemy.base import metadata_registry, orm_registry

        ctx = cast("click.Context", click.get_current_context())
        configs = [get_config_by_bind_key(ctx, bind_key)] if bind_key is not None else _resolve_alchemy_configs(ctx)
        all_tables = "*" in table_names

        if all_tables and not Confirm.ask(
            "[yellow bold]You have specified '*'. Are you sure you want to dump all tables from the database?",
        ):
            return console.rule("[red bold]No data was dumped.", style="red", align="left")

        async def _dump_tables() -> None:
            for config in configs:
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


class _ConsoleProxy:
    """Lazy Rich console proxy so registering CLI groups does not import ``rich``."""

    def rule(self, *args: Any, **kwargs: Any) -> None:
        from rich import get_console

        get_console().rule(*args, **kwargs)

    def print(self, *args: Any, **kwargs: Any) -> None:
        from rich import get_console

        get_console().print(*args, **kwargs)


def _load_toml(pyproject_path: Path) -> dict[str, Any]:
    """Load TOML data from ``pyproject_path`` using ``tomllib`` or ``tomli``."""
    toml_mod = import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")
    with pyproject_path.open("rb") as f:
        return cast("dict[str, Any]", toml_mod.load(f))


def _normalize_config_path(config_path: str) -> str:
    """Normalize supported config path syntax to a dotted path.

    Args:
        config_path: Dotted ``module.attribute`` or ``module:attribute`` path.

    Returns:
        A dotted path string.

    Raises:
        ImproperConfigurationError: If ``:`` is used with invalid syntax.
    """
    from advanced_alchemy.exceptions import ImproperConfigurationError

    module_path, separator, attribute_path = config_path.partition(":")
    if not separator:
        return config_path
    if not module_path or not attribute_path or ":" in attribute_path:
        msg = (
            f"Config path '{config_path}' is not a valid reference. "
            "Use 'module:attribute' with a single ':', or dotted 'module.attribute'."
        )
        raise ImproperConfigurationError(msg)
    return f"{module_path}.{attribute_path}"


def _import_config_target(config_path: str) -> Any:
    """Import a config target or module from ``config_path``."""
    from advanced_alchemy.utils import module_loader

    normalized = _normalize_config_path(config_path)
    if "." not in normalized:
        return import_module(normalized)

    try:
        return module_loader.import_string(normalized)
    except ImportError as orig_err:
        try:
            return import_module(normalized)
        except ImportError:
            raise orig_err from None


def _run_coroutine_sync(coro: "Coroutine[Any, Any, Any]") -> Any:
    """Execute a coroutine from synchronous code even when an event loop is running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def _is_direct_config(config: Any) -> bool:
    """Return ``True`` if ``config`` is a direct SQLAlchemy config instance."""
    if isinstance(config, type):
        return False
    return (
        getattr(config, "alembic_config", None) is not None
        and hasattr(config, "bind_key")
        and callable(getattr(config, "get_engine", None))
    )


def _is_sequence_not_str(value: Any) -> bool:
    """Return ``True`` when ``value`` is a non-string, non-bytes ``Sequence``."""
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _is_valid_config(config: Any) -> bool:
    """Return ``True`` if ``config`` is a direct config or a wrapper exposing ``.config``."""
    if _is_direct_config(config):
        return True
    if isinstance(config, type) or not hasattr(config, "config"):
        return False
    nested: Any = getattr(config, "config", None)
    if _is_direct_config(nested):
        return True
    if not _is_sequence_not_str(nested):
        return False
    nested_items = cast("Sequence[Any]", nested)
    return bool(nested_items) and all(_is_direct_config(item) for item in nested_items)


def _unwrap_nested_configs(config: Any) -> "list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]":
    """Unwrap a config or wrapper object into a flat list of direct configs."""
    if _is_direct_config(config):
        return [cast("Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]", config)]
    nested: Any = getattr(config, "config", config)
    if _is_sequence_not_str(nested):
        nested_items = cast("Sequence[Any]", nested)
        return [cast("Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]", item) for item in nested_items]
    return [cast("Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]", nested)]


def _is_valid_config_or_sequence(value: Any) -> bool:
    """Return ``True`` if ``value`` is a valid config or non-empty sequence of valid configs."""
    if _is_valid_config(value):
        return True
    if not _is_sequence_not_str(value):
        return False
    items = cast("Sequence[Any]", value)
    return bool(items) and all(_is_valid_config(item) for item in items)


def _describe_module_reference(module: ModuleType, config_path: str) -> str:
    """Build an actionable error message when ``config_path`` resolves to a module."""
    candidates = sorted(
        name for name, value in vars(module).items() if not name.startswith("_") and _is_valid_config_or_sequence(value)
    )
    if candidates:
        examples = ", ".join(f"'{config_path}:{name}'" for name in candidates)
        return (
            f"Config '{config_path}' names a module, not a database configuration. "
            f"Point at the configuration itself, for example {examples}."
        )
    return (
        f"Config '{config_path}' names a module that exports no database configuration. "
        "Point at a config instance, a list of configs, or a factory returning them, "
        "using 'module:attribute' or 'module.attribute'."
    )


def _validate_config_result(
    config_result: Any, config_path: str
) -> "Union[list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]], SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]":
    """Validate and unwrap a resolved configuration result."""
    from advanced_alchemy.exceptions import ImproperConfigurationError

    if isinstance(config_result, ModuleType):
        raise ImproperConfigurationError(_describe_module_reference(config_result, config_path))

    if config_result is None:
        msg = f"Config '{config_path}' resolved to None. Expected config instance or list of configs."
        raise ImproperConfigurationError(msg)

    if _is_sequence_not_str(config_result):
        result_items = cast("Sequence[Any]", config_result)
        if not result_items:
            msg = f"Config '{config_path}' resolved to empty list. Expected at least one config."
            raise ImproperConfigurationError(msg)

        unwrapped_list: list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = []
        for i, item in enumerate(result_items):
            if not _is_valid_config(item):
                msg = (
                    f"Config '{config_path}' returned invalid config at index {i}. "
                    "Expected SQLAlchemyAsyncConfig or SQLAlchemySyncConfig instance."
                )
                raise ImproperConfigurationError(msg)
            unwrapped_list.extend(_unwrap_nested_configs(item))
        return unwrapped_list

    if not _is_valid_config(config_result):
        msg = (
            f"Config '{config_path}' returned invalid type '{type(config_result).__name__}'. "
            "Expected SQLAlchemyAsyncConfig or SQLAlchemySyncConfig instance or list."
        )
        raise ImproperConfigurationError(msg)

    unwrapped = _unwrap_nested_configs(config_result)
    if len(unwrapped) == 1:
        return unwrapped[0]
    return unwrapped


def _emit_validation_summary(
    console: Any,
    configs: "Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]",
) -> None:
    """Print configuration validation output to the console."""
    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    console.print(f"[green]✓[/] Successfully loaded {len(configs)} config(s)")
    for i, cfg in enumerate(configs):
        config_name = cfg.bind_key or f"config-{i}"
        config_type = type(cfg).__name__
        is_async = isinstance(cfg, SQLAlchemyAsyncConfig) or bool(getattr(cfg, "is_async", False))
        execution_hint = "[dim cyan](async-capable)[/]" if is_async else "[dim](sync)[/]"
        console.print(f"  [dim]•[/] {config_name}: {config_type} {execution_hint}")


def _print_missing_config_error(console: Any) -> None:
    """Print actionable instructions when no CLI configuration can be found."""
    from rich.markup import escape

    console.print("[red]Error: No Advanced Alchemy config found.[/]")
    console.print("\nSpecify config using one of:")
    console.print("  1. CLI flag:        alchemy --config myapp.config:alchemy_config <command>")
    console.print("  2. Environment var: export ALCHEMY_CONFIG=myapp.config:alchemy_config")
    console.print(f"  3. pyproject.toml:  {escape('[tool.advanced-alchemy]')}")
    console.print('                      config = "myapp.config:alchemy_config"')


def _load_and_deduplicate_configs(
    effective_path: str,
) -> "list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]":
    """Resolve comma-separated config paths and deduplicate by ``bind_key`` (later wins)."""
    all_configs: list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = []
    for raw_segment in effective_path.split(","):
        segment = raw_segment.strip()
        if not segment:
            continue
        resolved = resolve_config_sync(segment)
        if isinstance(resolved, list):
            all_configs.extend(resolved)
        else:
            all_configs.append(resolved)

    configs_list: list[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = []
    seen_bind_keys: dict[str, int] = {}
    for cfg in all_configs:
        if cfg.bind_key is not None and cfg.bind_key in seen_bind_keys:
            configs_list[seen_bind_keys[cfg.bind_key]] = cfg
        else:
            if cfg.bind_key is not None:
                seen_bind_keys[cfg.bind_key] = len(configs_list)
            configs_list.append(cfg)
    return configs_list


def _maybe_validate_configs(
    ctx: "Any",
    console: Any,
    configs: "Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]",
) -> None:
    """Emit validation summary once when ``--validate-config`` is active."""
    if ctx.obj.get("validate_config") and not ctx.obj.get("_config_validated"):
        ctx.obj["_config_validated"] = True
        _emit_validation_summary(console, configs)


def _resolve_alchemy_configs(
    ctx: "Any",
    config_path: Optional[str] = None,
) -> "Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]":
    """Load or retrieve SQLAlchemy configs from CLI option, env var, ``pyproject.toml``, or ``ctx.obj``."""
    from rich import get_console
    from rich.markup import escape

    from advanced_alchemy.exceptions import AdvancedAlchemyError

    ctx.ensure_object(dict)
    console = get_console()
    effective_path: Optional[str] = (
        config_path if config_path is not None else cast("Optional[str]", ctx.obj.get("config_path"))
    )

    if effective_path is None and ctx.obj.get("configs"):
        existing_configs = cast(
            "Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]",
            ctx.obj["configs"],
        )
        _maybe_validate_configs(ctx, console, existing_configs)
        return existing_configs

    if effective_path is None:
        effective_path = discover_config_from_pyproject()
        if effective_path is not None:
            console.print("[dim]Using config from pyproject.toml[/]")

    if effective_path is None:
        _print_missing_config_error(console)
        ctx.exit(1)
        raise SystemExit(1)

    cwd = str(Path.cwd())
    added_cwd = cwd not in sys.path
    if added_cwd:
        sys.path.insert(0, cwd)

    try:
        configs_list = _load_and_deduplicate_configs(effective_path)
    except (ImportError, AdvancedAlchemyError) as e:
        console.print(f"[red]Error loading config: {escape(str(e))}[/]", emoji=False)
        ctx.exit(1)
        raise
    else:
        if not configs_list:
            console.print("[red]Error: No valid configs found after resolution.[/]")
            console.print("\nEnsure your config path returns valid config instance(s).")
            ctx.exit(1)
            raise SystemExit(1)

        ctx.obj["configs"] = configs_list
        ctx.obj["config_path"] = None
        _maybe_validate_configs(ctx, console, configs_list)
        return configs_list
    finally:
        if added_cwd and cwd in sys.path and sys.path[0] == cwd:
            sys.path.remove(cwd)


def _config_option(click_mod: Any) -> Callable[[Any], Any]:
    """Build a reusable ``--config`` / ``-c`` Click option decorator."""
    from click.core import ParameterSource

    def _callback(ctx: "Any", param: "Any", value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        ctx.ensure_object(dict)
        source = ctx.get_parameter_source(param.name) if hasattr(ctx, "get_parameter_source") else None
        current_source = ctx.obj.get("config_source")
        if source == ParameterSource.ENVIRONMENT and current_source == ParameterSource.COMMANDLINE:
            return value
        ctx.obj["config_path"] = value
        ctx.obj["config_source"] = source
        return value

    return cast(
        "Callable[[Any], Any]",
        click_mod.option(
            "--config",
            "-c",
            help="Dotted or colon path to SQLAlchemy config(s) or factory callable (env: ALCHEMY_CONFIG)",
            required=False,
            default=None,
            type=str,
            envvar="ALCHEMY_CONFIG",
            expose_value=False,
            callback=_callback,
        ),
    )


def _validate_config_option(click_mod: Any) -> Callable[[Any], Any]:
    """Build a reusable ``--validate-config`` Click option decorator."""

    def _callback(ctx: "Any", _param: "Any", value: bool) -> bool:
        if value:
            ctx.ensure_object(dict)
            ctx.obj["validate_config"] = True
        return value

    return cast(
        "Callable[[Any], Any]",
        click_mod.option(
            "--validate-config",
            is_flag=True,
            default=False,
            help="Validate configuration before executing migrations",
            expose_value=False,
            callback=_callback,
        ),
    )

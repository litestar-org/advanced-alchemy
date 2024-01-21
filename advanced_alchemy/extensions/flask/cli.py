from __future__ import annotations

from typing import TYPE_CHECKING, cast

from click import argument, group, option, prompt, echo, confirm
from advanced_alchemy.config import engine
from flask.cli import FlaskGroup
from click import secho
from flask import current_app
from flask.cli import with_appcontext
from advanced_alchemy.alembic.commands import AlembicCommands

if TYPE_CHECKING:
    from flask_sqlalchemy.extension import SQLALchemy
    from alembic.migration import MigrationContext
    from alembic.operations.ops import MigrationScript, UpgradeOps


@group(cls=FlaskGroup, name="database")
def database_group() -> None:
    """Manage SQLAlchemy database components."""


@database_group.command(
    name="show-current-revision",
    help="Shows the current revision for the database.",
)
@option("--verbose", type=bool, help="Enable verbose output.", default=False, is_flag=True)
@with_appcontext
def show_database_revision( verbose: bool) -> None:
    """Show current database revision."""
    secho("*Listing current revision")

    alembic_commands = AlembicCommands(engine=app)
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
@with_appcontext
def downgrade_database( revision: str, sql: bool, tag: str | None, no_prompt: bool) -> None:
    """Downgrade the database to the latest revision."""
    secho("*Starting database downgrade process")
    input_confirmed = (
        True
        if no_prompt
        else confirm(f"Are you sure you you want to downgrade the database to the `{revision}` revision?")
    )
    if input_confirmed:
        _db = cast("SQLALchemy", current_app.extensions["sqlalchemy"])
        alembic_commands = AlembicCommands(engine=)
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
def upgrade_database( revision: str, sql: bool, tag: str | None, no_prompt: bool) -> None:
    """Upgrade the database to the latest revision."""
    secho("*Starting database upgrade process*", align="left")
    input_confirmed = (
        True
        if no_prompt
        else prompt(f"[bold]Are you sure you you want migrate the database to the `{revision}` revision?*")
    )
    if input_confirmed:
        alembic_commands = AlembicCommands(app=app)
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
@with_appcontext
def init_alembic( directory: str | None, multidb: bool, package: bool, no_prompt: bool) -> None:
    """Upgrade the database to the latest revision."""
    secho("*Initializing database migrations.", align="left")
    if directory is None:
        directory = plugin._alembic_config.script_location  # noqa: SLF001
    input_confirmed = (
        True
        if no_prompt
        else prompt(f"[bold]Are you sure you you want initialize the project in `{directory}`?*")
    )
    if input_confirmed:
        alembic_commands = AlembicCommands(app)
        alembic_commands.init(directory=directory, multidb=multidb, package=package)


@database_group.command(
    name="make-migrations",
    help="Create a new migration revision.",
)
@option("-m", "--message", default=None, help="Revision message")
@option("--autogenerate/--no-autogenerate", default=True, help="Automatically populate revision with detected changes")
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
def create_revision(

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

    def process_revision_directives(
        context: MigrationContext,  # noqa: ARG001
        revision: tuple[str],  # noqa: ARG001
        directives: list[MigrationScript],
    ) -> None:
        """Handle revision directives."""

        if autogenerate and cast("UpgradeOps", directives[0].upgrade_ops).is_empty():
            # Generate a revision file only if changes to the schema are detected
            secho(
                "The generation of a migration file is being skipped because it would result in an empty file.",
                style="magenta",
                align="left",
            )
            secho(
                "More information can be found here. https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect",
                style="magenta",
                align="left",
            )
            secho(
                "If you intend to create an empty migration file, use the --no-autogenerate option.",
                style="magenta",
                align="left",
            )
            directives.clear()

    secho("*Starting database upgrade process*", align="left")
    if message is None:
        message = "autogenerated" if no_prompt else prompt("Please enter a message describing this revision")

    alembic_commands = AlembicCommands(app=app)
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


@database_group.command(
    name="merge-migrations",
    help="Merge multiple revisions into a single new revision.",
)
@option("--revisions", default="head", help="Specify head revision to use as base for new revision.")
@option("-m", "--message", default=None, help="Revision message")
@option("--branch-label", default=None, help="Specify a branch label to apply to the new revision")
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
@with_appcontext
def merge_revisions(

    revisions: str,
    message: str | None,
    branch_label: str | None,
    rev_id: str | None,
    no_prompt: bool,
) -> None:
    """Merge multiple revisions into a single new revision."""
    secho("*Starting database upgrade process*", align="left")
    if message is None:
        message = "autogenerated" if no_prompt else prompt("Please enter a message describing this revision")

    alembic_commands = AlembicCommands(app=app)
    alembic_commands.merge(message=message, revisions=revisions, branch_label=branch_label, rev_id=rev_id)


@database_group.command(
    name="stamp-migration",
    help="Mark (Stamp) a specific revision as current without applying the migrations.",
)
@option(
    "--revision",
    type=str,
    help="Revision to stamp to",
    default="-1",
)
@option("--sql", type=bool, help="Generate SQL output for offline migrations.", default=False, is_flag=True)
@option(
    "--purge",
    type=bool,
    help="Delete existing records in the alembic version table before stamping.",
    default=False,
    is_flag=True,
)
@option(
    "--tag",
    help="an arbitrary 'tag' that can be intercepted by custom env.py scripts via the .EnvironmentContext.get_tag_argument method.",
    type=str,
    default=None,
)
@option(
    "--no-prompt",
    help="Do not prompt for confirmation.",
    type=bool,
    default=False,
    required=False,
    show_default=True,
    is_flag=True,
)
@with_appcontext
def stamp_revision( revision: str, sql: bool, tag: str | None, purge: bool, no_prompt: bool) -> None:
    """Create a new database revision."""
    secho("*Stamping database revision as current*", align="left")
    input_confirmed = True if no_prompt else prompt("Are you sure you you want to stamp revision as current?")
    if input_confirmed:
        alembic_commands = AlembicCommands(app=app)
        alembic_commands.stamp(sql=sql, revision=revision, tag=tag, purge=purge)

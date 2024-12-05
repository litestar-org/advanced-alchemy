from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Mapping, TextIO

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from alembic import command as migration_command
from alembic.config import Config as _AlembicCommandConfig
from alembic.ddl.impl import DefaultImpl

if TYPE_CHECKING:
    import os
    from argparse import Namespace
    from pathlib import Path

    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine

    from advanced_alchemy.config.sync import SQLAlchemySyncConfig
    from alembic.runtime.environment import ProcessRevisionDirectiveFn
    from alembic.script.base import Script


class AlembicSpannerImpl(DefaultImpl):
    """Alembic implementation for Spanner."""

    __dialect__ = "spanner+spanner"


class AlembicDuckDBImpl(DefaultImpl):
    """Alembic implementation for DuckDB."""

    __dialect__ = "duckdb"


class AlembicCommandConfig(_AlembicCommandConfig):
    def __init__(
        self,
        engine: Engine | AsyncEngine,
        version_table_name: str,
        bind_key: str | None = None,
        file_: str | os.PathLike[str] | None = None,
        ini_section: str = "alembic",
        output_buffer: TextIO | None = None,
        stdout: TextIO = sys.stdout,
        cmd_opts: Namespace | None = None,
        config_args: Mapping[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        template_directory: Path | None = None,
        version_table_schema: str | None = None,
        render_as_batch: bool = True,
        compare_type: bool = False,
        user_module_prefix: str | None = "sa.",
    ) -> None:
        """Initialize the AlembicCommandConfig.

        Args:
            engine (sqlalchemy.engine.Engine | sqlalchemy.ext.asyncio.AsyncEngine): The SQLAlchemy engine instance.
            version_table_name (str): The name of the version table.
            bind_key (str | None): The bind key for the metadata.
            file_ (str | os.PathLike[str] | None): The file path for the alembic configuration.
            ini_section (str): The ini section name.
            output_buffer (typing.TextIO | None): The output buffer for alembic commands.
            stdout (typing.TextIO): The standard output stream.
            cmd_opts (argparse.Namespace | None): Command line options.
            config_args (typing.Mapping[str, typing.Any] | None): Additional configuration arguments.
            attributes (dict[str, typing.Any] | None): Additional attributes for the configuration.
            template_directory (pathlib.Path | None): The directory for alembic templates.
            version_table_schema (str | None): The schema for the version table.
            render_as_batch (bool): Whether to render migrations as batch.
            compare_type (bool): Whether to compare types during migrations.
            user_module_prefix (str | None): The prefix for user modules.
        """
        self.template_directory = template_directory
        self.bind_key = bind_key
        self.version_table_name = version_table_name
        self.version_table_pk = engine.dialect.name != "spanner+spanner"
        self.version_table_schema = version_table_schema
        self.render_as_batch = render_as_batch
        self.user_module_prefix = user_module_prefix
        self.compare_type = compare_type
        self.engine = engine
        self.db_url = engine.url.render_as_string(hide_password=False)
        if config_args is None:
            config_args = {}
        super().__init__(file_, ini_section, output_buffer, stdout, cmd_opts, config_args, attributes)

    def get_template_directory(self) -> str:
        """Return the directory where Alembic setup templates are found.

        This method is used by the alembic ``init`` and ``list_templates``
        commands.

        """
        if self.template_directory is not None:
            return str(self.template_directory)
        return super().get_template_directory()


class AlembicCommands:
    def __init__(self, sqlalchemy_config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> None:
        """Initialize the AlembicCommands.

        Args:
            sqlalchemy_config (SQLAlchemyAsyncConfig | SQLAlchemySyncConfig): The SQLAlchemy configuration.
        """
        self.sqlalchemy_config = sqlalchemy_config
        self.config = self._get_alembic_command_config()

    def upgrade(
        self,
        revision: str = "head",
        sql: bool = False,
        tag: str | None = None,
    ) -> None:
        """Upgrade the database to a specified revision.

        Args:
            revision (str): The target revision to upgrade to.
            sql (bool): If True, generate SQL script instead of applying changes.
            tag (str | None): An optional tag to apply to the migration.
        """

        return migration_command.upgrade(config=self.config, revision=revision, tag=tag, sql=sql)

    def downgrade(
        self,
        revision: str = "head",
        sql: bool = False,
        tag: str | None = None,
    ) -> None:
        """Downgrade the database to a specified revision.

        Args:
            revision (str): The target revision to downgrade to.
            sql (bool): If True, generate SQL script instead of applying changes.
            tag (str | None): An optional tag to apply to the migration.
        """
        return migration_command.downgrade(config=self.config, revision=revision, tag=tag, sql=sql)

    def check(self) -> None:
        """Check for pending upgrade operations.

        This method checks if there are any pending upgrade operations
        that need to be applied to the database.
        """
        return migration_command.check(config=self.config)

    def current(self, verbose: bool = False) -> None:
        """Display the current revision of the database.

        Args:
            verbose (bool): If True, display detailed information.
        """
        return migration_command.current(self.config, verbose=verbose)

    def edit(self, revision: str) -> None:
        """Edit the revision script using the system editor.

        Args:
            revision (str): The revision identifier to edit.
        """
        return migration_command.edit(config=self.config, rev=revision)

    def ensure_version(self, sql: bool = False) -> None:
        """Ensure the alembic version table exists.

        Args:
            sql (bool): If True, generate SQL script instead of applying changes.
        """
        return migration_command.ensure_version(config=self.config, sql=sql)

    def heads(self, verbose: bool = False, resolve_dependencies: bool = False) -> None:
        """Show current available heads in the script directory.

        Args:
            verbose (bool): If True, display detailed information.
            resolve_dependencies (bool): If True, resolve dependencies between heads.
        """
        return migration_command.heads(config=self.config, verbose=verbose, resolve_dependencies=resolve_dependencies)

    def history(
        self,
        rev_range: str | None = None,
        verbose: bool = False,
        indicate_current: bool = False,
    ) -> None:
        """List changeset scripts in chronological order.

        Args:
            rev_range (str | None): The revision range to display.
            verbose (bool): If True, display detailed information.
            indicate_current (bool): If True, indicate the current revision.
        """
        return migration_command.history(
            config=self.config,
            rev_range=rev_range,
            verbose=verbose,
            indicate_current=indicate_current,
        )

    def merge(
        self,
        revisions: str,
        message: str | None = None,
        branch_label: str | None = None,
        rev_id: str | None = None,
    ) -> Script | None:
        """Merge two revisions together.

        Args:
            revisions (str): The revisions to merge.
            message (str | None): The commit message for the merge.
            branch_label (str | None): The branch label for the merge.
            rev_id (str | None): The revision ID for the merge.

        Returns:
            Script | None: The resulting script from the merge.
        """
        return migration_command.merge(
            config=self.config,
            revisions=revisions,
            message=message,
            branch_label=branch_label,
            rev_id=rev_id,
        )

    def revision(
        self,
        message: str | None = None,
        autogenerate: bool = False,
        sql: bool = False,
        head: str = "head",
        splice: bool = False,
        branch_label: str | None = None,
        version_path: str | None = None,
        rev_id: str | None = None,
        depends_on: str | None = None,
        process_revision_directives: ProcessRevisionDirectiveFn | None = None,
    ) -> Script | list[Script | None] | None:
        """Create a new revision file.

        Args:
            message (str | None): The commit message for the revision.
            autogenerate (bool): If True, autogenerate the revision script.
            sql (bool): If True, generate SQL script instead of applying changes.
            head (str): The head revision to base the new revision on.
            splice (bool): If True, create a splice revision.
            branch_label (str | None): The branch label for the revision.
            version_path (str | None): The path for the version file.
            rev_id (str | None): The revision ID for the new revision.
            depends_on (str | None): The revisions this revision depends on.
            process_revision_directives (ProcessRevisionDirectiveFn | None): A function to process revision directives.

        Returns:
            Script | List[Script | None] | None: The resulting script(s) from the revision.
        """
        return migration_command.revision(
            config=self.config,
            message=message,
            autogenerate=autogenerate,
            sql=sql,
            head=head,
            splice=splice,
            branch_label=branch_label,
            version_path=version_path,
            rev_id=rev_id,
            depends_on=depends_on,
            process_revision_directives=process_revision_directives,
        )

    def show(
        self,
        rev: Any,
    ) -> None:
        """Show the revision(s) denoted by the given symbol.

        Args:
            rev (Any): The revision symbol to display.
        """
        return migration_command.show(config=self.config, rev=rev)

    def init(
        self,
        directory: str,
        package: bool = False,
        multidb: bool = False,
    ) -> None:
        """Initialize a new scripts directory.

        Args:
            directory (str): The directory to initialize.
            package (bool): If True, create a package.
            multidb (bool): If True, initialize for multiple databases.
        """
        template = "sync"
        if isinstance(self.sqlalchemy_config, SQLAlchemyAsyncConfig):
            template = "asyncio"
        if multidb:
            template = f"{template}-multidb"
            msg = "Multi database Alembic configurations are not currently supported."
            raise NotImplementedError(msg)
        return migration_command.init(
            config=self.config,
            directory=directory,
            template=template,
            package=package,
        )

    def list_templates(self) -> None:
        """List available templates.

        This method lists all available templates for alembic initialization.
        """
        return migration_command.list_templates(config=self.config)

    def stamp(
        self,
        revision: str,
        sql: bool = False,
        tag: str | None = None,
        purge: bool = False,
    ) -> None:
        """Stamp the revision table with the given revision.

        Args:
            revision (str): The revision to stamp.
            sql (bool): If True, generate SQL script instead of applying changes.
            tag (str | None): An optional tag to apply to the migration.
            purge (bool): If True, purge the revision history.
        """
        return migration_command.stamp(config=self.config, revision=revision, sql=sql, tag=tag, purge=purge)

    def _get_alembic_command_config(self) -> AlembicCommandConfig:
        """Get the Alembic command configuration.

        Returns:
            AlembicCommandConfig: The configuration for Alembic commands.
        """
        kwargs: dict[str, Any] = {}
        if self.sqlalchemy_config.alembic_config.script_config:
            kwargs["file_"] = self.sqlalchemy_config.alembic_config.script_config
        if self.sqlalchemy_config.alembic_config.template_path:
            kwargs["template_directory"] = self.sqlalchemy_config.alembic_config.template_path
        kwargs.update(
            {
                "engine": self.sqlalchemy_config.get_engine(),
                "version_table_name": self.sqlalchemy_config.alembic_config.version_table_name,
            },
        )
        self.config = AlembicCommandConfig(**kwargs)
        self.config.set_main_option("script_location", self.sqlalchemy_config.alembic_config.script_location)
        return self.config

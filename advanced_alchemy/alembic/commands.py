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


class AlembicCommandConfig(_AlembicCommandConfig):
    def __init__(
        self,
        engine: Engine | AsyncEngine,
        version_table_name: str,
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
        self.template_directory = template_directory
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


class AlembicSpannerImpl(DefaultImpl):
    """Alembic implementation for Spanner."""

    __dialect__ = "spanner+spanner"


class AlembicDuckDBImpl(DefaultImpl):
    """Alembic implementation for DuckDB."""

    __dialect__ = "duckdb"


class AlembicCommands:
    def __init__(self, sqlalchemy_config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> None:
        self.sqlalchemy_config = sqlalchemy_config
        self.config = self._get_alembic_command_config()

    def upgrade(
        self,
        revision: str = "head",
        sql: bool = False,
        tag: str | None = None,
    ) -> None:
        """Create or upgrade a database."""

        return migration_command.upgrade(config=self.config, revision=revision, tag=tag, sql=sql)

    def downgrade(
        self,
        revision: str = "head",
        sql: bool = False,
        tag: str | None = None,
    ) -> None:
        """Downgrade a database to a specific revision."""

        return migration_command.downgrade(config=self.config, revision=revision, tag=tag, sql=sql)

    def check(self) -> None:
        """Check if revision command with autogenerate has pending upgrade ops."""

        return migration_command.check(config=self.config)

    def current(self, verbose: bool = False) -> None:
        """Display the current revision for a database."""

        return migration_command.current(self.config, verbose=verbose)

    def edit(self, revision: str) -> None:
        """Edit revision script(s) using $EDITOR."""

        return migration_command.edit(config=self.config, rev=revision)

    def ensure_version(self, sql: bool = False) -> None:
        """Create the alembic version table if it doesn't exist already."""

        return migration_command.ensure_version(config=self.config, sql=sql)

    def heads(self, verbose: bool = False, resolve_dependencies: bool = False) -> None:
        """Show current available heads in the script directory."""

        return migration_command.heads(config=self.config, verbose=verbose, resolve_dependencies=resolve_dependencies)

    def history(
        self,
        rev_range: str | None = None,
        verbose: bool = False,
        indicate_current: bool = False,
    ) -> None:
        """List changeset scripts in chronological order."""

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
        """Merge two revisions together. Creates a new migration file."""

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
        """Create a new revision file."""

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
        """Show the revision(s) denoted by the given symbol."""

        return migration_command.show(config=self.config, rev=rev)

    def init(
        self,
        directory: str,
        package: bool = False,
        multidb: bool = False,
    ) -> None:
        """Initialize a new scripts directory."""
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
        """List available templates."""

        return migration_command.list_templates(config=self.config)

    def stamp(
        self,
        revision: str,
        sql: bool = False,
        tag: str | None = None,
        purge: bool = False,
    ) -> None:
        """'stamp' the revision table with the given revision; don't run any migrations."""
        return migration_command.stamp(config=self.config, revision=revision, sql=sql, tag=tag, purge=purge)

    def _get_alembic_command_config(self) -> AlembicCommandConfig:
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

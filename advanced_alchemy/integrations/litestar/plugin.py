from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from litestar.contrib.sqlalchemy.plugins import SQLAlchemyInitPlugin, SQLAlchemyPlugin, _slots_base
from litestar.contrib.sqlalchemy.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from advanced_alchemy.alembic.commands import AlembicCommands as _AlembicCommands
from advanced_alchemy.exceptions import ImproperConfigurationError
from alembic import command as migration_command

if TYPE_CHECKING:
    from click import Group
    from litestar import Litestar

    from advanced_alchemy.config.asyncio import AlembicAsyncConfig
    from advanced_alchemy.config.sync import AlembicSyncConfig


__all__ = ("AdvancedAlchemyPlugin",)


def _get_advanced_alchemy_plugin(app: Litestar) -> AdvancedAlchemyPlugin:
    """Retrieve a advanced alchemy plugin from the Litestar application's plugins.

    This function attempts to find and return either the SQLAlchemyPlugin or SQLAlchemyInitPlugin.
    If neither plugin is found, it raises an ImproperlyConfiguredException.
    """
    with suppress(KeyError):
        return app.plugins.get(AdvancedAlchemyPlugin)
    msg = "Failed to initialize database migrations. The required plugin (SQLAlchemyPlugin or SQLAlchemyInitPlugin) is missing."
    raise ImproperConfigurationError(
        msg,
    )


def _get_sqlalchemy_plugin(app: Litestar) -> SQLAlchemyPlugin | SQLAlchemyInitPlugin:
    """Retrieve the sqlalchemy plugin from the Litestar application's plugins.

    This function attempts to find and return either the SQLAlchemyPlugin or SQLAlchemyInitPlugin.
    If neither plugin is found, it raises an ImproperlyConfiguredException.
    """
    for type_ in SQLAlchemyPlugin, SQLAlchemyInitPlugin:
        with suppress(KeyError):
            return app.plugins.get(type_)
    msg = "Failed to initialize database migrations. The required plugin (SQLAlchemyPlugin or SQLAlchemyInitPlugin) is missing."
    raise ImproperConfigurationError(
        msg,
    )


class AlembicCommands(_AlembicCommands):
    def __init__(self, app: Litestar) -> None:
        self._app = app
        self.sqlalchemy_config = _get_sqlalchemy_plugin(self._app)._config  # type: ignore[assignment]  # noqa: SLF001
        self.plugin_config = _get_advanced_alchemy_plugin(self._app)._config  # noqa: SLF001
        self.config = self._get_alembic_command_config()

    def init(
        self,
        directory: str,
        package: bool = False,
        multidb: bool = False,
    ) -> None:
        """Initialize a new scripts directory."""
        template = "sync"
        if isinstance(self.plugin_config, SQLAlchemyAsyncConfig):
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


class AdvancedAlchemyPlugin(InitPluginProtocol, CLIPluginProtocol, _slots_base.SlotsBase):
    """Advanced Alchemy plugin lifecycle configuration."""

    def __init__(self, config: AlembicAsyncConfig | AlembicSyncConfig) -> None:
        """Initialize ``SQLAlchemyPlugin``.

        Args:
            config: configure DB connection and hook handlers and dependencies.
        """
        self._config = config

    def on_cli_init(self, cli: Group) -> None:
        from advanced_alchemy.integrations.litestar.cli import database_group

        cli.add_command(database_group)
        return super().on_cli_init(cli)

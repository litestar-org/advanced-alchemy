from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.contrib.sqlalchemy.plugins import _slots_base
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

if TYPE_CHECKING:
    from click import Group

    from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

__all__ = ("AdvancedAlchemyPlugin",)


class AdvancedAlchemyPlugin(InitPluginProtocol, CLIPluginProtocol, _slots_base.SlotsBase):
    """Advanced Alchemy plugin lifecycle configuration."""

    def __init__(self, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> None:
        """Initialize ``SQLAlchemyPlugin``.

        Args:
            config: configure DB connection and hook handlers and dependencies.
        """
        self._config = config
        self._alembic_config = config.alembic_config

    def on_cli_init(self, cli: Group) -> None:
        from advanced_alchemy.integrations.litestar.cli import database_group

        cli.add_command(database_group)
        return super().on_cli_init(cli)

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from litestar.plugins import InitPluginProtocol

from advanced_alchemy.extensions.litestar.plugins import _slots_base
from advanced_alchemy.extensions.litestar.plugins.init import (
    EngineConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.extensions.litestar.plugins.serialization import SQLAlchemySerializationPlugin

if TYPE_CHECKING:
    from litestar.config.app import AppConfig


class SQLAlchemyPlugin(InitPluginProtocol, _slots_base.SlotsBase):
    """A plugin that provides SQLAlchemy integration."""

    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | list[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
    ) -> None:
        """Initialize ``SQLAlchemyPlugin``.

        Args:
            config: configure DB connection and hook handlers and dependencies.
        """
        self._config = config

    @property
    def config(
        self,
    ) -> SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig]:
        return self._config

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure application for use with SQLAlchemy.

        Args:
            app_config: The :class:`AppConfig <.config.app.AppConfig>` instance.
        """
        app_config.plugins.extend([SQLAlchemyInitPlugin(config=self._config), SQLAlchemySerializationPlugin()])
        return app_config


__all__ = (
    "EngineConfig",
    "SQLAlchemyAsyncConfig",
    "SQLAlchemyInitPlugin",
    "SQLAlchemyPlugin",
    "SQLAlchemySerializationPlugin",
    "SQLAlchemySyncConfig",
)

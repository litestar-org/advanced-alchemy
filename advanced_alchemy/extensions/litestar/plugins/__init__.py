from collections.abc import Sequence
from typing import Union

from litestar.config.app import AppConfig
from litestar.plugins import InitPluginProtocol

from advanced_alchemy.extensions.litestar.plugins import _slots_base
from advanced_alchemy.extensions.litestar.plugins.init import (
    EngineConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.extensions.litestar.plugins.serialization import SQLAlchemySerializationPlugin


class SQLAlchemyPlugin(InitPluginProtocol, _slots_base.SlotsBase):
    """A plugin that provides SQLAlchemy integration."""

    def __init__(
        self,
        config: Union[
            SQLAlchemyAsyncConfig, SQLAlchemySyncConfig, Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]
        ],
    ) -> None:
        """Initialize ``SQLAlchemyPlugin``.

        Args:
            config: configure DB connection and hook handlers and dependencies.
        """
        self._config = config if isinstance(config, Sequence) else [config]

    @property
    def config(
        self,
    ) -> Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]:
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

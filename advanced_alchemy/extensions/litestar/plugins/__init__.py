from collections.abc import AsyncGenerator, Generator, Sequence
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Callable, Optional, Union, cast

from litestar.config.app import AppConfig
from litestar.plugins import InitPluginProtocol
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

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

        Returns:
            The :class:`AppConfig <.config.app.AppConfig>` instance.
        """
        app_config.plugins.extend([SQLAlchemyInitPlugin(config=self._config), SQLAlchemySerializationPlugin()])
        return app_config

    def _get_config(self, key: Optional[str] = None) -> Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]:
        """Get a configuration by key.

        Args:
            key: Optional key to identify the configuration. If not provided, uses the first config.

        Raises:
            ValueError: If no configuration is found.

        Returns:
            The SQLAlchemy configuration.
        """
        if key is None:
            return self._config[0]
        for config in self._config:
            if getattr(config, "key", None) == key:
                return config
        msg = f"No configuration found with key {key}"
        raise ValueError(msg)

    def get_session(
        self,
        key: Optional[str] = None,
    ) -> Union[AsyncGenerator[AsyncSession, None], Generator[Session, None, None]]:
        """Get a SQLAlchemy session.

        Args:
            key: Optional key to identify the configuration. If not provided, uses the first config.

        Returns:
            A SQLAlchemy session.
        """
        config = self._get_config(key)

        if isinstance(config, SQLAlchemyAsyncConfig):

            @asynccontextmanager
            async def async_gen() -> AsyncGenerator[AsyncSession, None]:
                async with config.get_session() as session:
                    yield session

            return cast("AsyncGenerator[AsyncSession, None]", async_gen())

        @contextmanager
        def sync_gen() -> Generator[Session, None, None]:
            with config.get_session() as session:
                yield session

        return cast("Generator[Session, None, None]", sync_gen())

    def provide_session(
        self,
        key: Optional[str] = None,
    ) -> Callable[..., Union[AsyncGenerator[AsyncSession, None], Generator[Session, None, None]]]:
        """Get a session provider for dependency injection.

        Args:
            key: Optional key to identify the configuration. If not provided, uses the first config.

        Returns:
            A callable that returns a session provider.
        """

        def provider(
            *args: Any,  # noqa: ARG001
            **kwargs: Any,  # noqa: ARG001
        ) -> Union[AsyncGenerator[AsyncSession, None], Generator[Session, None, None]]:
            return self.get_session(key)

        return provider

    def get_engine(
        self,
        key: Optional[str] = None,
    ) -> Union[AsyncEngine, Engine]:
        """Get the SQLAlchemy engine.

        Args:
            key: Optional key to identify the configuration. If not provided, uses the first config.

        Returns:
            The SQLAlchemy engine.
        """
        config = self._get_config(key)
        return config.get_engine()


__all__ = (
    "EngineConfig",
    "SQLAlchemyAsyncConfig",
    "SQLAlchemyInitPlugin",
    "SQLAlchemyPlugin",
    "SQLAlchemySerializationPlugin",
    "SQLAlchemySyncConfig",
)

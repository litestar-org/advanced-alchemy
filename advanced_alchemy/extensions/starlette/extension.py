# ruff: noqa: ARG001
from __future__ import annotations

import contextlib
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, AsyncGenerator, Callable, Generator, Sequence, Union, overload

from starlette.applications import Starlette
from starlette.requests import Request  # noqa: TC002

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.starlette.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlalchemy.orm import Session
    from starlette.applications import Starlette


class AdvancedAlchemy:
    """AdvancedAlchemy integration for Starlette applications.

    This class manages SQLAlchemy sessions and engine lifecycle within a Starlette application.
    It provides middleware for handling transactions based on commit strategies.

    Args:
        config (advanced_alchemy.config.asyncio.SQLAlchemyAsyncConfig | advanced_alchemy.config.sync.SQLAlchemySyncConfig):
            The SQLAlchemy configuration.
        app (starlette.applications.Starlette | None):
            The Starlette application instance. Defaults to None.
    """

    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
        app: Starlette | None = None,
    ) -> None:
        self._config = config if isinstance(config, Sequence) else [config]
        self._mapped_configs: dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = self.map_configs()  # noqa: UP007
        self._app: Starlette | None = None

        if app is not None:
            self.init_app(app)

    @property
    def config(self) -> Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig]:
        """Current Advanced Alchemy configuration."""

        return self._config

    def init_app(self, app: Starlette) -> None:
        """Initializes the Starlette application with SQLAlchemy engine and sessionmaker.

        Sets up middleware and shutdown handlers for managing the database engine.

        Args:
            app (starlette.applications.Starlette): The Starlette application instance.
        """
        self._app = app
        unique_bind_keys = {config.bind_key for config in self.config}
        if len(unique_bind_keys) != len(self.config):  # pragma: no cover
            msg = "Please ensure that each config has a unique name for the `bind_key` attribute.  The default is `default` and can only be bound to a single engine."
            raise ImproperConfigurationError(msg)

        for config in self.config:
            config.init_app(app)

        app.state.advanced_alchemy = self

    @property
    def app(self) -> Starlette:
        """Returns the Starlette application instance.

        Raises:
            advanced_alchemy.exceptions.ImproperConfigurationError:
                If the application is not initialized.

        Returns:
            starlette.applications.Starlette: The Starlette application instance.
        """
        if self._app is None:
            msg = "Application not initialized. Did you forget to call init_app?"
            raise ImproperConfigurationError(msg)

        return self._app

    async def on_startup(self) -> None:  # pragma: no cover
        """Initializes the database."""
        for config in self.config:
            await config.on_startup()

    async def on_shutdown(self) -> None:  # pragma: no cover
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.

        Returns:
            None
        """
        for config in self.config:
            await config.on_shutdown()
        with contextlib.suppress(AttributeError, KeyError):
            delattr(self.app.state, "advanced_alchemy")

    def map_configs(self) -> dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]:  # noqa: UP007
        """Maps the configs to the session bind keys."""
        mapped_configs: dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = {}  # noqa: UP007
        for config in self.config:
            if config.bind_key is None:
                config.bind_key = "default"
            mapped_configs[config.bind_key] = config
        return mapped_configs

    def get_config(self, key: str | None = None) -> Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]:  # noqa: UP007
        """Get the config for the given key."""
        if key is None:
            key = "default"
        if key == "default" and len(self.config) == 1:
            key = self.config[0].bind_key or "default"
        config = self._mapped_configs.get(key)
        if config is None:
            msg = f"Config with key {key} not found"
            raise ImproperConfigurationError(msg)
        return config

    def get_async_config(self, key: str | None = None) -> SQLAlchemyAsyncConfig:
        """Get the async config for the given key."""
        config = self.get_config(key)
        if not isinstance(config, SQLAlchemyAsyncConfig):
            msg = "Expected an async config, but got a sync config"
            raise ImproperConfigurationError(msg)
        return config

    def get_sync_config(self, key: str | None = None) -> SQLAlchemySyncConfig:
        """Get the sync config for the given key."""
        config = self.get_config(key)
        if not isinstance(config, SQLAlchemySyncConfig):
            msg = "Expected a sync config, but got an async config"
            raise ImproperConfigurationError(msg)
        return config

    @asynccontextmanager
    async def with_async_session(self, key: str | None = None) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for getting an async session."""
        config = self.get_async_config(key)
        async with config.get_session() as session:
            yield session

    @contextmanager
    def with_sync_session(self, key: str | None = None) -> Generator[Session, None]:
        """Context manager for getting a sync session."""
        config = self.get_sync_config(key)
        with config.get_session() as session:
            yield session

    @overload
    @staticmethod
    def _get_session_from_request(request: Request, config: SQLAlchemyAsyncConfig) -> AsyncSession: ...

    @overload
    @staticmethod
    def _get_session_from_request(request: Request, config: SQLAlchemySyncConfig) -> Session: ...

    @staticmethod
    def _get_session_from_request(
        request: Request, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig
    ) -> Session | AsyncSession:  # pragma: no cover
        """Get the session for the given key."""
        session = getattr(request.state, config.session_key, None)
        if session is None:
            session = config.create_session_maker()()
            setattr(request.state, config.session_key, session)
        return session

    def get_session(self, request: Request, key: str | None = None) -> Session | AsyncSession:
        """Get the session for the given key."""
        config = self.get_config(key)
        return self._get_session_from_request(request, config)

    def get_async_session(self, request: Request, key: str | None = None) -> AsyncSession:
        """Get the async session for the given key."""
        config = self.get_async_config(key)
        return self._get_session_from_request(request, config)

    def get_sync_session(self, request: Request, key: str | None = None) -> Session:
        """Get the sync session for the given key."""
        config = self.get_sync_config(key)
        return self._get_session_from_request(request, config)

    def provide_session(self, key: str | None = None) -> Callable[[Request], Session | AsyncSession]:
        """Get the session for the given key."""
        config = self.get_config(key)

        def _get_session(request: Request) -> Session | AsyncSession:
            return self._get_session_from_request(request, config)

        return _get_session

    def provide_async_session(self, key: str | None = None) -> Callable[[Request], AsyncSession]:
        """Get the async session for the given key."""
        config = self.get_async_config(key)

        def _get_session(request: Request) -> AsyncSession:
            return self._get_session_from_request(request, config)

        return _get_session

    def provide_sync_session(self, key: str | None = None) -> Callable[[Request], Session]:
        """Get the sync session for the given key."""
        config = self.get_sync_config(key)

        def _get_session(request: Request) -> Session:
            return self._get_session_from_request(request, config)

        return _get_session

    def get_engine(self, key: str | None = None) -> Engine | AsyncEngine:  # pragma: no cover
        """Get the engine for the given key."""
        config = self.get_config(key)
        return config.get_engine()

    def get_async_engine(self, key: str | None = None) -> AsyncEngine:
        """Get the async engine for the given key."""
        config = self.get_async_config(key)
        return config.get_engine()

    def get_sync_engine(self, key: str | None = None) -> Engine:
        """Get the sync engine for the given key."""
        config = self.get_sync_config(key)
        return config.get_engine()

    def provide_engine(self, key: str | None = None) -> Callable[[], Engine | AsyncEngine]:  # pragma: no cover
        """Get the engine for the given key."""
        config = self.get_config(key)

        def _get_engine() -> Engine | AsyncEngine:
            return config.get_engine()

        return _get_engine

    def provide_async_engine(self, key: str | None = None) -> Callable[[], AsyncEngine]:  # pragma: no cover
        """Get the async engine for the given key."""
        config = self.get_async_config(key)

        def _get_engine() -> AsyncEngine:
            return config.get_engine()

        return _get_engine

    def provide_sync_engine(self, key: str | None = None) -> Callable[[], Engine]:  # pragma: no cover
        """Get the sync engine for the given key."""
        config = self.get_sync_config(key)

        def _get_engine() -> Engine:
            return config.get_engine()

        return _get_engine

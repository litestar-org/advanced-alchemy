# ruff: noqa: ARG001
import contextlib
from collections.abc import AsyncGenerator, Generator, Sequence
from contextlib import asynccontextmanager, contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    Union,
    cast,
    overload,
)

from starlette.requests import Request

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
        config: Union[
            SQLAlchemyAsyncConfig, SQLAlchemySyncConfig, Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]
        ],
        app: Optional["Starlette"] = None,
    ) -> None:
        self._config = config if isinstance(config, Sequence) else [config]
        self._mapped_configs: dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = self.map_configs()
        self._app = cast("Optional[Starlette]", None)

        if app is not None:
            self.init_app(app)

    @property
    def config(self) -> Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]:
        """Current Advanced Alchemy configuration."""

        return self._config

    def init_app(self, app: "Starlette") -> None:
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

        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def wrapped_lifespan(app: "Starlette") -> AsyncGenerator[Any, None]:  # pragma: no cover
            async with self.lifespan(app), original_lifespan(app) as state:
                yield state

        app.router.lifespan_context = wrapped_lifespan

    @asynccontextmanager
    async def lifespan(self, app: "Starlette") -> AsyncGenerator[Any, None]:  # pragma: no cover
        """Context manager for lifespan events.

        Args:
            app: The starlette application.

        Yields:
            None
        """
        await self.on_startup()
        try:
            yield
        finally:
            await self.on_shutdown()

    @property
    def app(self) -> "Starlette":  # pragma: no cover
        """Returns the Starlette application instance.

        Raises:
            advanced_alchemy.exceptions.ImproperConfigurationError:
                If the application is not initialized.

        Returns:
            starlette.applications.Starlette: The Starlette application instance.
        """
        if self._app is None:  # pragma: no cover
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

    def map_configs(self) -> dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]:
        """Maps the configs to the session bind keys."""
        mapped_configs: dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = {}
        for config in self.config:
            if config.bind_key is None:
                config.bind_key = "default"
            mapped_configs[config.bind_key] = config
        return mapped_configs

    def get_config(self, key: Optional[str] = None) -> Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]:
        """Get the config for the given key."""
        if key is None:
            key = "default"
        if key == "default" and len(self.config) == 1:
            key = self.config[0].bind_key or "default"
        config = self._mapped_configs.get(key)
        if config is None:  # pragma: no cover
            msg = f"Config with key {key} not found"
            raise ImproperConfigurationError(msg)
        return config

    def get_async_config(self, key: Optional[str] = None) -> SQLAlchemyAsyncConfig:
        """Get the async config for the given key."""
        config = self.get_config(key)
        if not isinstance(config, SQLAlchemyAsyncConfig):  # pragma: no cover
            msg = "Expected an async config, but got a sync config"
            raise ImproperConfigurationError(msg)
        return config

    def get_sync_config(self, key: Optional[str] = None) -> SQLAlchemySyncConfig:
        """Get the sync config for the given key."""
        config = self.get_config(key)
        if not isinstance(config, SQLAlchemySyncConfig):  # pragma: no cover
            msg = "Expected a sync config, but got an async config"
            raise ImproperConfigurationError(msg)
        return config

    @asynccontextmanager
    async def with_async_session(
        self, key: Optional[str] = None
    ) -> AsyncGenerator["AsyncSession", None]:  # pragma: no cover
        """Context manager for getting an async session."""
        config = self.get_async_config(key)
        async with config.get_session() as session:
            yield session

    @contextmanager
    def with_sync_session(self, key: Optional[str] = None) -> Generator["Session", None]:  # pragma: no cover
        """Context manager for getting a sync session."""
        config = self.get_sync_config(key)
        with config.get_session() as session:
            yield session

    @overload
    @staticmethod
    def _get_session_from_request(request: Request, config: SQLAlchemyAsyncConfig) -> "AsyncSession": ...

    @overload
    @staticmethod
    def _get_session_from_request(request: Request, config: SQLAlchemySyncConfig) -> "Session": ...

    @staticmethod
    def _get_session_from_request(
        request: Request,
        config: Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig],  # pragma: no cover
    ) -> Union["Session", "AsyncSession"]:  # pragma: no cover
        """Get the session for the given key."""
        session = getattr(request.state, config.session_key, None)
        if session is None:
            session = config.create_session_maker()()
            setattr(request.state, config.session_key, session)
        return session

    def get_session(
        self, request: Request, key: Optional[str] = None
    ) -> Union["Session", "AsyncSession"]:  # pragma: no cover
        """Get the session for the given key."""
        config = self.get_config(key)
        return self._get_session_from_request(request, config)

    def get_async_session(self, request: Request, key: Optional[str] = None) -> "AsyncSession":  # pragma: no cover
        """Get the async session for the given key."""
        config = self.get_async_config(key)
        return self._get_session_from_request(request, config)

    def get_sync_session(self, request: Request, key: Optional[str] = None) -> "Session":  # pragma: no cover
        """Get the sync session for the given key."""
        config = self.get_sync_config(key)
        return self._get_session_from_request(request, config)

    def provide_session(
        self, key: Optional[str] = None
    ) -> Callable[[Request], Union["Session", "AsyncSession"]]:  # pragma: no cover
        """Get the session for the given key."""
        config = self.get_config(key)

        def _get_session(request: Request) -> Union["Session", "AsyncSession"]:
            return self._get_session_from_request(request, config)

        return _get_session

    def provide_async_session(
        self, key: Optional[str] = None
    ) -> Callable[[Request], "AsyncSession"]:  # pragma: no cover
        """Get the async session for the given key."""
        config = self.get_async_config(key)

        def _get_session(request: Request) -> "AsyncSession":
            return self._get_session_from_request(request, config)

        return _get_session

    def provide_sync_session(self, key: Optional[str] = None) -> Callable[[Request], "Session"]:  # pragma: no cover
        """Get the sync session for the given key."""
        config = self.get_sync_config(key)

        def _get_session(request: Request) -> "Session":
            return self._get_session_from_request(request, config)

        return _get_session

    def get_engine(self, key: Optional[str] = None) -> Union["Engine", "AsyncEngine"]:  # pragma: no cover
        """Get the engine for the given key."""
        config = self.get_config(key)
        return config.get_engine()

    def get_async_engine(self, key: Optional[str] = None) -> "AsyncEngine":  # pragma: no cover
        """Get the async engine for the given key."""
        config = self.get_async_config(key)
        return config.get_engine()

    def get_sync_engine(self, key: Optional[str] = None) -> "Engine":  # pragma: no cover
        """Get the sync engine for the given key."""
        config = self.get_sync_config(key)
        return config.get_engine()

    def provide_engine(
        self, key: Optional[str] = None
    ) -> Callable[[], Union["Engine", "AsyncEngine"]]:  # pragma: no cover
        """Get the engine for the given key."""
        config = self.get_config(key)

        def _get_engine() -> Union["Engine", "AsyncEngine"]:
            return config.get_engine()

        return _get_engine

    def provide_async_engine(self, key: Optional[str] = None) -> Callable[[], "AsyncEngine"]:  # pragma: no cover
        """Get the async engine for the given key."""
        config = self.get_async_config(key)

        def _get_engine() -> "AsyncEngine":
            return config.get_engine()

        return _get_engine

    def provide_sync_engine(self, key: Optional[str] = None) -> Callable[[], "Engine"]:  # pragma: no cover
        """Get the sync engine for the given key."""
        config = self.get_sync_config(key)

        def _get_engine() -> "Engine":
            return config.get_engine()

        return _get_engine

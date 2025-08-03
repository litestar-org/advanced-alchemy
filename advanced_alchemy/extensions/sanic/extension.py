from collections.abc import AsyncGenerator, Generator, Sequence
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, cast, overload

from sanic import Request, Sanic

from advanced_alchemy.exceptions import ImproperConfigurationError, MissingDependencyError
from advanced_alchemy.extensions.sanic.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

try:
    from sanic_ext import Extend
    from sanic_ext.extensions.base import Extension

    SANIC_INSTALLED = True
except ModuleNotFoundError:  # pragma: no cover
    SANIC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]
    Extension = type("Extension", (), {})  # type: ignore
    Extend = type("Extend", (), {})  # type: ignore

if TYPE_CHECKING:
    from sanic import Sanic
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlalchemy.orm import Session


__all__ = ("AdvancedAlchemy",)


class AdvancedAlchemy(Extension):  # type: ignore[no-untyped-call]  # pyright: ignore[reportGeneralTypeIssues,reportUntypedBaseClass]
    """Sanic extension for integrating Advanced Alchemy with SQLAlchemy.

    Args:
        config: One or more configurations for SQLAlchemy.
        app: The Sanic application instance.
    """

    name = "AdvancedAlchemy"

    def __init__(
        self,
        *,
        sqlalchemy_config: Union[
            "SQLAlchemyAsyncConfig",
            "SQLAlchemySyncConfig",
            Sequence[Union["SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig"]],
        ],
        sanic_app: Optional["Sanic[Any, Any]"] = None,
    ) -> None:
        if not SANIC_INSTALLED:  # pragma: no cover
            msg = "Could not locate either Sanic or Sanic Extensions. Both libraries must be installed to use Advanced Alchemy. Try: pip install sanic[ext]"
            raise MissingDependencyError(msg)
        self._config = sqlalchemy_config if isinstance(sqlalchemy_config, Sequence) else [sqlalchemy_config]
        self._mapped_configs: dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = self.map_configs()
        self._app = sanic_app
        self._initialized = False
        if self._app is not None:
            self.register(self._app)

    def register(self, sanic_app: "Sanic[Any, Any]") -> None:
        """Initialize the extension with the given Sanic app."""
        self._app = sanic_app
        Extend.register(self)  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
        self._initialized = True

    @property
    def sanic_app(self) -> "Sanic[Any, Any]":
        """The Sanic app.

        Raises:
            ImproperConfigurationError: If the app is not initialized.
        """
        if self._app is None:  # pragma: no cover
            msg = "AdvancedAlchemy has not been initialized with a Sanic app."
            raise ImproperConfigurationError(msg)
        return self._app

    @property
    def sqlalchemy_config(self) -> Sequence[Union["SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig"]]:
        """Current Advanced Alchemy configuration."""

        return self._config

    def startup(self, bootstrap: "Extend") -> None:  # pyright: ignore[reportUnknownParameterType,reportInvalidTypeForm]
        """Advanced Alchemy Sanic extension startup hook.

        Args:
            bootstrap (sanic_ext.Extend): The Sanic extension bootstrap.
        """
        for config in self.sqlalchemy_config:
            config.init_app(self.sanic_app, bootstrap)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

    def map_configs(self) -> dict[str, Union["SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig"]]:
        """Maps the configs to the session bind keys.

        Returns:
            A dictionary mapping bind keys to SQLAlchemy configurations.
        """
        mapped_configs: dict[str, Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]] = {}
        for config in self.sqlalchemy_config:
            if config.bind_key is None:
                config.bind_key = "default"
            mapped_configs[config.bind_key] = config
        return mapped_configs

    def get_config(self, key: Optional[str] = None) -> Union["SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig"]:
        """Get the config for the given key.

        Returns:
            The config for the given key.

        Raises:
            ImproperConfigurationError: If the config is not found.
        """
        if key is None:
            key = "default"
        if key == "default" and len(self.sqlalchemy_config) == 1:
            key = self.sqlalchemy_config[0].bind_key or "default"
        config = self._mapped_configs.get(key)
        if config is None:  # pragma: no cover
            msg = f"Config with key {key} not found"
            raise ImproperConfigurationError(msg)
        return config

    def get_async_config(self, key: Optional[str] = None) -> "SQLAlchemyAsyncConfig":
        """Get the async config for the given key.

        Returns:
            The async config for the given key.

        Raises:
            ImproperConfigurationError: If the config is not an async config.
        """
        config = self.get_config(key)
        if not isinstance(config, SQLAlchemyAsyncConfig):  # pragma: no cover
            msg = "Expected an async config, but got a sync config"
            raise ImproperConfigurationError(msg)
        return config

    def get_sync_config(self, key: Optional[str] = None) -> "SQLAlchemySyncConfig":
        """Get the sync config for the given key.

        Returns:
            The sync config for the given key.

        Raises:
            ImproperConfigurationError: If the config is not an sync config.
        """
        config = self.get_config(key)
        if not isinstance(config, SQLAlchemySyncConfig):  # pragma: no cover
            msg = "Expected a sync config, but got an async config"
            raise ImproperConfigurationError(msg)
        return config

    @asynccontextmanager
    async def with_async_session(
        self, key: Optional[str] = None
    ) -> AsyncGenerator["AsyncSession", None]:  # pragma: no cover
        """Context manager for getting an async session.

        Yields:
            An AsyncSession instance.
        """
        config = self.get_async_config(key)
        async with config.get_session() as session:
            yield session

    @contextmanager
    def with_sync_session(self, key: Optional[str] = None) -> Generator["Session", None]:  # pragma: no cover
        """Context manager for getting a sync session.

        Yields:
            A Session instance.
        """
        config = self.get_sync_config(key)
        with config.get_session() as session:
            yield session

    @overload
    @staticmethod
    def _get_session_from_request(request: "Request", config: "SQLAlchemyAsyncConfig") -> "AsyncSession": ...

    @overload
    @staticmethod
    def _get_session_from_request(request: "Request", config: "SQLAlchemySyncConfig") -> "Session": ...

    @staticmethod
    def _get_session_from_request(
        request: "Request",
        config: Union["SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig"],  # pragma: no cover
    ) -> Union["Session", "AsyncSession"]:  # pragma: no cover
        """Get the session for the request and config.

        Returns:
            The session for the request and config.
        """
        session = getattr(request.ctx, config.session_key, None)
        if session is None:
            setattr(request.ctx, config.session_key, config.get_session())
        return cast("Union[Session, AsyncSession]", session)

    def get_session(
        self, request: "Request", key: Optional[str] = None
    ) -> Union["Session", "AsyncSession"]:  # pragma: no cover
        """Get the session for the given key.

        Returns:
            The session for the given key.
        """
        config = self.get_config(key)
        return self._get_session_from_request(request, config)

    def get_async_session(self, request: "Request", key: Optional[str] = None) -> "AsyncSession":  # pragma: no cover
        """Get the async session for the given key.

        Returns:
            The async session for the given key.
        """
        config = self.get_async_config(key)
        return self._get_session_from_request(request, config)

    def get_sync_session(self, request: "Request", key: Optional[str] = None) -> "Session":  # pragma: no cover
        """Get the sync session for the given key.

        Returns:
            The sync session for the given key.
        """
        config = self.get_sync_config(key)
        return self._get_session_from_request(request, config)

    def provide_session(
        self, key: Optional[str] = None
    ) -> Callable[["Request"], Union["Session", "AsyncSession"]]:  # pragma: no cover
        """Get session provider for the given key.

        Returns:
            The session provider for the given key.
        """
        config = self.get_config(key)

        def _get_session(request: "Request") -> Union["Session", "AsyncSession"]:
            return self._get_session_from_request(request, config)

        return _get_session

    def provide_async_session(
        self, key: Optional[str] = None
    ) -> Callable[["Request"], "AsyncSession"]:  # pragma: no cover
        """Get async session provider for the given key.

        Returns:
            The async session provider for the given key.
        """
        config = self.get_async_config(key)

        def _get_session(request: Request) -> "AsyncSession":
            return self._get_session_from_request(request, config)

        return _get_session

    def provide_sync_session(self, key: Optional[str] = None) -> Callable[[Request], "Session"]:  # pragma: no cover
        """Get sync session provider for the given key.

        Returns:
            The sync session provider for the given key.
        """
        config = self.get_sync_config(key)

        def _get_session(request: Request) -> "Session":
            return self._get_session_from_request(request, config)

        return _get_session

    def get_engine(self, key: Optional[str] = None) -> Union["Engine", "AsyncEngine"]:  # pragma: no cover
        """Get the engine for the given key.

        Returns:
            The engine for the given key.
        """
        config = self.get_config(key)
        return config.get_engine()

    def get_async_engine(self, key: Optional[str] = None) -> "AsyncEngine":  # pragma: no cover
        """Get the async engine for the given key.

        Returns:
            The async engine for the given key.
        """
        config = self.get_async_config(key)
        return config.get_engine()

    def get_sync_engine(self, key: Optional[str] = None) -> "Engine":  # pragma: no cover
        """Get the sync engine for the given key.

        Returns:
            The sync engine for the given key.
        """
        config = self.get_sync_config(key)
        return config.get_engine()

    def provide_engine(
        self, key: Optional[str] = None
    ) -> Callable[[], Union["Engine", "AsyncEngine"]]:  # pragma: no cover
        """Get the engine for the given key.

        Returns:
            A callable that returns the engine.
        """
        config = self.get_config(key)

        def _get_engine() -> Union["Engine", "AsyncEngine"]:
            return config.get_engine()

        return _get_engine

    def provide_async_engine(self, key: Optional[str] = None) -> Callable[[], "AsyncEngine"]:  # pragma: no cover
        """Get the async engine for the given key.

        Returns:
            A callable that returns the engine.
        """
        config = self.get_async_config(key)

        def _get_engine() -> "AsyncEngine":
            return config.get_engine()

        return _get_engine

    def provide_sync_engine(self, key: Optional[str] = None) -> Callable[[], "Engine"]:  # pragma: no cover
        """Get the sync engine for the given key.

        Returns:
            A callable that returns the engine.
        """
        config = self.get_sync_config(key)

        def _get_engine() -> "Engine":
            return config.get_engine()

        return _get_engine

    def add_session_dependency(
        self, session_type: type[Union["Session", "AsyncSession"]], key: Optional[str] = None
    ) -> None:
        """Add a session dependency to the Sanic app."""
        self.sanic_app.ext.add_dependency(session_type, self.provide_session(key))  # pyright: ignore[reportUnknownMemberType]

    def add_engine_dependency(
        self, engine_type: type[Union["Engine", "AsyncEngine"]], key: Optional[str] = None
    ) -> None:
        """Add an engine dependency to the Sanic app."""
        self.sanic_app.ext.add_dependency(engine_type, self.provide_engine(key))  # pyright: ignore[reportUnknownMemberType]

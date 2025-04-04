"""Configuration classes for Sanic integration.

This module provides configuration classes for integrating SQLAlchemy with Sanic applications,
including both synchronous and asynchronous database configurations.
"""

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, cast

from click import echo
from sanic import HTTPResponse, Request, Sanic
from sqlalchemy.exc import OperationalError

from advanced_alchemy.exceptions import ImproperConfigurationError

try:
    from sanic_ext import Extend

    SANIC_INSTALLED = True
except ModuleNotFoundError:  # pragma: no cover
    SANIC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]
    Extend = type("Extend", (), {})  # type: ignore

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker
from typing_extensions import Literal

from advanced_alchemy._listeners import set_async_context
from advanced_alchemy._serialization import decode_json, encode_json
from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import EngineConfig as _EngineConfig
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.service import schema_dump


def _make_unique_context_key(app: "Sanic[Any, Any]", key: str) -> str:  # pragma: no cover
    """Generates a unique context key for the Sanic application.

    Ensures that the key does not already exist in the application's state.

    Args:
        app (sanic.Sanic): The Sanic application instance.
        key (str): The base key name.

    Returns:
        str: A unique key name.
    """
    i = 0
    while True:
        if not hasattr(app.ctx, key):
            return key
        key = f"{key}_{i}"
        i += i


def serializer(value: Any) -> str:
    """Serialize JSON field values.

    Args:
        value: Any JSON serializable value.

    Returns:
        str: JSON string representation of the value.
    """
    return encode_json(schema_dump(value))


@dataclass
class EngineConfig(_EngineConfig):
    """Configuration for SQLAlchemy's Engine.

    This class extends the base EngineConfig with Sanic-specific JSON serialization options.

    For details see: https://docs.sqlalchemy.org/en/20/core/engines.html

    Attributes:
        json_deserializer: Callable for converting JSON strings to Python objects.
        json_serializer: Callable for converting Python objects to JSON strings.
    """

    json_deserializer: Callable[[str], Any] = decode_json
    """For dialects that support the :class:`~sqlalchemy.types.JSON` datatype, this is a Python callable that will
    convert a JSON string to a Python object.  But default, this uses the built-in serializers."""
    json_serializer: Callable[[Any], str] = serializer
    """For dialects that support the JSON datatype, this is a Python callable that will render a given object as JSON.
    By default, By default, the built-in serializer is used."""


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """SQLAlchemy Async config for Sanic."""

    _app: "Optional[Sanic[Any, Any]]" = None
    """The Sanic application instance."""
    commit_mode: Literal["manual", "autocommit", "autocommit_include_redirect"] = "manual"
    """The commit mode to use for database sessions."""
    engine_key: str = "db_engine"
    """Key to use for the dependency injection of database engines."""
    session_key: str = "db_session"
    """Key to use for the dependency injection of database sessions."""
    session_maker_key: str = "session_maker_class"
    """Key under which to store the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>` in the application state instance.
    """

    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """

    async def create_all_metadata(self) -> None:  # pragma: no cover
        """Create all metadata tables in the database."""
        if self.engine_instance is None:
            self.engine_instance = self.get_engine()
        async with self.engine_instance.begin() as conn:
            try:
                await conn.run_sync(
                    metadata_registry.get(None if self.bind_key == "default" else self.bind_key).create_all
                )
                await conn.commit()
            except OperationalError as exc:
                echo(f" * Could not create target metadata. Reason: {exc}")
            else:
                echo(" * Created target metadata.")

    @property
    def app(self) -> "Sanic[Any, Any]":
        """The Sanic application instance.

        Raises:
            ImproperConfigurationError: If the application is not initialized.
        """
        if self._app is None:
            msg = "The Sanic application instance is not set."
            raise ImproperConfigurationError(msg)
        return self._app

    def init_app(self, app: "Sanic[Any, Any]", bootstrap: "Extend") -> None:  # pyright: ignore[reportUnknownParameterType,reportInvalidTypeForm]
        """Initialize the Sanic application with this configuration.

        Args:
            app: The Sanic application instance.
            bootstrap: The Sanic extension bootstrap.
        """
        self._app = app
        self.bind_key = self.bind_key or "default"
        _ = self.create_session_maker()
        self.session_key = _make_unique_context_key(app, f"advanced_alchemy_async_session_{self.session_key}")
        self.engine_key = _make_unique_context_key(app, f"advanced_alchemy_async_engine_{self.engine_key}")
        self.session_maker_key = _make_unique_context_key(
            app, f"advanced_alchemy_async_session_maker_{self.session_maker_key}"
        )
        self.startup(bootstrap)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

    def startup(self, bootstrap: "Extend") -> None:  # pyright: ignore[reportUnknownParameterType,reportInvalidTypeForm]
        """Initialize the Sanic application with this configuration.

        Args:
            bootstrap: The Sanic extension bootstrap.
        """

        @self.app.before_server_start  # pyright: ignore[reportUnknownMemberType]
        async def on_startup(_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            setattr(self.app.ctx, self.engine_key, self.get_engine())  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            setattr(self.app.ctx, self.session_maker_key, self.create_session_maker())  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                AsyncEngine,
                self.get_engine_from_request,
            )
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                async_sessionmaker[AsyncSession],
                self.get_sessionmaker_from_request,
            )
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                AsyncSession,
                self.get_session_from_request,
            )
            await self.on_startup()

        @self.app.after_server_stop  # pyright: ignore[reportUnknownMemberType]
        async def on_shutdown(_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            if self.engine_instance is not None:
                await self.engine_instance.dispose()
            if hasattr(self.app.ctx, self.engine_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
                delattr(self.app.ctx, self.engine_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            if hasattr(self.app.ctx, self.session_maker_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
                delattr(self.app.ctx, self.session_maker_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]

        @self.app.middleware("request")  # pyright: ignore[reportUnknownMemberType]
        async def on_request(request: Request) -> None:  # pyright: ignore[reportUnusedFunction]
            session = cast("Optional[AsyncSession]", getattr(request.ctx, self.session_key, None))
            if session is None:
                setattr(request.ctx, self.session_key, self.get_session())
                set_async_context(True)

        @self.app.middleware("response")  # type: ignore[arg-type]
        async def on_response(request: Request, response: HTTPResponse) -> None:  # pyright: ignore[reportUnusedFunction]
            session = cast("Optional[AsyncSession]", getattr(request.ctx, self.session_key, None))
            if session is not None:
                await self.session_handler(session=session, request=request, response=response)

    async def on_startup(self) -> None:
        """Initialize the Sanic application with this configuration."""
        if self.create_all:
            await self.create_all_metadata()

    def create_session_maker(self) -> Callable[[], "AsyncSession"]:
        """Get a session maker. If none exists yet, create one.

        Returns:
            Callable[[], Session]: Session factory used by the plugin.
        """
        if self.session_maker:
            return self.session_maker

        session_kws = self.session_config_dict
        if self.engine_instance is None:
            self.engine_instance = self.get_engine()
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.engine_instance
        self.session_maker = self.session_maker_class(**session_kws)
        return self.session_maker

    async def session_handler(
        self, session: "AsyncSession", request: "Request", response: "HTTPResponse"
    ) -> None:  # pragma: no cover
        """Handles the session after a request is processed.

        Applies the commit strategy and ensures the session is closed.

        Args:
            session (sqlalchemy.ext.asyncio.AsyncSession):
                The database session.
            request (sanic.Request):
                The incoming HTTP request.
            response (sanic.HTTPResponse):
                The outgoing HTTP response.
        """
        try:
            if (self.commit_mode == "autocommit" and 200 <= response.status < 300) or (  # noqa: PLR2004
                self.commit_mode == "autocommit_include_redirect" and 200 <= response.status < 400  # noqa: PLR2004
            ):
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            with contextlib.suppress(AttributeError, KeyError):
                delattr(request.ctx, self.session_key)

    def get_engine_from_request(self, request: "Request") -> AsyncEngine:
        """Retrieve the engine from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            AsyncEngine: The SQLAlchemy engine.
        """
        return cast("AsyncEngine", getattr(request.app.ctx, self.engine_key, self.get_engine()))  # pragma: no cover

    def get_sessionmaker_from_request(self, request: "Request") -> async_sessionmaker[AsyncSession]:
        """Retrieve the session maker from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            SessionMakerT: The session maker.
        """
        return cast(
            "async_sessionmaker[AsyncSession]", getattr(request.app.ctx, self.session_maker_key, None)
        )  # pragma: no cover

    def get_session_from_request(self, request: Request) -> AsyncSession:
        """Retrieve the session from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            SessionT: The session associated with the request.
        """
        return cast("AsyncSession", getattr(request.ctx, self.session_key, None))  # pragma: no cover

    async def close_engine(self) -> None:  # pragma: no cover
        """Close the engine."""
        if self.engine_instance is not None:
            await self.engine_instance.dispose()

    async def on_shutdown(self) -> None:  # pragma: no cover
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.

        """
        await self.close_engine()
        if hasattr(self.app.ctx, self.engine_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            delattr(self.app.ctx, self.engine_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
        if hasattr(self.app.ctx, self.session_maker_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            delattr(self.app.ctx, self.session_maker_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """SQLAlchemy Sync config for Starlette."""

    _app: "Optional[Sanic[Any, Any]]" = None
    """The Sanic application instance."""
    commit_mode: Literal["manual", "autocommit", "autocommit_include_redirect"] = "manual"
    """The commit mode to use for database sessions."""
    engine_key: str = "db_engine"
    """Key to use for the dependency injection of database engines."""
    session_key: str = "db_session"
    """Key to use for the dependency injection of database sessions."""
    session_maker_key: str = "session_maker_class"
    """Key under which to store the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>` in the application state instance.
    """

    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """

    @property
    def app(self) -> "Sanic[Any, Any]":
        """The Sanic application instance.

        Raises:
            ImproperConfigurationError: If the application is not initialized.
        """
        if self._app is None:
            msg = "The Sanic application instance is not set."
            raise ImproperConfigurationError(msg)
        return self._app

    async def create_all_metadata(self) -> None:  # pragma: no cover
        """Create all metadata tables in the database."""
        if self.engine_instance is None:
            self.engine_instance = self.get_engine()
        with self.engine_instance.begin() as conn:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, metadata_registry.get(None if self.bind_key == "default" else self.bind_key).create_all, conn
                )
            except OperationalError as exc:
                echo(f" * Could not create target metadata. Reason: {exc}")

    def init_app(self, app: "Sanic[Any, Any]", bootstrap: "Extend") -> None:  # pyright: ignore[reportUnknownParameterType,reportInvalidTypeForm]
        """Initialize the Sanic application with this configuration.

        Args:
            app: The Sanic application instance.
            bootstrap: The Sanic extension bootstrap.
        """
        self._app = app
        self.bind_key = self.bind_key or "default"
        _ = self.create_session_maker()
        self.session_key = _make_unique_context_key(app, f"advanced_alchemy_sync_session_{self.session_key}")
        self.engine_key = _make_unique_context_key(app, f"advanced_alchemy_sync_engine_{self.engine_key}")
        self.session_maker_key = _make_unique_context_key(
            app, f"advanced_alchemy_sync_session_maker_{self.session_maker_key}"
        )
        self.startup(bootstrap)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

    def startup(self, bootstrap: "Extend") -> None:  # pyright: ignore[reportUnknownParameterType,reportInvalidTypeForm]
        """Initialize the Sanic application with this configuration.

        Args:
            bootstrap: The Sanic extension bootstrap.
        """

        @self.app.before_server_start  # pyright: ignore[reportUnknownMemberType]
        async def on_startup(_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            setattr(self.app.ctx, self.engine_key, self.get_engine())  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            setattr(self.app.ctx, self.session_maker_key, self.create_session_maker())  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                AsyncEngine,
                self.get_engine_from_request,
            )
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                sessionmaker[Session],
                self.get_sessionmaker_from_request,
            )
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                AsyncSession,
                self.get_session_from_request,
            )
            await self.on_startup()

        @self.app.after_server_stop  # pyright: ignore[reportUnknownMemberType]
        async def on_shutdown(_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            await self.on_shutdown()

        @self.app.middleware("request")  # pyright: ignore[reportUnknownMemberType]
        async def on_request(request: Request) -> None:  # pyright: ignore[reportUnusedFunction]
            session = cast("Optional[Session]", getattr(request.ctx, self.session_key, None))
            if session is None:
                setattr(request.ctx, self.session_key, self.get_session())
                set_async_context(False)

        @self.app.middleware("response")  # type: ignore[arg-type]
        async def on_response(request: Request, response: HTTPResponse) -> None:  # pyright: ignore[reportUnusedFunction]
            session = cast("Optional[Session]", getattr(request.ctx, self.session_key, None))
            if session is not None:
                await self.session_handler(session=session, request=request, response=response)

    async def on_startup(self) -> None:
        """Initialize the Sanic application with this configuration."""
        if self.create_all:
            await self.create_all_metadata()

    def create_session_maker(self) -> Callable[[], "Session"]:
        """Get a session maker. If none exists yet, create one.

        Returns:
            Callable[[], Session]: Session factory used by the plugin.
        """
        if self.session_maker:
            return self.session_maker

        session_kws = self.session_config_dict
        if self.engine_instance is None:
            self.engine_instance = self.get_engine()
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.engine_instance
        self.session_maker = self.session_maker_class(**session_kws)
        return self.session_maker

    async def session_handler(
        self, session: "Session", request: "Request", response: "HTTPResponse"
    ) -> None:  # pragma: no cover
        """Handles the session after a request is processed.

        Applies the commit strategy and ensures the session is closed.

        Args:
            session (sqlalchemy.orm.Session):
                The database session.
            request (sanic.Request):
                The incoming HTTP request.
            response (sanic.HTTPResponse):
                The outgoing HTTP response.
        """
        loop = asyncio.get_event_loop()
        try:
            if (self.commit_mode == "autocommit" and 200 <= response.status < 300) or (  # noqa: PLR2004
                self.commit_mode == "autocommit_include_redirect" and 200 <= response.status < 400  # noqa: PLR2004
            ):
                await loop.run_in_executor(None, session.commit)
            else:
                await loop.run_in_executor(None, session.rollback)
        finally:
            await loop.run_in_executor(None, session.close)
            with contextlib.suppress(AttributeError, KeyError):
                delattr(request.ctx, self.session_key)

    def get_engine_from_request(self, request: Request) -> "AsyncEngine":
        """Retrieve the engine from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            AsyncEngine: The SQLAlchemy engine.
        """
        return cast("AsyncEngine", getattr(request.app.ctx, self.engine_key, self.get_engine()))  # pragma: no cover

    def get_sessionmaker_from_request(self, request: Request) -> sessionmaker[Session]:
        """Retrieve the session maker from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            SessionMakerT: The session maker.
        """
        return cast("sessionmaker[Session]", getattr(request.app.ctx, self.session_maker_key, None))  # pragma: no cover

    def get_session_from_request(self, request: Request) -> "Session":
        """Retrieve the session from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            SessionT: The session associated with the request.
        """
        return cast("Session", getattr(request.ctx, self.session_key, None))  # pragma: no cover

    async def close_engine(self) -> None:  # pragma: no cover
        """Close the engine."""
        if self.engine_instance is not None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.engine_instance.dispose)

    async def on_shutdown(self) -> None:  # pragma: no cover
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.
        """
        await self.close_engine()
        if hasattr(self.app.ctx, self.engine_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            delattr(self.app.ctx, self.engine_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
        if hasattr(self.app.ctx, self.session_maker_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]
            delattr(self.app.ctx, self.session_maker_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportOptionalMemberAccess]

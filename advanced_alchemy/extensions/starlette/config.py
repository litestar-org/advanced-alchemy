"""Configuration classes for Starlette integration.

This module provides configuration classes for integrating SQLAlchemy with Starlette applications,
including both synchronous and asynchronous database configurations.
"""

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

from click import echo
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from typing_extensions import Literal

from advanced_alchemy._serialization import decode_json, encode_json
from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import EngineConfig as _EngineConfig
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.service import schema_dump

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session
    from starlette.applications import Starlette
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response


def _make_unique_state_key(app: "Starlette", key: str) -> str:  # pragma: no cover
    """Generates a unique state key for the Starlette application.

    Ensures that the key does not already exist in the application's state.

    Args:
        app (starlette.applications.Starlette): The Starlette application instance.
        key (str): The base key name.

    Returns:
        str: A unique key name.
    """
    i = 0
    while True:
        if not hasattr(app.state, key):
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

    This class extends the base EngineConfig with Starlette-specific JSON serialization options.

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
    """SQLAlchemy Async config for Starlette."""

    app: "Optional[Starlette]" = None
    """The Starlette application instance."""
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

    def init_app(self, app: "Starlette") -> None:
        """Initialize the Starlette application with this configuration.

        Args:
            app: The Starlette application instance.
        """
        self.app = app
        self.bind_key = self.bind_key or "default"
        _ = self.create_session_maker()
        self.session_key = _make_unique_state_key(app, f"advanced_alchemy_async_session_{self.session_key}")
        self.engine_key = _make_unique_state_key(app, f"advanced_alchemy_async_engine_{self.engine_key}")
        self.session_maker_key = _make_unique_state_key(
            app, f"advanced_alchemy_async_session_maker_{self.session_maker_key}"
        )

        app.add_middleware(BaseHTTPMiddleware, dispatch=self.middleware_dispatch)

    async def on_startup(self) -> None:
        """Initialize the Starlette application with this configuration."""
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
        self, session: "AsyncSession", request: "Request", response: "Response"
    ) -> None:  # pragma: no cover
        """Handles the session after a request is processed.

        Applies the commit strategy and ensures the session is closed.

        Args:
            session (sqlalchemy.ext.asyncio.AsyncSession):
                The database session.
            request (starlette.requests.Request):
                The incoming HTTP request.
            response (starlette.responses.Response):
                The outgoing HTTP response.

        Returns:
            None
        """
        try:
            if (self.commit_mode == "autocommit" and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                self.commit_mode == "autocommit_include_redirect" and 200 <= response.status_code < 400  # noqa: PLR2004
            ):
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            with contextlib.suppress(AttributeError, KeyError):
                delattr(request.state, self.session_key)

    async def middleware_dispatch(
        self, request: "Request", call_next: "RequestResponseEndpoint"
    ) -> "Response":  # pragma: no cover
        """Middleware dispatch function to handle requests and responses.

        Processes the request, invokes the next middleware or route handler, and
        applies the session handler after the response is generated.

        Args:
            request (starlette.requests.Request): The incoming HTTP request.
            call_next (starlette.middleware.base.RequestResponseEndpoint):
                The next middleware or route handler.

        Returns:
            starlette.responses.Response: The HTTP response.
        """
        response = await call_next(request)
        session = cast("Optional[AsyncSession]", getattr(request.state, self.session_key, None))
        if session is not None:
            await self.session_handler(session=session, request=request, response=response)

        return response

    async def close_engine(self) -> None:  # pragma: no cover
        """Close the engine."""
        if self.engine_instance is not None:
            await self.engine_instance.dispose()

    async def on_shutdown(self) -> None:  # pragma: no cover
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.

        Returns:
            None
        """
        await self.close_engine()
        if self.app is not None:
            with contextlib.suppress(AttributeError, KeyError):
                delattr(self.app.state, self.engine_key)
                delattr(self.app.state, self.session_maker_key)
                delattr(self.app.state, self.session_key)


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """SQLAlchemy Sync config for Starlette."""

    app: "Optional[Starlette]" = None
    """The Starlette application instance."""
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
        with self.engine_instance.begin() as conn:
            try:
                await run_in_threadpool(
                    metadata_registry.get(None if self.bind_key == "default" else self.bind_key).create_all, conn
                )
            except OperationalError as exc:
                echo(f" * Could not create target metadata. Reason: {exc}")

    def init_app(self, app: "Starlette") -> None:
        """Initialize the Starlette application with this configuration.

        Args:
            app: The Starlette application instance.
        """
        self.app = app
        self.bind_key = self.bind_key or "default"
        self.session_key = _make_unique_state_key(app, f"advanced_alchemy_sync_session_{self.session_key}")
        self.engine_key = _make_unique_state_key(app, f"advanced_alchemy_sync_engine_{self.engine_key}")
        self.session_maker_key = _make_unique_state_key(
            app, f"advanced_alchemy_sync_session_maker_{self.session_maker_key}"
        )
        _ = self.create_session_maker()
        app.add_middleware(BaseHTTPMiddleware, dispatch=self.middleware_dispatch)

    async def on_startup(self) -> None:
        """Initialize the Starlette application with this configuration."""
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
        self, session: "Session", request: "Request", response: "Response"
    ) -> None:  # pragma: no cover
        """Handles the session after a request is processed.

        Applies the commit strategy and ensures the session is closed.

        Args:
            session (sqlalchemy.orm.Session | sqlalchemy.ext.asyncio.AsyncSession):
                The database session.
            request (starlette.requests.Request):
                The incoming HTTP request.
            response (starlette.responses.Response):
                The outgoing HTTP response.

        Returns:
            None
        """
        try:
            if (self.commit_mode == "autocommit" and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                self.commit_mode == "autocommit_include_redirect" and 200 <= response.status_code < 400  # noqa: PLR2004
            ):
                await run_in_threadpool(session.commit)
            else:
                await run_in_threadpool(session.rollback)
        finally:
            await run_in_threadpool(session.close)
            with contextlib.suppress(AttributeError, KeyError):
                delattr(request.state, self.session_key)

    async def middleware_dispatch(
        self, request: "Request", call_next: "RequestResponseEndpoint"
    ) -> "Response":  # pragma: no cover
        """Middleware dispatch function to handle requests and responses.

        Processes the request, invokes the next middleware or route handler, and
        applies the session handler after the response is generated.

        Args:
            request (starlette.requests.Request): The incoming HTTP request.
            call_next (starlette.middleware.base.RequestResponseEndpoint):
                The next middleware or route handler.

        Returns:
            starlette.responses.Response: The HTTP response.
        """
        response = await call_next(request)
        session = cast("Optional[Session]", getattr(request.state, self.session_key, None))
        if session is not None:
            await self.session_handler(session=session, request=request, response=response)

        return response

    async def close_engine(self) -> None:  # pragma: no cover
        """Close the engines."""
        if self.engine_instance is not None:
            await run_in_threadpool(self.engine_instance.dispose)

    async def on_shutdown(self) -> None:  # pragma: no cover
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.

        Returns:
            None
        """
        await self.close_engine()
        if self.app is not None:
            with contextlib.suppress(AttributeError, KeyError):
                delattr(self.app.state, self.engine_key)
                delattr(self.app.state, self.session_maker_key)
                delattr(self.app.state, self.session_key)

"""Configuration classes for Starlette integration.

This module provides configuration classes for integrating SQLAlchemy with Starlette applications,
including both synchronous and asynchronous database configurations.
"""

import contextlib
import logging
from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, cast

from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool  # pyright: ignore[reportUnknownVariableType]
from starlette.requests import Request
from typing_extensions import Literal

from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import EngineConfig as _EngineConfig
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.routing.context import reset_routing_context
from advanced_alchemy.routing.maker import dispose_session_maker_async, dispose_session_maker_sync
from advanced_alchemy.utils.serialization import decode_json, encode_json, schema_dump

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session
    from starlette.applications import Starlette
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.responses import Response
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("advanced_alchemy.extensions.starlette")


FASTAPI_CLI_INSTALLED = bool(find_spec("fastapi_cli"))


def _echo(message: str) -> None:  # pragma: no cover
    """Echo a message using either rich toolkit or click echo."""
    if FASTAPI_CLI_INSTALLED:
        from fastapi_cli.utils.cli import get_rich_toolkit

        with get_rich_toolkit() as toolkit:
            toolkit.print(message, tag="INFO")
    else:
        from click import echo

        echo(message)


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


class SessionMiddleware:
    """Pure ASGI middleware for database session lifecycle management.

    Unlike BaseHTTPMiddleware, this intercepts the ``send`` callable directly to capture
    the response status code at the moment it is sent. This ensures ``response_status``
    is available on ``request.state`` before generator dependency cleanup runs, and avoids
    known Starlette issues with BaseHTTPMiddleware and generator dependencies.
    """

    def __init__(self, app: "ASGIApp", config: Union["SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig"]) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        reset_routing_context()

        status_code = 500
        response_started = False

        async def send_wrapper(message: Any) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                setattr(request.state, f"{self.config.session_key}_response_status", status_code)
            await send(message)

        exc_to_raise: Optional[BaseException] = None
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001
            exc_to_raise = exc
            if not response_started:
                setattr(request.state, f"{self.config.session_key}_response_status", 500)
        finally:
            session = getattr(request.state, self.config.session_key, None)
            is_generator_managed = getattr(request.state, f"{self.config.session_key}_generator_managed", False)
            if session is not None and not is_generator_managed:
                await self._handle_session_cleanup(session, request, status_code)

        if exc_to_raise is not None:
            raise exc_to_raise

    async def _handle_session_cleanup(
        self, session: Any, request: "Request", status_code: int
    ) -> None:  # pragma: no cover
        """Clean up a non-generator-managed session after the response."""
        config = self.config
        should_commit = (config.commit_mode == "autocommit" and 200 <= status_code < 300) or (  # noqa: PLR2004
            config.commit_mode == "autocommit_include_redirect" and 200 <= status_code < 400  # noqa: PLR2004
        )
        try:
            if isinstance(config, SQLAlchemyAsyncConfig):
                if should_commit:
                    await session.commit()
                else:
                    await session.rollback()
            elif should_commit:
                await run_in_threadpool(session.commit)
            else:
                await run_in_threadpool(session.rollback)
        except Exception:  # noqa: BLE001
            logger.debug("Session commit/rollback failed during middleware cleanup", exc_info=True)
        finally:
            try:
                if isinstance(config, SQLAlchemyAsyncConfig):
                    await session.close()
                else:
                    await run_in_threadpool(session.close)
            except Exception:  # noqa: BLE001
                logger.debug("Session close failed during middleware cleanup", exc_info=True)
            with contextlib.suppress(AttributeError, KeyError):
                delattr(request.state, config.session_key)


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
class AppStateKeys:
    """Keys for storing engine, session, and session maker in application/request state.

    Attributes:
        engine_key: Key to use for the dependency injection of database engines.
        session_key: Key to use for the dependency injection of database sessions.
        session_maker_key: Key under which to store the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>`
            in the application state instance.
    """

    engine_key: str = "db_engine"
    """Key to use for the dependency injection of database engines."""
    session_key: str = "db_session"
    """Key to use for the dependency injection of database sessions."""
    session_maker_key: str = "session_maker_class"
    """Key under which to store the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>` in the application state instance.
    """


@dataclass
class StarletteSessionConfig:
    """Starlette-specific session configuration.

    Attributes:
        app: The Starlette application instance.
        commit_mode: The commit mode to use for database sessions.
    """

    app: "Optional[Starlette]" = field(default=None, repr=False)
    """The Starlette application instance."""
    commit_mode: Literal["manual", "autocommit", "autocommit_include_redirect"] = "manual"
    """The commit mode to use for database sessions."""


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """SQLAlchemy Async config for Starlette."""

    starlette_session_config: StarletteSessionConfig = field(default_factory=StarletteSessionConfig)
    """Configuration for Starlette-specific session settings."""
    key_config: AppStateKeys = field(default_factory=AppStateKeys)
    """Configuration for engine, session, and session maker state keys."""

    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """

    @property
    def app(self) -> "Starlette":
        """The Starlette application instance.

        Raises:
            ImproperConfigurationError: If the application is not initialized.
        """
        if self.starlette_session_config.app is None:
            from advanced_alchemy.exceptions import ImproperConfigurationError

            msg = "Application not initialized. Did you forget to call init_app?"
            raise ImproperConfigurationError(msg)
        return self.starlette_session_config.app

    @app.setter
    def app(self, value: "Optional[Starlette]") -> None:
        self.starlette_session_config.app = value

    # -- Backward-compatible property accessors for starlette_session_config --

    @property
    def _app(self) -> "Optional[Starlette]":
        """The Starlette application instance."""
        return self.starlette_session_config.app

    @_app.setter
    def _app(self, value: "Optional[Starlette]") -> None:
        self.starlette_session_config.app = value

    @property
    def commit_mode(self) -> Literal["manual", "autocommit", "autocommit_include_redirect"]:
        """The commit mode to use for database sessions."""
        return self.starlette_session_config.commit_mode

    @commit_mode.setter
    def commit_mode(self, value: Literal["manual", "autocommit", "autocommit_include_redirect"]) -> None:
        self.starlette_session_config.commit_mode = value

    # -- Backward-compatible property accessors for key_config --

    @property
    def engine_key(self) -> str:
        """Key to use for the dependency injection of database engines."""
        return self.key_config.engine_key

    @engine_key.setter
    def engine_key(self, value: str) -> None:
        self.key_config.engine_key = value

    @property
    def session_key(self) -> str:
        """Key to use for the dependency injection of database sessions."""
        return self.key_config.session_key

    @session_key.setter
    def session_key(self, value: str) -> None:
        self.key_config.session_key = value

    @property
    def session_maker_key(self) -> str:
        """Key under which to store the SQLAlchemy sessionmaker in the application state."""
        return self.key_config.session_maker_key

    @session_maker_key.setter
    def session_maker_key(self, value: str) -> None:
        self.key_config.session_maker_key = value

    async def create_all_metadata(self) -> None:  # pragma: no cover
        """Create all metadata tables in the database."""
        if self.connection_config.engine_instance is None:
            self.connection_config.engine_instance = self.get_engine()
        async with self.connection_config.engine_instance.begin() as conn:
            try:
                await conn.run_sync(
                    metadata_registry.get(
                        None if self.metadata_config.bind_key == "default" else self.metadata_config.bind_key
                    ).create_all
                )
                await conn.commit()
            except OperationalError as exc:
                _echo(f" * Could not create target metadata. Reason: {exc}")
            else:
                _echo(" * Created target metadata.")

    def init_app(self, app: "Starlette") -> None:
        """Initialize the Starlette application with this configuration.

        Args:
            app: The Starlette application instance.
        """
        self.starlette_session_config.app = app
        self.metadata_config.bind_key = self.metadata_config.bind_key or "default"
        _ = self.create_session_maker()
        self.key_config.session_key = _make_unique_state_key(
            app, f"advanced_alchemy_async_session_{self.key_config.session_key}"
        )
        self.key_config.engine_key = _make_unique_state_key(
            app, f"advanced_alchemy_async_engine_{self.key_config.engine_key}"
        )
        self.key_config.session_maker_key = _make_unique_state_key(
            app, f"advanced_alchemy_async_session_maker_{self.key_config.session_maker_key}"
        )

        app.add_middleware(SessionMiddleware, config=self)  # pyright: ignore[reportUnknownMemberType]

    async def on_startup(self) -> None:
        """Initialize the Starlette application with this configuration."""
        if self.metadata_config.create_all:
            await self.create_all_metadata()

    def create_session_maker(self) -> Callable[[], "AsyncSession"]:
        """Get a session maker. If none exists yet, create one.

        Preserves ``engine_instance`` caching and then delegates to the
        base-class implementation so configured session listeners for file
        objects, timestamps, and cache invalidation are registered.

        Returns:
            Callable[[], Session]: Session factory used by the plugin.
        """
        if self.session_factory_config.session_maker:
            return self.session_factory_config.session_maker
        if self.connection_config.engine_instance is None:
            self.connection_config.engine_instance = self.get_engine()
        return super().create_session_maker()

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
        """
        try:
            if (self.commit_mode == "autocommit" and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                self.commit_mode == "autocommit_include_redirect" and 200 <= response.status_code < 400  # noqa: PLR2004
            ):
                await session.commit()
            else:
                await session.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Session commit/rollback failed during cleanup", exc_info=True)
        finally:
            try:
                await session.close()
            except Exception:  # noqa: BLE001
                logger.debug("Session close failed during cleanup", exc_info=True)
            with contextlib.suppress(AttributeError, KeyError):
                delattr(request.state, self.session_key)

    async def middleware_dispatch(
        self, request: "Request", call_next: "RequestResponseEndpoint"
    ) -> "Response":  # pragma: no cover
        """Middleware dispatch function to handle requests and responses.

        Processes the request, invokes the next middleware or route handler, and
        applies the session handler after the response is generated.

        For generator-managed sessions (e.g., from provide_service()), the middleware
        stores the response status but skips cleanup, allowing the generator to handle
        commit/rollback/close operations properly.

        Args:
            request (starlette.requests.Request): The incoming HTTP request.
            call_next (starlette.middleware.base.RequestResponseEndpoint):
                The next middleware or route handler.

        Returns:
            starlette.responses.Response: The HTTP response.
        """
        # Reset routing context for request-scoped isolation
        reset_routing_context()

        response = await call_next(request)

        # Store response status for generator dependencies to access during cleanup
        setattr(request.state, f"{self.session_key}_response_status", response.status_code)

        session = cast("Optional[AsyncSession]", getattr(request.state, self.session_key, None))

        # Check if session is managed by a generator dependency (e.g., provide_service)
        is_generator_managed = getattr(request.state, f"{self.session_key}_generator_managed", False)

        if session is not None and not is_generator_managed:
            # Only handle cleanup for non-generator-managed sessions
            await self.session_handler(session=session, request=request, response=response)

        return response

    async def close_engine(self) -> None:  # pragma: no cover
        """Close the engine."""
        if self.connection_config.engine_instance is not None:
            await self.connection_config.engine_instance.dispose()
        await dispose_session_maker_async(self.session_factory_config.session_maker)

    async def on_shutdown(self) -> None:  # pragma: no cover
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.
        """
        await self.close_engine()
        if self.starlette_session_config.app is not None:
            with contextlib.suppress(AttributeError, KeyError):
                delattr(self.starlette_session_config.app.state, self.engine_key)
                delattr(self.starlette_session_config.app.state, self.session_maker_key)
                delattr(self.starlette_session_config.app.state, self.session_key)


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """SQLAlchemy Sync config for Starlette."""

    starlette_session_config: StarletteSessionConfig = field(default_factory=StarletteSessionConfig)
    """Configuration for Starlette-specific session settings."""
    key_config: AppStateKeys = field(default_factory=AppStateKeys)
    """Configuration for engine, session, and session maker state keys."""

    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """

    @property
    def app(self) -> "Starlette":
        """The Starlette application instance.

        Raises:
            ImproperConfigurationError: If the application is not initialized.
        """
        if self.starlette_session_config.app is None:
            from advanced_alchemy.exceptions import ImproperConfigurationError

            msg = "Application not initialized. Did you forget to call init_app?"
            raise ImproperConfigurationError(msg)
        return self.starlette_session_config.app

    @app.setter
    def app(self, value: "Optional[Starlette]") -> None:
        self.starlette_session_config.app = value

    # -- Backward-compatible property accessors for starlette_session_config --

    @property
    def _app(self) -> "Optional[Starlette]":
        """The Starlette application instance."""
        return self.starlette_session_config.app

    @_app.setter
    def _app(self, value: "Optional[Starlette]") -> None:
        self.starlette_session_config.app = value

    @property
    def commit_mode(self) -> Literal["manual", "autocommit", "autocommit_include_redirect"]:
        """The commit mode to use for database sessions."""
        return self.starlette_session_config.commit_mode

    @commit_mode.setter
    def commit_mode(self, value: Literal["manual", "autocommit", "autocommit_include_redirect"]) -> None:
        self.starlette_session_config.commit_mode = value

    # -- Backward-compatible property accessors for key_config --

    @property
    def engine_key(self) -> str:
        """Key to use for the dependency injection of database engines."""
        return self.key_config.engine_key

    @engine_key.setter
    def engine_key(self, value: str) -> None:
        self.key_config.engine_key = value

    @property
    def session_key(self) -> str:
        """Key to use for the dependency injection of database sessions."""
        return self.key_config.session_key

    @session_key.setter
    def session_key(self, value: str) -> None:
        self.key_config.session_key = value

    @property
    def session_maker_key(self) -> str:
        """Key under which to store the SQLAlchemy sessionmaker in the application state."""
        return self.key_config.session_maker_key

    @session_maker_key.setter
    def session_maker_key(self, value: str) -> None:
        self.key_config.session_maker_key = value

    async def create_all_metadata(self) -> None:  # pragma: no cover
        """Create all metadata tables in the database."""
        if self.connection_config.engine_instance is None:
            self.connection_config.engine_instance = self.get_engine()
        with self.connection_config.engine_instance.begin() as conn:
            try:
                await run_in_threadpool(
                    lambda: metadata_registry.get(
                        None if self.metadata_config.bind_key == "default" else self.metadata_config.bind_key
                    ).create_all(conn)
                )
            except OperationalError as exc:
                _echo(f" * Could not create target metadata. Reason: {exc}")

    def init_app(self, app: "Starlette") -> None:
        """Initialize the Starlette application with this configuration.

        Args:
            app: The Starlette application instance.
        """
        self.starlette_session_config.app = app
        self.metadata_config.bind_key = self.metadata_config.bind_key or "default"
        self.key_config.session_key = _make_unique_state_key(
            app, f"advanced_alchemy_sync_session_{self.key_config.session_key}"
        )
        self.key_config.engine_key = _make_unique_state_key(
            app, f"advanced_alchemy_sync_engine_{self.key_config.engine_key}"
        )
        self.key_config.session_maker_key = _make_unique_state_key(
            app, f"advanced_alchemy_sync_session_maker_{self.key_config.session_maker_key}"
        )
        _ = self.create_session_maker()
        app.add_middleware(SessionMiddleware, config=self)  # pyright: ignore[reportUnknownMemberType]

    async def on_startup(self) -> None:
        """Initialize the Starlette application with this configuration."""
        if self.metadata_config.create_all:
            await self.create_all_metadata()

    def create_session_maker(self) -> Callable[[], "Session"]:
        """Get a session maker. If none exists yet, create one.

        Preserves ``engine_instance`` caching and then delegates to the
        base-class implementation so configured session listeners are
        registered.

        Returns:
            Callable[[], Session]: Session factory used by the plugin.
        """
        if self.session_factory_config.session_maker:
            return self.session_factory_config.session_maker
        if self.connection_config.engine_instance is None:
            self.connection_config.engine_instance = self.get_engine()
        return super().create_session_maker()

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
        """
        try:
            if (self.commit_mode == "autocommit" and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                self.commit_mode == "autocommit_include_redirect" and 200 <= response.status_code < 400  # noqa: PLR2004
            ):
                await run_in_threadpool(session.commit)
            else:
                await run_in_threadpool(session.rollback)
        except Exception:  # noqa: BLE001
            logger.debug("Session commit/rollback failed during cleanup", exc_info=True)
        finally:
            try:
                await run_in_threadpool(session.close)
            except Exception:  # noqa: BLE001
                logger.debug("Session close failed during cleanup", exc_info=True)
            with contextlib.suppress(AttributeError, KeyError):
                delattr(request.state, self.session_key)

    async def middleware_dispatch(
        self, request: "Request", call_next: "RequestResponseEndpoint"
    ) -> "Response":  # pragma: no cover
        """Middleware dispatch function to handle requests and responses.

        Processes the request, invokes the next middleware or route handler, and
        applies the session handler after the response is generated.

        For generator-managed sessions (e.g., from provide_service()), the middleware
        stores the response status but skips cleanup, allowing the generator to handle
        commit/rollback/close operations properly.

        Args:
            request (starlette.requests.Request): The incoming HTTP request.
            call_next (starlette.middleware.base.RequestResponseEndpoint):
                The next middleware or route handler.

        Returns:
            starlette.responses.Response: The HTTP response.
        """
        # Reset routing context for request-scoped isolation
        reset_routing_context()

        response = await call_next(request)

        # Store response status for generator dependencies to access during cleanup
        setattr(request.state, f"{self.session_key}_response_status", response.status_code)

        session = cast("Optional[Session]", getattr(request.state, self.session_key, None))

        # Check if session is managed by a generator dependency (e.g., provide_service)
        is_generator_managed = getattr(request.state, f"{self.session_key}_generator_managed", False)

        if session is not None and not is_generator_managed:
            # Only handle cleanup for non-generator-managed sessions
            await self.session_handler(session=session, request=request, response=response)

        return response

    async def close_engine(self) -> None:  # pragma: no cover
        """Close the engines."""
        if self.connection_config.engine_instance is not None:
            await run_in_threadpool(self.connection_config.engine_instance.dispose)
        await run_in_threadpool(lambda: dispose_session_maker_sync(self.session_factory_config.session_maker))

    async def on_shutdown(self) -> None:  # pragma: no cover
        """Handles the shutdown event by disposing of the SQLAlchemy engine.

        Ensures that all connections are properly closed during application shutdown.
        """
        await self.close_engine()
        if self.starlette_session_config.app is not None:
            with contextlib.suppress(AttributeError, KeyError):
                delattr(self.starlette_session_config.app.state, self.engine_key)
                delattr(self.starlette_session_config.app.state, self.session_maker_key)
                delattr(self.starlette_session_config.app.state, self.session_key)

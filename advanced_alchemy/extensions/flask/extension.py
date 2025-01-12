"""Flask extension for Advanced Alchemy."""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Generator, Sequence, Union, cast

from flask import g

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask.cli import database_group
from advanced_alchemy.extensions.flask.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.flask.portal import PortalProvider

if TYPE_CHECKING:
    from flask import Flask
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    from advanced_alchemy.extensions.flask.portal import (
        GreenletBlockingPortal as BlockingPortal,
    )


# Global portal provider


def run_global_event_loop(portal_provider: PortalProvider) -> None:
    """Run the asyncio event loop in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    portal_provider.portal._loop = loop  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    portal_provider.portal._active_tasks = set()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    _loop_thread_ready.set()

    try:
        loop.run_forever()
    finally:
        if portal_provider.portal._active_tasks:  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            for task in portal_provider.portal._active_tasks:  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                task.cancel()
            loop.run_until_complete(
                asyncio.gather(*portal_provider.portal._active_tasks, return_exceptions=True)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            )
        loop.close()


GLOBAL_PORTAL_PROVIDER: PortalProvider = PortalProvider()
_loop_thread: threading.Thread | None = None
_loop_thread_ready = threading.Event()
_loop_stop_event = threading.Event()


class AdvancedAlchemy:
    """Flask extension for Advanced Alchemy.

    This extension provides integration between Flask and Advanced Alchemy, including:
    - Async and sync session management
    - Database migration commands via Click
    - Automatic async/sync session handling
    - Support for multiple database bindings
    """

    __slots__ = (
        "_config",
        "_has_async_config",
        "_loop_stop_event",
        "_loop_thread",
        "_loop_thread_ready",
        "_session_makers",
        "portal_provider",
    )

    def __init__(
        self,
        config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig | Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig],
        app: Flask | None = None,
        *,
        portal_provider: PortalProvider | None = None,
    ) -> None:
        """Initialize the extension.

        Args:
            config: SQLAlchemy configuration(s) for the extension
            app: Optional Flask application instance
            portal_provider: Optional custom blocking portal provider
        """
        self.portal_provider = portal_provider if portal_provider is not None else GLOBAL_PORTAL_PROVIDER
        self._config = config if isinstance(config, Sequence) else [config]
        self._has_async_config = any(isinstance(c, SQLAlchemyAsyncConfig) for c in self.config)
        self._session_makers: dict[str, Callable[..., Union[AsyncSession, Session]]] = {}  # noqa: UP007
        if app is not None:
            self.init_app(app)

    @property
    def config(self) -> Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig]:
        """Get the SQLAlchemy configuration(s).

        Returns:
            The configured SQLAlchemy configuration(s)
        """
        return self._config

    @contextmanager
    def with_portal(self) -> Generator[BlockingPortal | None, None, None]:
        """Context manager for using the portal."""
        if self._has_async_config:
            if not _loop_thread_ready.is_set():
                msg = "Background event loop is not running."
                raise RuntimeError(msg)
            with self.portal_provider as portal:
                yield portal
        else:
            yield None

    def init_app(self, app: Flask) -> None:
        """Initialize the Flask application.

        Args:
            app: The Flask app instance to initialize.

        Raises:
            ImproperConfigurationError: If this extension is already registered on the given Flask instance.
        """
        if "advanced_alchemy" in app.extensions:
            msg = "Advanced Alchemy extension is already registered on this Flask application."
            raise ImproperConfigurationError(msg)

        if self._has_async_config:
            # Start the background event loop thread
            global _loop_thread  # noqa: PLW0603
            _loop_thread = threading.Thread(
                target=run_global_event_loop,
                kwargs={"portal_provider": self.portal_provider},
                daemon=True,
            )
            _loop_thread.start()
            _loop_thread_ready.wait()  # Wait for the loop to be ready

        # Initialize each config with the app if it's a Flask config
        for config in self.config:
            config.init_app(app, self.portal_provider.portal)
            # Register session maker
            bind_key = config.bind_key if config.bind_key is not None else "default"
            session_maker = config.create_session_maker()
            self._session_makers[bind_key] = session_maker

        app.extensions["advanced_alchemy"] = self
        app.cli.add_command(database_group)

    def _create_session_maker_with_connection_callback(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig,
    ) -> Callable[..., Union[AsyncSession, Session]]:  # noqa: UP007
        """Create a session maker with a connection callback to set the `_session_portal` attribute."""
        session_maker = config.create_session_maker()

        def get_session_with_portal(*args: Any, **kwargs: Any) -> AsyncSession | Session:
            session = session_maker(*args, **kwargs)
            setattr(session, "_session_portal", self.portal_provider.portal)  # pyright: ignore[reportPrivateUsage]
            return session

        return get_session_with_portal

    def get_session(self, bind_key: str = "default") -> Session | AsyncSession:
        """Get a new session from the configured session factory.

        Args:
            bind_key: Optional bind key to specify which database to use

        Returns:
            A new SQLAlchemy session
        """
        # If no bind key is specified and there is only one config, use its bind key
        if bind_key == "default" and len(self.config) == 1:
            bind_key = self.config[0].bind_key if self.config[0].bind_key is not None else "default"

        if g.get(f"advanced_alchemy_session_{bind_key}") is not None:
            return cast("Union[AsyncSession, Session]", g.get(f"advanced_alchemy_session_{bind_key}"))
        session_maker = self._session_makers.get(bind_key)
        if session_maker is None:
            msg = f'No session maker found for bind key "{bind_key}"'
            raise ValueError(msg)
        session = session_maker()
        if self._has_async_config:
            setattr(session, "_session_portal", self.portal_provider.portal)  # pyright: ignore[reportPrivateUsage]
        g.setdefault(f"advanced_alchemy_session_{bind_key}", session)
        return session

    @property
    def is_async_enabled(self) -> bool:
        """Return True if any of the database configs are async."""
        return self._has_async_config

    def __del__(self) -> None:
        """Stop the event loop thread."""
        if _loop_thread is not None and _loop_thread.is_alive():
            _loop_stop_event.set()
            _loop_thread.join()

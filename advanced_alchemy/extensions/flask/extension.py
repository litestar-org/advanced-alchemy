# ruff: noqa: SLF001, ARG001
"""Flask extension for Advanced Alchemy."""

from collections.abc import Generator, Sequence
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Callable, Optional, Union, cast

from flask import g
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask.cli import database_group
from advanced_alchemy.extensions.flask.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.utils.portals import PortalProvider

if TYPE_CHECKING:
    from flask import Flask


class AdvancedAlchemy:
    """Flask extension for Advanced Alchemy."""

    __slots__ = (
        "_config",
        "_has_async_config",
        "_session_makers",
        "portal_provider",
    )

    def __init__(
        self,
        config: "Union[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig, Sequence[Union[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig]]]",
        app: "Optional[Flask]" = None,
        *,
        portal_provider: "Optional[PortalProvider]" = None,
    ) -> None:
        """Initialize the extension."""
        self.portal_provider = portal_provider if portal_provider is not None else PortalProvider()
        self._config = config if isinstance(config, Sequence) else [config]
        self._has_async_config = any(isinstance(c, SQLAlchemyAsyncConfig) for c in self.config)
        self._session_makers: dict[str, Callable[..., Union[AsyncSession, Session]]] = {}

        if app is not None:
            self.init_app(app)

    @property
    def config(self) -> "Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]":
        """Get the SQLAlchemy configuration(s)."""
        return self._config

    @property
    def is_async_enabled(self) -> bool:
        """Return True if any of the database configs are async."""
        return self._has_async_config

    def init_app(self, app: "Flask") -> None:
        """Initialize the Flask application.

        Args:
            app: The Flask application to initialize.

        Raises:
            ImproperConfigurationError: If the extension is already registered on the Flask application.
        """
        if "advanced_alchemy" in app.extensions:
            msg = "Advanced Alchemy extension is already registered on this Flask application."
            raise ImproperConfigurationError(msg)

        if self._has_async_config:
            self.portal_provider.start()

            # Create tables for async configs
            for cfg in self._config:
                if isinstance(cfg, SQLAlchemyAsyncConfig):
                    self.portal_provider.portal.call(cfg.create_all_metadata)

            # Register shutdown handler for the portal
            @app.teardown_appcontext
            def shutdown_portal(exception: "Optional[BaseException]" = None) -> None:  # pyright: ignore[reportUnusedFunction]
                """Stop the portal when the application shuts down."""
                if not app.debug:  # Don't stop portal in debug mode
                    with suppress(Exception):
                        self.portal_provider.stop()

        # Initialize each config with the app
        for config in self.config:
            config.init_app(app, self.portal_provider.portal)
            bind_key = config.bind_key if config.bind_key is not None else "default"
            session_maker = config.create_session_maker()
            self._session_makers[bind_key] = session_maker

        # Register session cleanup only
        app.teardown_appcontext(self._teardown_appcontext)

        app.extensions["advanced_alchemy"] = self
        app.cli.add_command(database_group)

    def _teardown_appcontext(self, exception: "Optional[BaseException]" = None) -> None:
        """Clean up resources when the application context ends."""
        for key in list(g):
            if key.startswith("advanced_alchemy_session_"):
                session = getattr(g, key)
                if isinstance(session, AsyncSession):
                    # Close async sessions through the portal
                    with suppress(ImproperConfigurationError):
                        self.portal_provider.portal.call(session.close)
                else:
                    session.close()
                delattr(g, key)

    def get_session(self, bind_key: str = "default") -> "Union[AsyncSession, Session]":
        """Get a new session from the configured session factory.

        Args:
            bind_key: The bind key to use for the session.

        Returns:
            A new session from the configured session factory.

        Raises:
            ImproperConfigurationError: If no session maker is found for the bind key.
        """
        if bind_key == "default" and len(self.config) == 1:
            bind_key = self.config[0].bind_key if self.config[0].bind_key is not None else "default"

        session_key = f"advanced_alchemy_session_{bind_key}"
        if hasattr(g, session_key):
            return cast("Union[AsyncSession, Session]", getattr(g, session_key))

        session_maker = self._session_makers.get(bind_key)
        if session_maker is None:
            msg = f'No session maker found for bind key "{bind_key}"'
            raise ImproperConfigurationError(msg)

        session = session_maker()
        if self._has_async_config:
            # Ensure portal is started
            if not self.portal_provider.is_running:
                self.portal_provider.start()
            setattr(session, "_session_portal", self.portal_provider.portal)
        setattr(g, session_key, session)
        return session

    def get_async_session(self, bind_key: str = "default") -> AsyncSession:
        """Get an async session from the configured session factory."""
        session = self.get_session(bind_key)
        if not isinstance(session, AsyncSession):
            msg = f"Expected async session for bind key {bind_key}, but got {type(session)}"
            raise ImproperConfigurationError(msg)
        return session

    def get_sync_session(self, bind_key: str = "default") -> Session:
        """Get a sync session from the configured session factory."""
        session = self.get_session(bind_key)
        if not isinstance(session, Session):
            msg = f"Expected sync session for bind key {bind_key}, but got {type(session)}"
            raise ImproperConfigurationError(msg)
        return session

    @contextmanager
    def with_session(  # pragma: no cover (more on this later)
        self, bind_key: str = "default"
    ) -> "Generator[Union[AsyncSession, Session], None, None]":
        """Provide a transactional scope around a series of operations.

        Args:
            bind_key: The bind key to use for the session.

        Yields:
            A session.
        """
        session = self.get_session(bind_key)
        try:
            yield session
        finally:
            if isinstance(session, AsyncSession):
                with suppress(ImproperConfigurationError):
                    self.portal_provider.portal.call(session.close)
            else:
                session.close()

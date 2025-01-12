"""Flask extension for Advanced Alchemy."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator, Sequence

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask.cli import database_group
from advanced_alchemy.extensions.flask.config import SQLAlchemyAsyncConfig

if TYPE_CHECKING:
    from flask import Flask
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlalchemy.orm import Session

    from advanced_alchemy.extensions.flask.config import SQLAlchemySyncConfig


class AdvancedAlchemy:
    """Flask extension for Advanced Alchemy.

    This extension provides integration between Flask and Advanced Alchemy, including:
    - Async and sync session management
    - Database migration commands via Click
    - Automatic async/sync session handling
    - Support for multiple database bindings
    """

    __slots__ = ("_config", "_has_async_config", "_portal_provider")

    def __init__(
        self,
        config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig | Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig],
        app: Flask | None = None,
    ) -> None:
        """Initialize the extension.

        Args:
            config: SQLAlchemy configuration(s) for the extension
            app: Optional Flask application instance
        """
        self._config: Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig] = (
            [config] if not isinstance(config, Sequence) else config
        )
        self._has_async_config = any(isinstance(cfg, SQLAlchemyAsyncConfig) for cfg in self._config)
        if app is not None:
            self.init_app(app)

    @property
    def config(self) -> Sequence[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig]:
        """Get the SQLAlchemy configuration(s).

        Returns:
            The configured SQLAlchemy configuration(s)
        """
        return self._config

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

        # Initialize each config with the app if it's a Flask config
        for config in self.config:
            if config.app is None:
                config.app = app

        app.extensions["advanced_alchemy"] = self
        app.cli.add_command(database_group)

    def get_session(self, bind_key: str | None = None) -> Any:
        """Get a new session from the configured session factory.

        Args:
            bind_key: Optional bind key to specify which database to use

        Returns:
            A new SQLAlchemy session
        """
        for config in self.config:
            if config.bind_key == bind_key:
                return config.get_session()
        return self.config[0].get_session()

    def get_engine(self, bind_key: str | None = None) -> Engine | AsyncEngine:
        """Get the SQLAlchemy engine.

        Args:
            bind_key: Optional bind key to specify which database to use

        Returns:
            The configured SQLAlchemy engine
        """
        for config in self.config:
            if config.bind_key == bind_key:
                return config.get_engine()
        return self.config[0].get_engine()

    @property
    def is_async_enabled(self) -> bool:
        """Return True if any of the database configs are async."""
        return self._has_async_config

    def get_db(self, key: str | None = None) -> Any:
        """Retrieve a session using the provided key.

        Args:
            key: Optional key to specify which database session to retrieve.

        Returns:
            A SQLAlchemy session corresponding to the key.
        """
        return self.get_session(bind_key=key)

    @contextmanager
    def session(self, bind_key: str | None = None) -> Iterator[Session]:
        """Get a synchronous session context manager.

        Args:
            bind_key: Optional bind key to specify which database to use.

        Returns:
            A context manager yielding a SQLAlchemy session.

        Example:
            ```python
            with alchemy.session() as session:
                user = session.get(User, 1)
                session.add(user)
                session.commit()
            ```
        """
        session = self.get_session(bind_key)
        if isawaitable(session):
            msg = f"Session for bind key {bind_key} is not an sync session"
            raise ImproperConfigurationError(msg)
        with session as session:
            try:
                yield session
            except Exception as e:
                session.rollback()
                raise e from e
            finally:
                session.close()

    @asynccontextmanager
    async def async_session(self, bind_key: str | None = None) -> AsyncIterator[AsyncSession]:
        """Get an asynchronous session context manager.

        Args:
            bind_key: Optional bind key to specify which database to use.

        Returns:
            An async context manager yielding a SQLAlchemy async session.

        Example:
            ```python
            async with alchemy.async_session() as session:
                user = await session.get(User, 1)
                session.add(user)
                await session.commit()
            ```

        Raises:
            ImproperConfigurationError: If the session is not an async session.
        """
        session = self.get_session(bind_key)
        if not isawaitable(session):
            msg = f"Session for bind key {bind_key} is not an async session"
            raise ImproperConfigurationError(msg)
        async with await session as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                raise e from e
            finally:
                await session.close()

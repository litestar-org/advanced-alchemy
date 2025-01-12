from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from litestar.cli._utils import console
from litestar.serialization import decode_json, encode_json
from sqlalchemy.exc import OperationalError

from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import EngineConfig as _EngineConfig
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig

if TYPE_CHECKING:
    from typing import Any

    from flask import Flask, Response
    from litestar.datastructures.state import State
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlalchemy.orm import Session


__all__ = ("CommitMode", "EngineConfig", "SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig")


class CommitMode(str, Enum):
    """Commit mode for database sessions."""

    DEFAULT = "default"
    """Default mode - no automatic commit."""
    AUTOCOMMIT = "autocommit"
    """Automatically commit on successful response."""
    AUTOCOMMIT_WITH_REDIRECT = "autocommit_with_redirect"
    """Automatically commit on successful response, including redirects."""


def should_commit_response(response: Response, commit_mode: CommitMode) -> bool:
    """Determine if a response should trigger a commit based on commit mode.

    Args:
        response: The Flask response object.
        commit_mode: The commit mode to use.

    Returns:
        bool: Whether the response should trigger a commit.
    """
    if commit_mode == CommitMode.DEFAULT:
        return False

    if commit_mode == CommitMode.AUTOCOMMIT_WITH_REDIRECT:
        return 200 <= response.status_code < 400  # noqa: PLR2004

    return 200 <= response.status_code < 300  # noqa: PLR2004


def serializer(value: Any) -> str:
    """Serialize JSON field values.

    Args:
        value: Any json serializable value.

    Returns:
        JSON string.
    """
    return encode_json(value).decode("utf-8")


@dataclass
class EngineConfig(_EngineConfig):
    """Configuration for SQLAlchemy's :class:`Engine <sqlalchemy.engine.Engine>`.

    For details see: https://docs.sqlalchemy.org/en/20/core/engines.html
    """

    json_deserializer: Callable[[str], Any] = decode_json
    """For dialects that support the :class:`JSON <sqlalchemy.types.JSON>` datatype, this is a Python callable that will
    convert a JSON string to a Python object. By default, this is set to Litestar's decode_json function."""
    json_serializer: Callable[[Any], str] = serializer
    """For dialects that support the JSON datatype, this is a Python callable that will render a given object as JSON.
    By default, Litestar's encode_json function is used."""


"""Flask-specific synchronous SQLAlchemy configuration."""


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """Flask-specific synchronous SQLAlchemy configuration."""

    app: Flask | None = None
    """The Flask application instance."""
    commit_mode: CommitMode = field(default=CommitMode.DEFAULT)
    """The commit mode to use for database sessions."""

    def init_app(self, app: Flask) -> None:
        """Initialize the Flask application with this configuration.

        Args:
            app: The Flask application instance.
        """
        self.app = app
        if self.commit_mode != CommitMode.DEFAULT:
            self._setup_commit_middleware(app)

    def _setup_commit_middleware(self, app: Flask) -> None:
        """Set up the commit middleware for the Flask application.

        Args:
            app: The Flask application instance.
        """
        session_factory = self.create_session_factory()

        @app.after_request
        def commit_session(response: Response) -> Response:  # pyright: ignore[reportUnusedFunction]
            """Commit the session if the response meets the commit criteria."""
            if should_commit_response(response, self.commit_mode):
                session = session_factory()
                try:
                    session.commit()
                finally:
                    session.close()
            return response

    def create_session_maker(self) -> Callable[[], Session]:
        """Get a session maker. If none exists yet, create one.

        Returns:
            Session factory used by the plugin.
        """
        if self.session_maker:
            return self.session_maker

        session_kws = self.session_config_dict
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.get_engine()
        self.session_maker = self.session_maker_class(**session_kws)
        return self.session_maker

    def provide_engine(self) -> Engine:
        """Create the SQLAlchemy sync engine.

        Returns:
            Engine: The configured SQLAlchemy sync engine
        """
        engine = self.get_engine()
        if self.app is not None:
            self.app.extensions[f"advanced_alchemy_engine_{self.bind_key}"] = engine
        return engine

    def create_session_factory(self) -> Callable[[], Session]:
        """Create the SQLAlchemy sync session factory.

        Returns:
            sessionmaker[Session]: The configured SQLAlchemy sync session factory
        """
        session_factory = self.create_session_maker()
        if self.app is not None:
            self.app.extensions[f"advanced_alchemy_session_{self.bind_key}"] = session_factory
        return session_factory

    def create_all_metadata(self) -> None:
        """Create all metadata"""
        with self.get_engine().begin() as conn:
            try:
                metadata_registry.get(self.bind_key).create_all(conn)
            except OperationalError as exc:
                console.print(f"[bold red] * Could not create target metadata.  Reason: {exc}")


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """Flask-specific asynchronous SQLAlchemy configuration."""

    app: Flask | None = None
    """The Flask application instance."""
    commit_mode: CommitMode = field(default=CommitMode.DEFAULT)
    """The commit mode to use for database sessions."""

    def init_app(self, app: Flask) -> None:
        """Initialize the Flask application with this configuration.

        Args:
            app: The Flask application instance.
        """
        self.app = app
        if self.commit_mode != CommitMode.DEFAULT:
            self._setup_commit_middleware(app)

    def _setup_commit_middleware(self, app: Flask) -> None:
        """Set up the commit middleware for the Flask application.

        Args:
            app: The Flask application instance.
        """
        session_factory = self.create_session_factory()

        @app.after_request
        async def commit_session(response: Response) -> Response:  # pyright: ignore[reportUnusedFunction]
            """Commit the session if the response meets the commit criteria."""
            if should_commit_response(response, self.commit_mode):
                session = session_factory()
                try:
                    await session.commit()
                finally:
                    await session.close()
            return response

    def create_session_maker(self) -> Callable[[], AsyncSession]:
        """Get a session maker. If none exists yet, create one.

        Returns:
            Session factory used by the plugin.
        """
        if self.session_maker:
            return self.session_maker

        session_kws = self.session_config_dict
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.get_engine()
        self.session_maker = self.session_maker_class(**session_kws)
        return self.session_maker

    def provide_engine(self, state: State) -> AsyncEngine:
        """Create an engine instance.

        Args:
            state: The ``Litestar.state`` instance.

        Returns:
            An engine instance.
        """
        engine = self.get_engine()
        if self.app is not None:
            self.app.extensions[f"advanced_alchemy_engine_{self.bind_key}"] = engine
        return engine

    def create_session_factory(self) -> Callable[[], AsyncSession]:
        """Create the SQLAlchemy async session factory.

        Returns:
            sessionmaker[AsyncSession]: The configured SQLAlchemy async session factory
        """
        session_factory = self.create_session_maker()
        if self.app is not None:
            self.app.extensions[f"advanced_alchemy_session_{self.bind_key}"] = session_factory
        return session_factory

    async def create_all_metadata(self) -> None:
        """Create all metadata"""
        async with self.get_engine().begin() as conn:
            try:
                await conn.run_sync(metadata_registry.get(self.bind_key).create_all)
            except OperationalError as exc:
                console.print(f"[bold red] * Could not create target metadata.  Reason: {exc}")

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

from flask import g, has_request_context
from litestar.cli._utils import console
from litestar.serialization import decode_json, encode_json
from sqlalchemy.exc import OperationalError

from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import EngineConfig as _EngineConfig
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from typing import Any

    from anyio.from_thread import BlockingPortal
    from flask import Flask, Response
    from sqlalchemy.ext.asyncio import AsyncSession
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

    def init_app(self, app: Flask, portal: BlockingPortal | None = None) -> None:
        """Initialize the Flask application with this configuration.

        Args:
            app: The Flask application instance.
            portal: The portal to use for thread-safe communication. Unused in synchronous configurations, but here for
                consistent API.
        """
        self.app = app
        self.bind_key = self.bind_key or "default"
        if self.create_all:
            self.create_all_metadata()
        if self.commit_mode != CommitMode.DEFAULT:
            self._setup_session_handling(app)

    def _setup_session_handling(self, app: Flask) -> None:
        """Set up the session handling for the Flask application.

        Args:
            app: The Flask application instance.
        """

        @app.after_request
        def handle_db_session(response: Response) -> Response:  # pyright: ignore[reportUnusedFunction]
            """Commit the session if the response meets the commit criteria."""
            if not has_request_context():
                return response

            db_session = cast("Optional[Session]", g.pop(f"advanced_alchemy_session_{self.bind_key}", None))
            if db_session is not None:
                if (self.commit_mode == CommitMode.AUTOCOMMIT and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                    self.commit_mode == CommitMode.AUTOCOMMIT_WITH_REDIRECT and 200 <= response.status_code < 400  # noqa: PLR2004
                ):
                    db_session.commit()
                db_session.close()
            return response

    def create_all_metadata(self) -> None:
        """Create all metadata"""
        with self.get_engine().begin() as conn:
            try:
                metadata_registry.get(self.bind_key).create_all(conn)
            except OperationalError as exc:
                console.print(f"[bold red] * Could not create target metadata. Reason: {exc}")


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """Flask-specific asynchronous SQLAlchemy configuration."""

    app: Flask | None = None
    """The Flask application instance."""
    commit_mode: CommitMode = field(default=CommitMode.DEFAULT)
    """The commit mode to use for database sessions."""

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

    def init_app(self, app: Flask, portal: BlockingPortal | None = None) -> None:
        """Initialize the Flask application with this configuration.

        Args:
            app: The Flask application instance.
            portal: The portal to use for thread-safe communication.
        """
        self.app = app
        self.bind_key = self.bind_key or "default"
        if portal is None:
            msg = "Portal is required for asynchronous configurations"
            raise ImproperConfigurationError(msg)
        if self.create_all:
            portal.call(self.create_all_metadata)
        if self.commit_mode != CommitMode.DEFAULT:
            self._setup_session_handling(app, portal)

    def _setup_session_handling(self, app: Flask, portal: BlockingPortal) -> None:
        """Set up the session handling for the Flask application.

        Args:
            app: The Flask application instance.
            portal: The portal to use for thread-safe communication.
        """

        @app.after_request
        def handle_db_session(response: Response) -> Response:  # pyright: ignore[reportUnusedFunction]
            """Commit the session if the response meets the commit criteria."""
            if not has_request_context():
                return response

            db_session = cast("Optional[AsyncSession]", g.pop(f"advanced_alchemy_session_{self.bind_key}", None))
            if db_session is not None:
                if (self.commit_mode == CommitMode.AUTOCOMMIT and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                    self.commit_mode == CommitMode.AUTOCOMMIT_WITH_REDIRECT and 200 <= response.status_code < 400  # noqa: PLR2004
                ):
                    portal.call(db_session.commit)
                portal.call(db_session.close)
            return response

    async def create_all_metadata(self) -> None:
        """Create all metadata"""
        async with self.get_engine().begin() as conn:
            try:
                await conn.run_sync(metadata_registry.get(self.bind_key).create_all)
            except OperationalError as exc:
                console.print(f"[bold red] * Could not create target metadata. Reason: {exc}")

"""Configuration classes for Flask integration.

This module provides configuration classes for integrating SQLAlchemy with Flask applications,
including both synchronous and asynchronous database configurations.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, Union, cast

from click import echo
from flask import g, has_request_context
from sqlalchemy.exc import OperationalError
from typing_extensions import Literal

from advanced_alchemy._serialization import decode_json, encode_json
from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config import EngineConfig as _EngineConfig
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.service import schema_dump

if TYPE_CHECKING:
    from flask import Flask, Response
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    from advanced_alchemy.utils.portals import Portal

__all__ = ("EngineConfig", "SQLAlchemyAsyncConfig", "SQLAlchemySyncConfig")

ConfigT = TypeVar("ConfigT", bound="Union[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig]")


def serializer(value: "Any") -> str:
    """Serialize JSON field values.

    Calls the `:func:schema_dump` function to convert the value to a built-in before encoding.

    Args:
        value: Any JSON serializable value.

    Returns:
        str: JSON string representation of the value.
    """

    return encode_json(schema_dump(value))


@dataclass
class EngineConfig(_EngineConfig):
    """Configuration for SQLAlchemy's Engine.

    This class extends the base EngineConfig with Flask-specific JSON serialization options.

    For details see: https://docs.sqlalchemy.org/en/20/core/engines.html

    Attributes:
        json_deserializer: Callable for converting JSON strings to Python objects.
        json_serializer: Callable for converting Python objects to JSON strings.
    """

    json_deserializer: "Callable[[str], Any]" = decode_json
    """For dialects that support the :class:`~sqlalchemy.types.JSON` datatype, this is a Python callable that will
    convert a JSON string to a Python object."""
    json_serializer: "Callable[[Any], str]" = serializer
    """For dialects that support the JSON datatype, this is a Python callable that will render a given object as JSON."""


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """Flask-specific synchronous SQLAlchemy configuration.

    Attributes:
        app: The Flask application instance.
        commit_mode: The commit mode to use for database sessions.
    """

    app: "Optional[Flask]" = None
    """The Flask application instance."""
    commit_mode: Literal["manual", "autocommit", "autocommit_include_redirect"] = "manual"
    """The commit mode to use for database sessions."""

    def create_session_maker(self) -> "Callable[[], Session]":
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

    def init_app(self, app: "Flask", portal: "Optional[Portal]" = None) -> None:
        """Initialize the Flask application with this configuration.

        Args:
            app: The Flask application instance.
            portal: The portal to use for thread-safe communication. Unused in synchronous configurations.
        """
        self.app = app
        self.bind_key = self.bind_key or "default"
        if self.create_all:
            self.create_all_metadata()
        if self.commit_mode != "manual":
            self._setup_session_handling(app)

    def _setup_session_handling(self, app: "Flask") -> None:
        """Set up the session handling for the Flask application.

        Args:
            app: The Flask application instance.
        """

        @app.after_request
        def handle_db_session(response: "Response") -> "Response":  # pyright: ignore[reportUnusedFunction]
            """Commit the session if the response meets the commit criteria."""
            if not has_request_context():
                return response

            db_session = cast("Optional[Session]", g.pop(f"advanced_alchemy_session_{self.bind_key}", None))
            if db_session is not None:
                if (self.commit_mode == "autocommit" and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                    self.commit_mode == "autocommit_include_redirect" and 200 <= response.status_code < 400  # noqa: PLR2004
                ):
                    db_session.commit()
                db_session.close()
            return response

    def close_engines(self, portal: "Portal") -> None:
        """Close the engines.

        Args:
            portal: The portal to use for thread-safe communication.
        """
        if self.engine_instance is not None:
            self.engine_instance.dispose()

    def create_all_metadata(self) -> None:  # pragma: no cover
        """Create all metadata tables in the database."""
        if self.engine_instance is None:
            self.engine_instance = self.get_engine()
        with self.engine_instance.begin() as conn:
            try:
                metadata_registry.get(None if self.bind_key == "default" else self.bind_key).create_all(conn)
            except OperationalError as exc:
                echo(f" * Could not create target metadata. Reason: {exc}")
            else:
                echo(" * Created target metadata.")


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """Flask-specific asynchronous SQLAlchemy configuration.

    Attributes:
        app: The Flask application instance.
        commit_mode: The commit mode to use for database sessions.
    """

    app: "Optional[Flask]" = None
    """The Flask application instance."""
    commit_mode: Literal["manual", "autocommit", "autocommit_include_redirect"] = "manual"
    """The commit mode to use for database sessions."""

    def create_session_maker(self) -> "Callable[[], AsyncSession]":
        """Get a session maker. If none exists yet, create one.

        Returns:
            Callable[[], AsyncSession]: Session factory used by the plugin.
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

    def init_app(self, app: "Flask", portal: "Optional[Portal]" = None) -> None:
        """Initialize the Flask application with this configuration.

        Args:
            app: The Flask application instance.
            portal: The portal to use for thread-safe communication.

        Raises:
            ImproperConfigurationError: If portal is not provided for async configuration.
        """
        self.app = app
        self.bind_key = self.bind_key or "default"
        if portal is None:
            msg = "Portal is required for asynchronous configurations"
            raise ImproperConfigurationError(msg)
        if self.create_all:
            _ = portal.call(self.create_all_metadata)
        self._setup_session_handling(app, portal)

    def _setup_session_handling(self, app: "Flask", portal: "Portal") -> None:
        """Set up the session handling for the Flask application.

        Args:
            app: The Flask application instance.
            portal: The portal to use for thread-safe communication.
        """

        @app.after_request
        def handle_db_session(response: "Response") -> "Response":  # pyright: ignore[reportUnusedFunction]
            """Commit the session if the response meets the commit criteria."""
            if not has_request_context():
                return response

            db_session = cast("Optional[AsyncSession]", g.pop(f"advanced_alchemy_session_{self.bind_key}", None))
            if db_session is not None:
                p = getattr(db_session, "_session_portal", None) or portal
                if (self.commit_mode == "autocommit" and 200 <= response.status_code < 300) or (  # noqa: PLR2004
                    self.commit_mode == "autocommit_include_redirect" and 200 <= response.status_code < 400  # noqa: PLR2004
                ):
                    _ = p.call(db_session.commit)
                _ = p.call(db_session.close)
            return response

        @app.teardown_appcontext
        def close_db_session(_: "Optional[BaseException]" = None) -> None:  # pyright: ignore[reportUnusedFunction]
            """Close the session at the end of the request."""
            db_session = cast("Optional[AsyncSession]", g.pop(f"advanced_alchemy_session_{self.bind_key}", None))
            if db_session is not None:
                p = getattr(db_session, "_session_portal", None) or portal
                _ = p.call(db_session.close)

    def close_engines(self, portal: "Portal") -> None:
        """Close the engines.

        Args:
            portal: The portal to use for thread-safe communication.
        """
        if self.engine_instance is not None:
            _ = portal.call(self.engine_instance.dispose)

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

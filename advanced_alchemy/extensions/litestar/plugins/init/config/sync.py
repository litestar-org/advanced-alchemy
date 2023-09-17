from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, cast

from litestar.constants import HTTP_RESPONSE_START
from litestar.status_codes import HTTP_200_OK, HTTP_300_MULTIPLE_CHOICES
from litestar.utils import delete_litestar_scope_state, get_litestar_scope_state, set_litestar_scope_state
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.common import (
    SESSION_SCOPE_KEY,
    SESSION_TERMINUS_ASGI_EVENTS,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.engine import EngineConfig

if TYPE_CHECKING:
    from typing import Any

    from litestar import Litestar
    from litestar.datastructures.state import State
    from litestar.types import BeforeMessageSendHookHandler, Message, Scope
    from litestar.types.asgi_types import HTTPResponseStartEvent


__all__ = (
    "SQLAlchemySyncConfig",
    "default_before_send_handler",
    "autocommit_before_send_handler",
)


def default_before_send_handler(message: Message, scope: Scope) -> None:
    """Handle closing and cleaning up sessions before sending.

    Args:
        message: ASGI-``Message``
        scope: An ASGI-``Scope``

    Returns:
        None
    """
    session = cast("Session | None", get_litestar_scope_state(scope, SESSION_SCOPE_KEY))
    if session and message["type"] in SESSION_TERMINUS_ASGI_EVENTS:
        session.close()
        delete_litestar_scope_state(scope, SESSION_SCOPE_KEY)


def autocommit_before_send_handler(message: Message, scope: Scope) -> None:
    """Handle commit/rollback, closing and cleaning up sessions before sending.

    Args:
        message: ASGI-``Message``
        scope: An ASGI-``Scope``

    Returns:
        None
    """
    session = cast("Session | None", get_litestar_scope_state(scope, SESSION_SCOPE_KEY))
    try:
        if session is not None and message["type"] == HTTP_RESPONSE_START:
            if HTTP_200_OK <= cast("HTTPResponseStartEvent", message)["status"] < HTTP_300_MULTIPLE_CHOICES:
                session.commit()
            else:
                session.rollback()
    finally:
        if session and message["type"] in SESSION_TERMINUS_ASGI_EVENTS:
            session.close()
            delete_litestar_scope_state(scope, SESSION_SCOPE_KEY)


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """Sync SQLAlchemy Configuration."""

    before_send_handler: BeforeMessageSendHookHandler = default_before_send_handler
    """Handler to call before the ASGI message is sent.

    The handler should handle closing the session stored in the ASGI scope, if it's still open, and committing and
    uncommitted data.
    """
    engine_dependency_key: str = "db_engine"
    """Key to use for the dependency injection of database engines."""
    session_dependency_key: str = "db_session"
    """Key to use for the dependency injection of database sessions."""
    engine_app_state_key: str = "db_engine"
    """Key under which to store the SQLAlchemy engine in the application :class:`State <.datastructures.State>`
    instance.
    """
    session_maker_app_state_key: str = "session_maker_class"
    """Key under which to store the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>` in the application
    :class:`State <.datastructures.State>` instance.
    """
    engine_config: EngineConfig = field(default_factory=EngineConfig)
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """

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
        return self.session_maker_class(**session_kws)

    def provide_engine(self, state: State) -> Engine:
        """Create an engine instance.

        Args:
            state: The ``Litestar.state`` instance.

        Returns:
            An engine instance.
        """
        return cast("Engine", state.get(self.engine_app_state_key))

    def provide_session(self, state: State, scope: Scope) -> Session:
        """Create a session instance.

        Args:
            state: The ``Litestar.state`` instance.
            scope: The current connection's scope.

        Returns:
            A session instance.
        """
        session = cast("Session | None", get_litestar_scope_state(scope, SESSION_SCOPE_KEY))
        if session is None:
            session_maker = cast("Callable[[], Session]", state[self.session_maker_app_state_key])
            session = session_maker()
            set_litestar_scope_state(scope, SESSION_SCOPE_KEY, session)
        return session

    @property
    def signature_namespace(self) -> dict[str, Any]:
        """Return the plugin's signature namespace.

        Returns:
            A string keyed dict of names to be added to the namespace for signature forward reference resolution.
        """
        return {"Engine": Engine, "Session": Session}

    def on_shutdown(self, app: Litestar) -> None:
        """Disposes of the SQLAlchemy engine.

        Args:
            app: The ``Litestar`` instance.

        Returns:
            None
        """
        engine = cast("Engine", app.state.pop(self.engine_app_state_key))
        engine.dispose()

    def create_app_state_items(self) -> dict[str, Any]:
        """Key/value pairs to be stored in application state."""
        return {
            self.engine_app_state_key: self.get_engine(),
            self.session_maker_app_state_key: self.create_session_maker(),
        }

    def update_app_state(self, app: Litestar) -> None:
        """Set the app state with engine and session.

        Args:
            app: The ``Litestar`` instance.
        """
        app.state.update(self.create_app_state_items())

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Union, cast

from litestar.cli._utils import console  # pyright: ignore
from litestar.constants import HTTP_RESPONSE_START
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar._utils import (
    delete_aa_scope_state,
    get_aa_scope_state,
    set_aa_scope_state,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SessionKeyConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.common import (
    SESSION_SCOPE_KEY,
    SESSION_TERMINUS_ASGI_EVENTS,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.engine import EngineConfig
from advanced_alchemy.routing.context import reset_routing_context
from advanced_alchemy.routing.maker import dispose_session_maker_sync

logger = logging.getLogger("advanced_alchemy.extensions.litestar")

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from litestar import Litestar
    from litestar.datastructures.state import State
    from litestar.types import BeforeMessageSendHookHandler, Message, Scope

__all__ = (
    "SQLAlchemySyncConfig",
    "SessionKeyConfig",
    "autocommit_before_send_handler",
    "autocommit_handler_maker",
    "default_before_send_handler",
    "default_handler_maker",
)


def default_handler_maker(
    session_scope_key: str = SESSION_SCOPE_KEY,
) -> "Callable[[Message, Scope], None]":
    """Set up the handler to issue a transaction commit or rollback based on specified status codes
    Args:
        session_scope_key: The key to use within the application state

    Returns:
        The handler callable
    """

    def handler(message: "Message", scope: "Scope") -> None:
        """Handle commit/rollback, closing and cleaning up sessions before sending.

        Args:
            message: ASGI-``Message``
            scope: An ASGI-``Scope``

        Returns:
            None
        """
        session = cast("Optional[Session]", get_aa_scope_state(scope, session_scope_key))
        if session and message["type"] in SESSION_TERMINUS_ASGI_EVENTS:
            session.close()
            delete_aa_scope_state(scope, session_scope_key)

    return handler


default_before_send_handler = default_handler_maker()


def autocommit_handler_maker(
    commit_on_redirect: bool = False,
    extra_commit_statuses: "Optional[set[int]]" = None,
    extra_rollback_statuses: "Optional[set[int]]" = None,
    session_scope_key: str = SESSION_SCOPE_KEY,
) -> "Callable[[Message, Scope], None]":
    """Set up the handler to issue a transaction commit or rollback based on specified status codes
    Args:
        commit_on_redirect: Issue a commit when the response status is a redirect (``3XX``)
        extra_commit_statuses: A set of additional status codes that trigger a commit
        extra_rollback_statuses: A set of additional status codes that trigger a rollback
        session_scope_key: The key to use within the application state

    Raises:
        ValueError: If extra rollback statuses and commit statuses share any status codes

    Returns:
        The handler callable
    """
    if extra_commit_statuses is None:
        extra_commit_statuses = set()

    if extra_rollback_statuses is None:
        extra_rollback_statuses = set()

    if len(extra_commit_statuses & extra_rollback_statuses) > 0:
        msg = "Extra rollback statuses and commit statuses must not share any status codes"
        raise ValueError(msg)

    commit_range = range(200, 400 if commit_on_redirect else 300)

    def handler(message: "Message", scope: "Scope") -> None:
        """Handle commit/rollback, closing and cleaning up sessions before sending.

        Args:
            message: ASGI-``Message``
            scope: An ASGI-``Scope``

        """
        session = cast("Optional[Session]", get_aa_scope_state(scope, session_scope_key))
        try:
            if session is not None and message["type"] == HTTP_RESPONSE_START:
                if (message["status"] in commit_range or message["status"] in extra_commit_statuses) and message[
                    "status"
                ] not in extra_rollback_statuses:
                    session.commit()
                else:
                    session.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Session commit/rollback failed during cleanup", exc_info=True)
        finally:
            if session and message["type"] in SESSION_TERMINUS_ASGI_EVENTS:
                try:
                    session.close()
                except Exception:  # noqa: BLE001
                    logger.debug("Session close failed during cleanup", exc_info=True)
                delete_aa_scope_state(scope, session_scope_key)

    return handler


autocommit_before_send_handler = autocommit_handler_maker()


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """Litestar Sync SQLAlchemy Configuration."""

    before_send_handler: Optional[
        Union["BeforeMessageSendHookHandler", Literal["autocommit", "autocommit_include_redirects"]]
    ] = None
    """Handler to call before the ASGI message is sent.

    The handler should handle closing the session stored in the ASGI scope, if it's still open, and committing and
    uncommitted data.
    """
    session_key_config: SessionKeyConfig = field(default_factory=SessionKeyConfig)
    """Configuration for session/engine key names used for dependency injection and application state."""
    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """
    set_default_exception_handler: bool = True
    """Sets the default exception handler on application start."""

    def __post_init__(self) -> None:
        if self.before_send_handler is None:
            self.before_send_handler = default_handler_maker(
                session_scope_key=self.session_key_config.session_scope_key
            )
        if self.before_send_handler == "autocommit":
            self.before_send_handler = autocommit_handler_maker(
                session_scope_key=self.session_key_config.session_scope_key
            )
        if self.before_send_handler == "autocommit_include_redirects":
            self.before_send_handler = autocommit_handler_maker(
                session_scope_key=self.session_key_config.session_scope_key,
                commit_on_redirect=True,
            )
        super().__post_init__()

    def create_session_maker(self) -> "Callable[[], Session]":
        """Get a session maker. If none exists yet, create one.

        Delegates to the base-class implementation so configured session
        listeners for file objects, timestamps, and cache invalidation are
        registered.

        Returns:
            Session factory used by the plugin.
        """
        if self.session_factory_config.session_maker:
            return self.session_factory_config.session_maker
        return super().create_session_maker()

    @asynccontextmanager
    async def lifespan(
        self,
        app: "Litestar",
    ) -> "AsyncGenerator[None, None]":
        deps = self.create_app_state_items()
        app.state.update(deps)
        try:
            if self.metadata_config.create_all:
                self.create_all_metadata(app)
            yield
        finally:
            if self.session_key_config.engine_dependency_key in deps:
                engine = deps[self.session_key_config.engine_dependency_key]
                if hasattr(engine, "dispose"):
                    cast("Engine", engine).dispose()
            dispose_session_maker_sync(self.session_factory_config.session_maker)

    def provide_engine(self, state: "State") -> "Engine":
        """Create an engine instance.

        Args:
            state: The ``Litestar.state`` instance.

        Returns:
            An engine instance.
        """
        return cast("Engine", state.get(self.session_key_config.engine_app_state_key))

    def provide_session(self, state: "State", scope: "Scope") -> "Session":
        """Create a session instance.

        Args:
            state: The ``Litestar.state`` instance.
            scope: The current connection's scope.

        Returns:
            A session instance.
        """
        # Import locally to avoid potential circular dependency issues at module level
        from advanced_alchemy._listeners import set_async_context

        session = cast("Optional[Session]", get_aa_scope_state(scope, self.session_key_config.session_scope_key))
        if session is None:
            # Reset routing context for request-scoped isolation when creating a new session
            reset_routing_context()
            session_maker = cast("Callable[[], Session]", state[self.session_key_config.session_maker_app_state_key])
            session = session_maker()
            set_aa_scope_state(scope, self.session_key_config.session_scope_key, session)

        set_async_context(False)  # Set context before yielding
        return session

    @property
    def signature_namespace(self) -> "dict[str, Any]":
        """Return the plugin's signature namespace.

        Returns:
            A string keyed dict of names to be added to the namespace for signature forward reference resolution.
        """
        return {"Engine": Engine, "Session": Session}

    def create_all_metadata(self, app: "Litestar") -> None:
        """Create all metadata

        Args:
            app (Litestar): The ``Litestar`` instance
        """
        with self.get_engine().begin() as conn:
            try:
                metadata_registry.get(self.metadata_config.bind_key).create_all(bind=conn)
            except OperationalError as exc:
                console.print(f"[bold red] * Could not create target metadata.  Reason: {exc}")

    def create_app_state_items(self) -> "dict[str, Any]":
        """Key/value pairs to be stored in application state.

        Returns:
            A dictionary of key/value pairs to be stored in application state.
        """
        return {
            self.session_key_config.engine_app_state_key: self.get_engine(),
            self.session_key_config.session_maker_app_state_key: self.create_session_maker(),
        }

    def update_app_state(self, app: "Litestar") -> None:
        """Set the app state with engine and session.

        Args:
            app: The ``Litestar`` instance.
        """
        app.state.update(self.create_app_state_items())

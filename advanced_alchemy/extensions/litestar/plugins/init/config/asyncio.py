from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Literal, cast

from litestar.cli._utils import console
from litestar.constants import HTTP_RESPONSE_START
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar._utils import (
    delete_aa_scope_state,
    get_aa_scope_state,
    set_aa_scope_state,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.common import (
    SESSION_SCOPE_KEY,
    SESSION_TERMINUS_ASGI_EVENTS,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.engine import EngineConfig

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine
    from typing import Any

    from litestar import Litestar
    from litestar.datastructures.state import State
    from litestar.types import BeforeMessageSendHookHandler, Message, Scope

    # noinspection PyUnresolvedReferences


__all__ = (
    "SQLAlchemyAsyncConfig",
    "default_before_send_handler",
    "autocommit_before_send_handler",
)


def default_handler_maker(
    session_scope_key: str = SESSION_SCOPE_KEY,
) -> Callable[[Message, Scope], Coroutine[Any, Any, None]]:
    """Set up the handler to issue a transaction commit or rollback based on specified status codes
    Args:
        session_scope_key: The key to use within the application state

    Returns:
        The handler callable
    """

    async def handler(message: Message, scope: Scope) -> None:
        """Handle commit/rollback, closing and cleaning up sessions before sending.

        Args:
            message: ASGI-``Message``
            scope: An ASGI-``Scope``

        Returns:
            None
        """
        session = cast("AsyncSession | None", get_aa_scope_state(scope, session_scope_key))
        if session and message["type"] in SESSION_TERMINUS_ASGI_EVENTS:
            await session.close()
            delete_aa_scope_state(scope, session_scope_key)

    return handler


default_before_send_handler = default_handler_maker()


def autocommit_handler_maker(
    commit_on_redirect: bool = False,
    extra_commit_statuses: set[int] | None = None,
    extra_rollback_statuses: set[int] | None = None,
    session_scope_key: str = SESSION_SCOPE_KEY,
) -> Callable[[Message, Scope], Coroutine[Any, Any, None]]:
    """Set up the handler to issue a transaction commit or rollback based on specified status codes
    Args:
        commit_on_redirect: Issue a commit when the response status is a redirect (``3XX``)
        extra_commit_statuses: A set of additional status codes that trigger a commit
        extra_rollback_statuses: A set of additional status codes that trigger a rollback
        session_scope_key: The key to use within the application state

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

    async def handler(message: Message, scope: Scope) -> None:
        """Handle commit/rollback, closing and cleaning up sessions before sending.

        Args:
            message: ASGI-``Message``
            scope: An ASGI-``Scope``

        Returns:
            None
        """
        session = cast("AsyncSession | None", get_aa_scope_state(scope, session_scope_key))
        try:
            if session is not None and message["type"] == HTTP_RESPONSE_START:
                if (message["status"] in commit_range or message["status"] in extra_commit_statuses) and message[
                    "status"
                ] not in extra_rollback_statuses:
                    await session.commit()
                else:
                    await session.rollback()
        finally:
            if session and message["type"] in SESSION_TERMINUS_ASGI_EVENTS:
                await session.close()
                delete_aa_scope_state(scope, session_scope_key)

    return handler


autocommit_before_send_handler = autocommit_handler_maker()


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """Async SQLAlchemy Configuration."""

    before_send_handler: BeforeMessageSendHookHandler | None | Literal["autocommit"] = None
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
    session_scope_key: str = SESSION_SCOPE_KEY
    """Key under which to store the SQLAlchemy scope in the application."""
    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """

    def _ensure_unique_session_scope_key(self, key: str, _iter: int = 0) -> str:
        if key in self.__class__._KEY_REGISTRY:  # noqa: SLF001
            _iter += 1
            key = self._ensure_unique_session_scope_key(f"{key}_{_iter}", _iter)
        return key

    def __post_init__(self) -> None:
        self.session_scope_key = self._ensure_unique_session_scope_key(self.session_scope_key)
        self.__class__._KEY_REGISTRY.add(self.session_scope_key)  # noqa: SLF001
        if self.before_send_handler is None:
            self.before_send_handler = default_handler_maker(session_scope_key=self.session_scope_key)
        if self.before_send_handler == "autocommit":
            self.before_send_handler = autocommit_handler_maker(session_scope_key=self.session_scope_key)
        super().__post_init__()

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
        return self.session_maker_class(**session_kws)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]

    @asynccontextmanager
    async def lifespan(
        self,
        app: Litestar,
    ) -> AsyncGenerator[None, None]:
        deps = self.create_app_state_items()
        app.state.update(deps)
        try:
            if self.create_all:
                await self.create_all_metadata(app)
            yield
        finally:
            if self.engine_dependency_key in deps:
                await cast("AsyncEngine", deps[self.engine_dependency_key]).dispose()

    def provide_engine(self, state: State) -> AsyncEngine:
        """Create an engine instance.

        Args:
            state: The ``Litestar.state`` instance.

        Returns:
            An engine instance.
        """
        return cast("AsyncEngine", state.get(self.engine_app_state_key))

    def provide_session(self, state: State, scope: Scope) -> AsyncSession:
        """Create a session instance.

        Args:
            state: The ``Litestar.state`` instance.
            scope: The current connection's scope.

        Returns:
            A session instance.
        """
        session = cast("AsyncSession | None", get_aa_scope_state(scope, self.session_scope_key))
        if session is None:
            session_maker = cast("Callable[[], AsyncSession]", state[self.session_maker_app_state_key])
            session = session_maker()
            set_aa_scope_state(scope, self.session_scope_key, session)
        return session

    @property
    def signature_namespace(self) -> dict[str, Any]:
        """Return the plugin's signature namespace.

        Returns:
            A string keyed dict of names to be added to the namespace for signature forward reference resolution.
        """
        return {"AsyncEngine": AsyncEngine, "AsyncSession": AsyncSession}

    async def create_all_metadata(self, app: Litestar) -> None:
        """Create all metadata

        Args:
            app (Litestar): The ``Litestar`` instance
        """
        async with self.get_engine().begin() as conn:
            try:
                await conn.run_sync(self.alembic_config.target_metadata.create_all)
            except OperationalError as exc:
                console.print(f"[bold red] * Could not create target metadata.  Reason: {exc}")

    def create_app_state_items(self) -> dict[str, Any]:
        """Key/value pairs to be stored in application state."""
        return {
            self.engine_app_state_key: self.get_engine(),
            self.session_maker_app_state_key: self.create_session_maker(),
        }

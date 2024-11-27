from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Generic, Protocol, cast, overload

from sanic import HTTPResponse, Request, Sanic  # noqa: TC002
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from advanced_alchemy.config.common import EngineT, SessionMakerT, SessionT
from advanced_alchemy.exceptions import MissingDependencyError

try:
    from sanic.helpers import Default, _default  # pyright: ignore[reportPrivateUsage]
    from sanic_ext import Extend
    from sanic_ext.extensions.base import Extension

    SANIC_INSTALLED = True
except ModuleNotFoundError:
    SANIC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]
    Extension = type("Extension", (), {})  # type: ignore  # noqa: PGH003
    Extend = type("Extend", (), {})  # type: ignore  # noqa: PGH003
    Default = type("Default", (), {})  # type: ignore  # noqa: PGH003
    _default = Default()

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig
    from advanced_alchemy.config.types import CommitStrategy

__all__ = ("CommitStrategyExecutor", "SanicAdvancedAlchemy")


class CommitStrategyExecutor(Protocol):
    async def __call__(self, *, session: Session | AsyncSession, response: HTTPResponse) -> None: ...


class SanicAdvancedAlchemy(Generic[EngineT, SessionT, SessionMakerT], Extension):  # pyright: ignore[reportGeneralTypeIssues,reportUntypedBaseClass]
    """Sanic extension for integrating Advanced Alchemy with SQLAlchemy.

    Args:
        sqlalchemy_config (advanced_alchemy.config.sync.SQLAlchemySyncConfig | advanced_alchemy.config.asyncio.SQLAlchemyAsyncConfig):
            Configuration for SQLAlchemy.
        autocommit (advanced_alchemy.config.types.CommitStrategy | None):
            Strategy for committing transactions. Defaults to None.
        counters (sanic.helpers.Default | bool | None):
            Enables or disables counters. Defaults to sanic.helpers._default.
        session_maker_key (str| None):
            Key for the session maker in app context. Defaults to "sessionmaker".
        engine_key (str| None):
            Key for the engine in app context. Defaults to "engine".
        session_key (str| None):
            Key for the session in request context. Defaults to "session".
    """

    name = "AdvancedAlchemy"

    @overload
    def __init__(
        self: SanicAdvancedAlchemy[AsyncEngine, AsyncSession, async_sessionmaker[AsyncSession]],
        *,
        sqlalchemy_config: SQLAlchemyAsyncConfig,
        autocommit: CommitStrategy | None = None,
        counters: Default | bool = _default,  # pyright: ignore[reportInvalidTypeForm,reportUnknownParameterType]
        session_maker_key: str = "sessionmaker",
        engine_key: str = "engine",
        session_key: str = "session",
    ) -> None: ...

    @overload
    def __init__(
        self: SanicAdvancedAlchemy[Engine, Session, sessionmaker[Session]],
        *,
        sqlalchemy_config: SQLAlchemySyncConfig,
        autocommit: CommitStrategy | None = None,
        counters: Default | bool = _default,  # pyright: ignore[reportInvalidTypeForm,reportUnknownParameterType]
        session_maker_key: str = "sessionmaker",
        engine_key: str = "engine",
        session_key: str = "session",
    ) -> None: ...

    def __init__(
        self: (
            SanicAdvancedAlchemy[AsyncEngine, AsyncSession, async_sessionmaker[AsyncSession]]
            | SanicAdvancedAlchemy[Engine, Session, sessionmaker[Session]]
        ),
        *,
        sqlalchemy_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
        autocommit: CommitStrategy | None = None,
        counters: Default | bool = _default,  # pyright: ignore[reportInvalidTypeForm,reportUnknownParameterType]
        session_maker_key: str = "sessionmaker",
        engine_key: str = "engine",
        session_key: str = "session",
    ) -> None:
        if not SANIC_INSTALLED:
            msg = "Could not locate either Sanic or Sanic Extensions. Both libraries must be installed to use Advanced Alchemy. Try: pip install sanic[ext]"
            raise MissingDependencyError(
                msg,
            )
        self.sqlalchemy_config = sqlalchemy_config
        self.engine_key = engine_key
        self.session_maker_key = session_maker_key
        self.session_key = session_key
        self.autocommit_strategy = autocommit
        self._commit_strategies: dict[CommitStrategy, CommitStrategyExecutor] = {  # pyright: ignore[reportAttributeAccessIssue]
            "always": self._commit_strategy_always,
            "match_status": self._commit_strategy_match_status,
        }
        self.counters = counters
        self.engine = (
            self.sqlalchemy_config.engine_instance
            if self.sqlalchemy_config.engine_instance is not None
            else self.sqlalchemy_config.get_engine()
        )
        self.session_maker = self.sqlalchemy_config.create_session_maker()

        session_maker = cast("SessionMakerT", self.session_maker)
        self.session_class = session_maker.class_

        self.app: Sanic  # pyright: ignore[reportMissingTypeArgument]

    async def _do_commit(self, session: Session | AsyncSession) -> None:
        """Commit the current transaction.

        Args:
            session (sqlalchemy.orm.Session | sqlalchemy.ext.asyncio.AsyncSession):
                The session to commit.
        """
        if not isinstance(session, AsyncSession):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.commit)
        else:
            await session.commit()

    async def _do_rollback(self, session: Session | AsyncSession) -> None:
        """Rollback the current transaction.

        Args:
            session (sqlalchemy.orm.Session | sqlalchemy.ext.asyncio.AsyncSession):
                The session to rollback.
        """
        if not isinstance(session, AsyncSession):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.rollback)
        else:
            await session.rollback()

    async def _do_close(self, session: Session | AsyncSession) -> None:
        """Close the session.

        Args:
            session (sqlalchemy.orm.Session | sqlalchemy.ext.asyncio.AsyncSession):
                The session to close.
        """
        if not isinstance(session, AsyncSession):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.close)
        else:
            await session.close()

    async def _commit_strategy_always(self, *, session: Session | AsyncSession, response: HTTPResponse) -> None:
        """Commit strategy that always commits the session.

        Args:
            session (sqlalchemy.orm.Session | sqlalchemy.ext.asyncio.AsyncSession):
                The session to commit.
            response (sanic.HTTPResponse):
                The HTTP response.
        """
        await self._do_commit(session)

    async def _commit_strategy_match_status(self, *, session: Session | AsyncSession, response: HTTPResponse) -> None:
        """Commit strategy that commits based on the response status.

        Args:
            session (sqlalchemy.orm.Session | sqlalchemy.ext.asyncio.AsyncSession):
                The session to commit or rollback.
            response (sanic.HTTPResponse):
                The HTTP response.
        """
        if 200 <= response.status < 300:  # noqa: PLR2004
            await self._do_commit(session)
        else:
            await self._do_rollback(session)

    async def session_handler(self, session: Session | AsyncSession, request: Request, response: HTTPResponse) -> None:
        """Handle the session lifecycle based on the commit strategy.

        Args:
            session (sqlalchemy.orm.Session | sqlalchemy.ext.asyncio.AsyncSession):
                The current session.
            request (sanic.Request):
                The incoming request.
            response (sanic.HTTPResponse):
                The outgoing response.
        """
        try:
            if self.autocommit_strategy:
                await self._commit_strategies[self.autocommit_strategy](session=session, response=response)  # pyright: ignore[reportArgumentType]
        finally:
            await self._do_close(session)
            delattr(request.ctx, self.session_key)

    def get_engine(self) -> EngineT:
        """Retrieve the SQLAlchemy engine from the app context.

        Returns:
            EngineT: The SQLAlchemy engine.
        """
        engine = getattr(self.app.ctx, self.engine_key, None)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        if engine is not None:
            return cast(EngineT, engine)
        engine = cast(EngineT, self.engine)
        setattr(self.app.ctx, self.engine_key, engine)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        return engine

    def get_sessionmaker(self) -> Callable[[], SessionT]:
        """Retrieve the session maker.

        Returns:
            Callable[[], SessionT]: A callable that returns a new session.
        """
        return cast(Callable[[], SessionT], self.session_maker)

    def get_session(self, request: Request) -> SessionT:
        """Retrieve or create a session for the current request.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            SessionT: The session associated with the request.
        """
        session = getattr(request.ctx, self.session_key, None)
        if session is not None:
            return cast(SessionT, session)

        session = cast("SessionT", self.session_maker())
        setattr(request.ctx, self.session_key, session)
        return session

    def get_engine_from_request(self, request: Request) -> EngineT:
        """Retrieve the engine from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            EngineT: The SQLAlchemy engine.
        """
        return cast("EngineT", getattr(request.app.ctx, self.engine_key, None))

    def get_sessionmaker_from_request(self, request: Request) -> SessionMakerT:
        """Retrieve the session maker from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            SessionMakerT: The session maker.
        """
        return cast("SessionMakerT", getattr(request.app.ctx, self.session_maker_key, None))

    def get_session_from_request(self, request: Request) -> SessionT:
        """Retrieve the session from the request context.

        Args:
            request (sanic.Request): The incoming request.

        Returns:
            SessionT: The session associated with the request.
        """
        return cast("SessionT", getattr(request.ctx, self.session_key, None))

    def startup(self, bootstrap: Extend) -> None:  # pyright: ignore[reportUnknownParameterType,reportInvalidTypeForm]
        """Advanced Alchemy Sanic extension startup hook.

        Args:
            bootstrap (sanic_ext.Extend): The Sanic extension bootstrap.
        """

        @self.app.before_server_start  # pyright: ignore[reportUnknownMemberType]
        async def on_startup(_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            setattr(self.app.ctx, self.engine_key, self.engine)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            setattr(self.app.ctx, self.session_maker_key, self.session_maker)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                type(self.engine),
                self.get_engine_from_request,
            )
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                type(self.session_maker),
                self.get_sessionmaker_from_request,
            )
            bootstrap.add_dependency(  # pyright: ignore[reportUnknownMemberType]
                self.session_class,
                self.get_session_from_request,
            )

        @self.app.after_server_stop  # pyright: ignore[reportUnknownMemberType]
        async def on_shutdown(_: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            if isinstance(self.engine, Engine):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.engine.dispose)
            else:
                await self.engine.dispose()
            if hasattr(self.app.ctx, self.engine_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
                delattr(self.app.ctx, self.engine_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            if hasattr(self.app.ctx, self.session_maker_key):  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
                delattr(self.app.ctx, self.session_maker_key)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

        @self.app.middleware("request")  # pyright: ignore[reportUnknownMemberType]
        async def on_request(request: Request) -> None:  # pyright: ignore[reportUnusedFunction]
            session: Session | AsyncSession | None = getattr(request.ctx, self.session_key, None)
            if session is None:
                session = self.get_session(request)
                setattr(request.ctx, self.session_key, session)

        @self.app.middleware("response")  # type: ignore[arg-type]
        async def on_response(request: Request, response: HTTPResponse) -> None:  # pyright: ignore[reportUnusedFunction]
            session: Session | AsyncSession | None = getattr(request.ctx, self.session_key, None)
            if session is not None:
                await self.session_handler(session=session, request=request, response=response)

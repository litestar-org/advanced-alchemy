from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Generic, Protocol, cast, overload

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.common import EngineT, SessionT
from advanced_alchemy.exceptions import MissingDependencyError

try:
    from sanic.helpers import Default, _default
    from sanic_ext import Extend
    from sanic_ext.extensions.base import Extension

    SANIC_INSTALLED = True
except ModuleNotFoundError:
    SANIC_INSTALLED = False
    Extension = type("Extension", (), {})  # type: ignore  # noqa: PGH003
    Extend = type("Extend", (), {})  # type: ignore  # noqa: PGH003
    Default = type("Default", (), {})  # type: ignore  # noqa: PGH003
    _default = Default()

if TYPE_CHECKING:
    from sanic import HTTPResponse, Request
    from sqlalchemy.orm import Session

    from advanced_alchemy.config.sync import SQLAlchemySyncConfig
    from advanced_alchemy.config.types import CommitStrategy


class CommitStrategyExecutor(Protocol):
    async def __call__(self, *, session: Session | AsyncSession, response: HTTPResponse) -> None:
        ...


class SanicAdvancedAlchemy(Extension, Generic[EngineT, SessionT]):
    name = "advanced_alchemy"

    @overload
    def __init__(
        self: SanicAdvancedAlchemy[AsyncEngine, AsyncSession],
        *,
        sqlalchemy_config: SQLAlchemyAsyncConfig,
        autocommit: CommitStrategy | None = None,
        counters: Default | bool = _default,
    ) -> None:
        ...

    @overload
    def __init__(
        self: SanicAdvancedAlchemy[Engine, Session],
        *,
        sqlalchemy_config: SQLAlchemySyncConfig,
        autocommit: CommitStrategy | None = None,
        counters: Default | bool = _default,
    ) -> None:
        ...

    def __init__(
        self: SanicAdvancedAlchemy[AsyncEngine, AsyncSession] | SanicAdvancedAlchemy[Engine, Session],
        *,
        sqlalchemy_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
        autocommit: CommitStrategy | None = None,
        counters: Default | bool = _default,
    ) -> None:
        if not SANIC_INSTALLED:
            msg = "Could not locate either Sanic or Sanic Extensions. Both libraries must be installed to use Advanced Alchemy. Try: pip install sanic[ext]"
            raise MissingDependencyError(
                msg,
            )
        self._kind = "async" if isinstance(sqlalchemy_config, SQLAlchemyAsyncConfig) else "sync"
        self.sqlalchemy_config = sqlalchemy_config
        self.engine_key = "db_engine"
        self.sessionmaker_key = "sessionmaker"
        self.session_key = "session"
        self.autocommit_strategy = autocommit
        self._commit_strategies: dict[CommitStrategy, CommitStrategyExecutor] = {
            "always": self._commit_strategy_always,
            "match_status": self._commit_strategy_match_status,
        }
        self.counters = counters

    async def _do_commit(self, session: Session | AsyncSession) -> None:
        if not isinstance(session, AsyncSession):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.commit)
        else:
            await session.commit()

    async def _do_rollback(self, session: Session | AsyncSession) -> None:
        if not isinstance(session, AsyncSession):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.rollback)
        else:
            await session.rollback()

    async def _do_close(self, session: Session | AsyncSession) -> None:
        if not isinstance(session, AsyncSession):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, session.close)
        else:
            await session.close()

    async def _commit_strategy_always(self, *, session: Session | AsyncSession, response: HTTPResponse) -> None:
        await self._do_commit(session)

    async def _commit_strategy_match_status(self, *, session: Session | AsyncSession, response: HTTPResponse) -> None:
        if 200 <= response.status < 300:  # noqa: PLR2004
            await self._do_commit(session)
        else:
            await self._do_rollback(session)

    async def session_handler(self, session: Session | AsyncSession, request: Request, response: HTTPResponse) -> None:
        try:
            if self.autocommit_strategy:
                await self._commit_strategies[self.autocommit_strategy](session=session, response=response)
        finally:
            await self._do_close(session)
            delattr(request.ctx, self.session_key)

    def get_engine(self) -> EngineT:
        return cast(EngineT, getattr(self.app.ctx, self.engine_key))

    def get_sessionmaker(self) -> Callable[[], SessionT]:
        return cast(Callable[[], SessionT], getattr(self.app.ctx, self.sessionmaker_key))

    def get_session(self, request: Request) -> SessionT:
        session = cast(SessionT | None, getattr(request.ctx, self.session_key, None))
        if session is not None:
            return session

        session = self.get_sessionmaker()()
        setattr(request.ctx, self.session_key, session)
        return session

    def startup(self, bootstrap: Extend) -> None:
        """Advanced Alchemy Sanic extension startup hook."""

        @self.app.before_server_start
        async def on_startup(_: Any) -> None:
            setattr(self.app.ctx, self.engine_key, self.config.get_engine())
            setattr(self.app.ctx, self.sessionmaker_key, self.config.create_session_maker())

        @self.app.after_server_stop
        async def on_shutdown(_: Any) -> None:
            engine = getattr(self.app.ctx, self.engine_key)
            if isinstance(engine, Engine):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, engine.dispose)
            else:
                await engine.dispose()
            delattr(self.app.ctx, self.engine_key)
            delattr(self.app.ctx, self.sessionmaker_key)

        @self.app.middleware("request")
        async def on_request(request: Request) -> None:
            session: Session | AsyncSession | None = getattr(request.ctx, self.session_key, None)
            if session is None:
                session = self.get_session(request)
                setattr(request.ctx, self.session_key, session)

        @self.app.middleware("response")
        async def on_response(request: Request, response: HTTPResponse) -> None:
            session: Session | AsyncSession | None = getattr(request.ctx, self.session_key, None)
            if session is not None:
                await self.session_handler(session=session, request=request, response=response)

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Generic, Protocol, cast, overload

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request  # noqa: TCH002

from advanced_alchemy.config.common import EngineT, SessionT
from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from starlette.applications import Starlette
    from starlette.responses import Response

    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig
    from advanced_alchemy.config.types import CommitStrategy


class CommitStrategyExecutor(Protocol):
    async def __call__(self, *, session: Session | AsyncSession, response: Response) -> None: ...


class StarletteAdvancedAlchemy(Generic[EngineT, SessionT]):
    @overload
    def __init__(
        self: StarletteAdvancedAlchemy[AsyncEngine, AsyncSession],
        config: SQLAlchemyAsyncConfig,
        autocommit: CommitStrategy | None = None,
        app: Starlette | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: StarletteAdvancedAlchemy[Engine, Session],
        config: SQLAlchemySyncConfig,
        autocommit: CommitStrategy | None = None,
        app: Starlette | None = None,
    ) -> None: ...

    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig,
        autocommit: CommitStrategy | None = None,
        app: Starlette | None = None,
    ) -> None:
        self.config = config
        self._app: Starlette
        self.engine_key: str
        self.sessionmaker_key: str
        self.session_key: str
        self.autocommit_strategy = autocommit
        self._commit_strategies: dict[CommitStrategy, CommitStrategyExecutor] = {
            "always": self._commit_strategy_always,
            "match_status": self._commit_strategy_match_status,
        }
        if app is not None:
            self.init_app(app)

    @staticmethod
    def _make_unique_state_key(app: Starlette, key: str) -> str:
        i = 0
        while True:
            if not hasattr(app.state, key):
                return key
            key = f"{key}_{i}"
            i += i

    def init_app(self, app: Starlette) -> None:
        engine = self.config.get_engine()
        self.engine_key = self._make_unique_state_key(app, f"sqla_engine_{engine.name}")
        self.sessionmaker_key = self._make_unique_state_key(app, f"sqla_sessionmaker_{engine.name}")
        self.session_key = f"sqla_session_{self.sessionmaker_key}"

        setattr(app.state, self.engine_key, engine)
        setattr(app.state, self.sessionmaker_key, self.config.create_session_maker())

        app.add_middleware(BaseHTTPMiddleware, dispatch=self.middleware_dispatch)
        app.add_event_handler("shutdown", self.on_shutdown)

        self._app = app

    async def _do_commit(self, session: Session | AsyncSession) -> None:
        if not isinstance(session, AsyncSession):
            await run_in_threadpool(session.commit)
        else:
            await session.commit()

    async def _do_rollback(self, session: Session | AsyncSession) -> None:
        if not isinstance(session, AsyncSession):
            await run_in_threadpool(session.rollback)
        else:
            await session.rollback()

    async def _do_close(self, session: Session | AsyncSession) -> None:
        if not isinstance(session, AsyncSession):
            await run_in_threadpool(session.close)
        else:
            await session.close()

    async def _commit_strategy_always(self, *, session: Session | AsyncSession, response: Response) -> None:
        await self._do_commit(session)

    async def _commit_strategy_match_status(self, *, session: Session | AsyncSession, response: Response) -> None:
        if 200 <= response.status_code < 300:  # noqa: PLR2004
            await self._do_commit(session)
        else:
            await self._do_rollback(session)

    async def session_handler(self, session: Session | AsyncSession, request: Request, response: Response) -> None:
        try:
            if self.autocommit_strategy:
                await self._commit_strategies[self.autocommit_strategy](session=session, response=response)
        finally:
            await self._do_close(session)
            delattr(request.state, self.session_key)

    @property
    def app(self) -> Starlette:
        try:
            return self._app
        except AttributeError as e:
            msg = "Application not initialized. Did you forget to call init_app?"
            raise ImproperConfigurationError(msg) from e

    def get_engine(self) -> EngineT:
        return cast(EngineT, getattr(self.app.state, self.engine_key))

    def get_sessionmaker(self) -> Callable[[], SessionT]:
        return cast(Callable[[], SessionT], getattr(self.app.state, self.sessionmaker_key))

    def get_session(self, request: Request) -> SessionT:
        session = getattr(request.state, self.session_key, None)
        if session is not None:
            return cast(SessionT, session)

        session = self.get_sessionmaker()()
        setattr(request.state, self.session_key, session)
        return session

    async def middleware_dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        session: Session | AsyncSession | None = getattr(request.state, self.session_key, None)
        if session is not None:
            await self.session_handler(session=session, request=request, response=response)

        return response

    async def on_shutdown(self) -> None:
        engine = getattr(self.app.state, self.engine_key)
        if isinstance(engine, Engine):
            await run_in_threadpool(engine.dispose)
        else:
            await engine.dispose()

        delattr(self.app.state, self.engine_key)
        delattr(self.app.state, self.sessionmaker_key)

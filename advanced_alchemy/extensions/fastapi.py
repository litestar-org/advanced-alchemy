from __future__ import annotations

from typing import TYPE_CHECKING, Generic, cast, overload

from fastapi import Request  # noqa: TCH002
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.common import EngineT, SessionT
from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.responses import Response

    from advanced_alchemy.config.sync import SQLAlchemySyncConfig


class FastAPIAdvancedAlchemy(Generic[EngineT, SessionT]):
    def __init__(self, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig, autocommit: bool = False) -> None:
        self.config = config
        self._kind = "async" if isinstance(config, SQLAlchemyAsyncConfig) else "sync"
        self.engine_key = f"{self._kind}_sqla_engine"
        self.sessionmaker_key = f"{self._kind}_sessionmaker"
        self.session_key = f"{self._kind}_sqla_session"
        self.autocommit = autocommit
        self._app: FastAPI

    @classmethod
    @overload
    def from_config(cls, config: SQLAlchemyAsyncConfig) -> FastAPIAdvancedAlchemy[AsyncEngine, AsyncSession]:
        return FastAPIAdvancedAlchemy[AsyncEngine, AsyncSession](config=config)

    @classmethod
    @overload
    def from_config(cls, config: SQLAlchemySyncConfig) -> FastAPIAdvancedAlchemy[Engine, Session]:
        return FastAPIAdvancedAlchemy[Engine, Session](config=config)

    @classmethod
    def from_config(cls, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> FastAPIAdvancedAlchemy:
        return cls(config=config)

    def init_app(self, app: FastAPI) -> None:
        app.add_middleware(BaseHTTPMiddleware, dispatch=self.middleware_dispatch)
        app.add_event_handler("startup", self.on_startup)
        app.add_event_handler("shutdown", self.on_shutdown)
        self._app = app

    async def session_handler_sync(self, session: Session, request: Request, response: Response) -> None:
        try:
            if self.autocommit:
                if 200 <= response.status_code < 300:  # noqa: PLR2004
                    await run_in_threadpool(session.commit)
                else:
                    await run_in_threadpool(session.rollback)
        finally:
            await run_in_threadpool(session.close)
            delattr(request.state, self.session_key)

    async def session_handler_async(self, session: AsyncSession, request: Request, response: Response) -> None:
        try:
            if self.autocommit:
                if 200 <= response.status_code < 300:  # noqa: PLR2004
                    await session.commit()
                else:
                    await session.rollback()
        finally:
            await session.close()
            delattr(request.state, self.session_key)

    @property
    def app(self) -> FastAPI:
        try:
            return self._app
        except AttributeError as e:
            msg = "FastAPI app not initialized. Did you forget to call init_app?"
            raise ImproperConfigurationError(msg) from e

    def get_engine(self) -> EngineT:
        return cast(EngineT, getattr(self.app.state, self.engine_key))

    def get_session(self, request: Request) -> SessionT:
        session = cast(SessionT | None, getattr(request.state, self.session_key, None))
        if session is not None:
            return session

        session_maker = getattr(request.app.state, self.sessionmaker_key)
        session = session_maker()
        setattr(request.state, self.session_key, session)
        return session

    async def middleware_dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        session: Session | AsyncSession | None = getattr(request.state, self.session_key, None)
        if session is not None:
            if isinstance(session, AsyncSession):
                await self.session_handler_async(session=session, request=request, response=response)
            else:
                await self.session_handler_sync(session=session, request=request, response=response)

        return response

    async def on_startup(self) -> None:
        setattr(self.app.state, self.engine_key, self.config.get_engine())
        setattr(self.app.state, self.sessionmaker_key, self.config.create_session_maker())

    async def on_shutdown(self) -> None:
        engine = getattr(self.app.state, self.engine_key)
        if isinstance(engine, Engine):
            await run_in_threadpool(engine.dispose)
        else:
            await engine.dispose()

        delattr(self.app.state, self.engine_key)
        delattr(self.app.state, self.sessionmaker_key)

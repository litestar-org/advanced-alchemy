from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from sanic import HTTPResponse, Request
    from sqlalchemy.orm import Session

    from advanced_alchemy.config.sync import SQLAlchemySyncConfig

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


class SanicAdvancedAlchemy(Extension):
    name = "advanced_alchemy"

    def __init__(
        self,
        *,
        sqlalchemy_config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig,
        autocommit: bool = False,
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
        self.autocommit = autocommit
        self.counters = counters

    @classmethod
    def from_config(cls, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> SanicAdvancedAlchemy:
        return cls(sqlalchemy_config=config)

    async def session_handler_sync(self, session: Session, request: Request, response: HTTPResponse) -> None:
        loop = asyncio.get_event_loop()
        try:
            if self.autocommit:
                if 200 <= response.status < 300:  # noqa: PLR2004
                    await loop.run_in_executor(None, session.commit)
                else:
                    await loop.run_in_executor(None, session.rollback)
        finally:
            await loop.run_in_executor(None, session.close)
            delattr(request.ctx, self.session_key)

    async def session_handler_async(self, session: AsyncSession, request: Request, response: HTTPResponse) -> None:
        try:
            if self.autocommit:
                if 200 <= response.status < 300:  # noqa: PLR2004
                    await session.commit()
                else:
                    await session.rollback()
        finally:
            await session.close()
            delattr(request.ctx, self.session_key)

    def startup(self, bootstrap: Extend) -> None:
        @self.app.before_server_start
        async def on_startup(_: Any) -> None:
            self.sqlalchemy_config.create_engine()
            self.sqlalchemy_config.create_session_maker()

        @self.app.after_server_stop
        async def on_shutdown(_: Any) -> None:
            engine = self.sqlalchemy_config.engine_instance
            if engine is not None:
                if isinstance(engine, Engine):
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, engine.dispose)
                else:
                    await engine.dispose()

        @self.app.middleware("request")
        async def on_request(request: Request) -> None:
            session: Session | AsyncSession | None = getattr(request.ctx, self.session_key, None)
            if session is None:
                session_maker = getattr(request.ctx, self.sessionmaker_key)
                session = session_maker()
                setattr(request.ctx, self.session_key, session)

        @self.app.middleware("response")
        async def on_response(request: Request, response: HTTPResponse) -> None:
            session: Session | AsyncSession | None = getattr(request.ctx, self.session_key, None)
            if session is not None:
                if isinstance(session, AsyncSession):
                    await self.session_handler_async(session=session, request=request, response=response)
                else:
                    await self.session_handler_sync(session=session, request=request, response=response)

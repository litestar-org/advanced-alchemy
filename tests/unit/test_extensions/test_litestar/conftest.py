from __future__ import annotations

import importlib
import random
import string
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, TypeVar, cast

import pytest
from litestar.app import Litestar
from litestar.testing import RequestFactory
from litestar.types import (
    ASGIVersion,
    RouteHandlerType,
    Scope,
    ScopeSession,
)
from pytest import FixtureRequest, MonkeyPatch
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.extensions.litestar.alembic import AlembicCommands
from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyPlugin
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig


@pytest.fixture
def create_module(tmp_path: Path, monkeypatch: MonkeyPatch) -> Callable[[str], ModuleType]:
    """Utility fixture for dynamic module creation."""

    def wrapped(source: str) -> ModuleType:
        """

        Args:
            source: Source code as a string.

        Returns:
            An imported module.
        """
        T = TypeVar("T")

        def not_none(val: T | None) -> T:
            assert val is not None
            return val

        def module_name_generator() -> str:
            letters = string.ascii_lowercase
            return "".join(random.choice(letters) for _ in range(10))

        module_name = module_name_generator()
        path = tmp_path / f"{module_name}.py"
        path.write_text(source)
        # https://docs.python.org/3/library/importlib.html#importing-a-source-file-directly
        spec = not_none(importlib.util.spec_from_file_location(module_name, path))
        module = not_none(importlib.util.module_from_spec(spec))
        monkeypatch.setitem(sys.modules, module_name, module)
        not_none(spec.loader).exec_module(module)
        return module

    return wrapped


@pytest.fixture
def create_scope() -> Callable[..., Scope]:
    def inner(
        *,
        type: str = "http",
        app: Litestar | None = None,
        asgi: ASGIVersion | None = None,
        auth: Any = None,
        client: tuple[str, int] | None = ("testclient", 50000),
        extensions: dict[str, dict[object, object]] | None = None,
        http_version: str = "1.1",
        path: str = "/",
        path_params: dict[str, str] | None = None,
        query_string: str = "",
        root_path: str = "",
        route_handler: RouteHandlerType | None = None,
        scheme: str = "http",
        server: tuple[str, int | None] | None = ("testserver", 80),
        session: ScopeSession | None = None,
        state: dict[str, Any] | None = None,
        user: Any = None,
        **kwargs: dict[str, Any],
    ) -> Scope:
        scope = {
            "app": app,
            "asgi": asgi or {"spec_version": "2.0", "version": "3.0"},
            "auth": auth,
            "type": type,
            "path": path,
            "raw_path": path.encode(),
            "root_path": root_path,
            "scheme": scheme,
            "query_string": query_string.encode(),
            "client": client,
            "server": server,
            "method": "GET",
            "http_version": http_version,
            "extensions": extensions or {"http.response.template": {}},
            "state": state or {},
            "path_params": path_params or {},
            "route_handler": route_handler,
            "user": user,
            "session": session,
            **kwargs,
        }
        return cast("Scope", scope)

    return inner


@pytest.fixture
def scope(create_scope: Callable[..., Scope]) -> Scope:
    return create_scope()


@pytest.fixture()
async def sync_sqlalchemy_plugin(engine: Engine, session_maker: sessionmaker[Session]) -> SQLAlchemyPlugin:
    return SQLAlchemyPlugin(config=SQLAlchemySyncConfig(engine_instance=engine, session_maker=session_maker))


@pytest.fixture()
async def async_sqlalchemy_plugin(
    async_engine: AsyncEngine,
    async_session_maker: async_sessionmaker[AsyncSession],
) -> SQLAlchemyPlugin:
    return SQLAlchemyPlugin(
        config=SQLAlchemyAsyncConfig(engine_instance=async_engine, session_maker=async_session_maker),
    )


@pytest.fixture()
async def sync_app(sync_sqlalchemy_plugin: SQLAlchemyPlugin) -> Litestar:
    return Litestar(plugins=[sync_sqlalchemy_plugin])


@pytest.fixture()
async def async_app(async_sqlalchemy_plugin: SQLAlchemyPlugin) -> Litestar:
    return Litestar(plugins=[async_sqlalchemy_plugin])


@pytest.fixture()
async def sync_alembic_commands(sync_app: Litestar) -> AlembicCommands:
    return AlembicCommands(app=sync_app)


@pytest.fixture()
async def async_alembic_commands(async_app: Litestar) -> AlembicCommands:
    return AlembicCommands(app=async_app)


@pytest.fixture(params=[pytest.param("sync_alembic_commands"), pytest.param("async_alembic_commands")])
async def alembic_commands(request: FixtureRequest) -> AlembicCommands:
    return cast(AlembicCommands, request.getfixturevalue(request.param))


@pytest.fixture(params=[pytest.param("sync_app"), pytest.param("async_app")])
async def app(request: FixtureRequest) -> Litestar:
    return cast(Litestar, request.getfixturevalue(request.param))


@pytest.fixture()
def request_factory() -> RequestFactory:
    return RequestFactory()

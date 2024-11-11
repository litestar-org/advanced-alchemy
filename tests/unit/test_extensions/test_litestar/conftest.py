from __future__ import annotations

import importlib.util
import os
import random
import string
import sys
from collections.abc import AsyncGenerator, Generator
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Tuple, cast
from unittest.mock import ANY

import pytest
from litestar.app import Litestar
from litestar.dto import AbstractDTO, DTOField, Mark
from litestar.dto._backend import DTOBackend
from litestar.dto.data_structures import DTOFieldDefinition
from litestar.testing import RequestFactory
from litestar.types import (
    ASGIVersion,
    RouteHandlerType,
    Scope,
    ScopeSession,  # type: ignore
)
from litestar.types.empty import Empty
from litestar.typing import FieldDefinition
from pytest import FixtureRequest, MonkeyPatch
from sqlalchemy import Engine, NullPool, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from typing_extensions import TypeVar

from advanced_alchemy.config.common import GenericSQLAlchemyConfig
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin, SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.alembic import AlembicCommands


@pytest.fixture(autouse=True)
def reload_package() -> Generator[None, None, None]:
    yield
    GenericSQLAlchemyConfig._SESSION_SCOPE_KEY_REGISTRY = set()  # type: ignore
    GenericSQLAlchemyConfig._ENGINE_APP_STATE_KEY_REGISTRY = set()  # type: ignore
    GenericSQLAlchemyConfig._SESSIONMAKER_APP_STATE_KEY_REGISTRY = set()  # type: ignore


@pytest.fixture(autouse=True)
def reset_cached_dto_backends() -> Generator[None, None, None]:
    DTOBackend._seen_model_names = set()  # pyright: ignore[reportPrivateUsage]
    AbstractDTO._dto_backends = {}  # pyright: ignore[reportPrivateUsage]
    yield
    DTOBackend._seen_model_names = set()  # pyright: ignore[reportPrivateUsage]
    AbstractDTO._dto_backends = {}  # pyright: ignore[reportPrivateUsage]


@pytest.fixture(autouse=True)
async def disable_implicit_sync_warning() -> None:
    os.environ["LITESTAR_WARN_IMPLICIT_SYNC_TO_THREAD"] = "0"


@pytest.fixture
def int_factory() -> Generator[Callable[[], int], None, None]:
    yield lambda: 2


@pytest.fixture
def expected_field_defs(int_factory: Callable[[], int]) -> Generator[List[DTOFieldDefinition], None, None]:
    yield [
        DTOFieldDefinition.from_field_definition(
            field_definition=FieldDefinition.from_kwarg(
                annotation=int,
                name="a",
            ),
            model_name=ANY,
            default_factory=Empty,  # type: ignore[arg-type]
            dto_field=DTOField(),
        ),
        replace(
            DTOFieldDefinition.from_field_definition(
                field_definition=FieldDefinition.from_kwarg(
                    annotation=int,
                    name="b",
                ),
                model_name=ANY,
                default_factory=Empty,  # type: ignore[arg-type]
                dto_field=DTOField(mark=Mark.READ_ONLY),
            ),
            metadata=ANY,
            type_wrappers=ANY,
            raw=ANY,
            kwarg_definition=ANY,
        ),
        replace(
            DTOFieldDefinition.from_field_definition(
                field_definition=FieldDefinition.from_kwarg(
                    annotation=int,
                    name="c",
                ),
                model_name=ANY,
                default_factory=Empty,  # type: ignore[arg-type]
                dto_field=DTOField(),
            ),
            metadata=ANY,
            type_wrappers=ANY,
            raw=ANY,
            kwarg_definition=ANY,
        ),
        replace(
            DTOFieldDefinition.from_field_definition(
                field_definition=FieldDefinition.from_kwarg(
                    annotation=int,
                    name="d",
                    default=1,
                ),
                model_name=ANY,
                default_factory=Empty,  # type: ignore[arg-type]
                dto_field=DTOField(),
            ),
            metadata=ANY,
            type_wrappers=ANY,
            raw=ANY,
            kwarg_definition=ANY,
        ),
        replace(
            DTOFieldDefinition.from_field_definition(
                field_definition=FieldDefinition.from_kwarg(
                    annotation=int,
                    name="e",
                ),
                model_name=ANY,
                default_factory=int_factory,
                dto_field=DTOField(),
            ),
            metadata=ANY,
            type_wrappers=ANY,
            raw=ANY,
            kwarg_definition=ANY,
        ),
    ]


@pytest.fixture
def create_module(tmp_path: Path, monkeypatch: MonkeyPatch) -> Generator[Callable[[str], ModuleType], None, None]:
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

    yield wrapped


@pytest.fixture
def create_scope() -> Generator[Callable[..., Scope], None, None]:
    def inner(
        *,
        type: str = "http",
        app: Litestar | None = None,
        asgi: ASGIVersion | None = None,
        auth: Any = None,
        client: Tuple[str, int] | None = ("testclient", 50000),
        extensions: Dict[str, Dict[object, object]] | None = None,
        http_version: str = "1.1",
        path: str = "/",
        path_params: Dict[str, str] | None = None,
        query_string: str = "",
        root_path: str = "",
        route_handler: RouteHandlerType | None = None,
        scheme: str = "http",
        server: Tuple[str, int | None] | None = ("testserver", 80),
        session: ScopeSession | None = None,  # pyright: ignore[reportUnknownParameterType]
        state: Dict[str, Any] | None = None,
        user: Any = None,
        **kwargs: Dict[str, Any],
    ) -> Scope:
        scope: Dict[str, Any] = {
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

    yield inner  # pyright: ignore[reportUnknownVariableType]


@pytest.fixture
def scope(create_scope: Callable[..., Scope]) -> Generator[Scope, None, None]:
    yield create_scope()


@pytest.fixture()
def engine() -> Generator[Engine, None, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_engine("sqlite:///:memory:", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
async def sync_sqlalchemy_plugin(
    engine: Engine,
    session_maker: sessionmaker[Session] | None = None,
) -> AsyncGenerator[SQLAlchemyPlugin, None]:
    yield SQLAlchemyPlugin(config=SQLAlchemySyncConfig(engine_instance=engine, session_maker=session_maker))


@pytest.fixture()
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def async_sqlalchemy_plugin(
    async_engine: AsyncEngine,
    async_session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncGenerator[SQLAlchemyPlugin, None]:
    yield SQLAlchemyPlugin(
        config=SQLAlchemyAsyncConfig(engine_instance=async_engine, session_maker=async_session_maker),
    )


@pytest.fixture(params=[pytest.param("sync_sqlalchemy_plugin"), pytest.param("async_sqlalchemy_plugin")])
async def plugin(request: FixtureRequest) -> AsyncGenerator[SQLAlchemyPlugin, None]:
    yield cast(SQLAlchemyPlugin, request.getfixturevalue(request.param))


@pytest.fixture()
async def sync_app(sync_sqlalchemy_plugin: SQLAlchemyPlugin) -> AsyncGenerator[Litestar, None]:
    yield Litestar(plugins=[sync_sqlalchemy_plugin])


@pytest.fixture()
async def async_app(async_sqlalchemy_plugin: SQLAlchemyPlugin) -> AsyncGenerator[Litestar, None]:
    yield Litestar(plugins=[async_sqlalchemy_plugin])


@pytest.fixture()
async def sync_alembic_commands(sync_app: Litestar) -> AsyncGenerator[AlembicCommands, None]:
    yield AlembicCommands(app=sync_app)


@pytest.fixture()
async def async_alembic_commands(async_app: Litestar) -> AsyncGenerator[AlembicCommands, None]:
    yield AlembicCommands(app=async_app)


@pytest.fixture(params=[pytest.param("sync_alembic_commands"), pytest.param("async_alembic_commands")])
async def alembic_commands(request: FixtureRequest) -> AsyncGenerator[AlembicCommands, None]:
    yield cast(AlembicCommands, request.getfixturevalue(request.param))


@pytest.fixture(params=[pytest.param("sync_app"), pytest.param("async_app")])
async def app(request: FixtureRequest) -> AsyncGenerator[Litestar, None]:
    yield cast(Litestar, request.getfixturevalue(request.param))


@pytest.fixture()
def request_factory() -> Generator[RequestFactory, None, None]:
    yield RequestFactory()

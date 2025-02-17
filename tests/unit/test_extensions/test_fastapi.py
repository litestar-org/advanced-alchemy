import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Callable, Literal, Union, cast
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from pytest import FixtureRequest
from pytest_mock import MockerFixture
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from typing_extensions import assert_type

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

AnyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]
pytestmark = pytest.mark.xfail(
    condition=sys.version_info < (3, 9),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Marking 3.8 as an acceptable failure for now.",
)


@pytest.fixture()
def app() -> FastAPI:
    return FastAPI()


@pytest.fixture()
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app=app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture()
def sync_config() -> SQLAlchemySyncConfig:
    return SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")


@pytest.fixture()
def async_config() -> SQLAlchemyAsyncConfig:
    return SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")


@pytest.fixture(params=["sync_config", "async_config"])
def config(request: FixtureRequest) -> AnyConfig:
    return cast(AnyConfig, request.getfixturevalue(request.param))


@pytest.fixture()
def alchemy(config: AnyConfig, app: FastAPI) -> AdvancedAlchemy:
    return AdvancedAlchemy(config, app=app)


async def test_infer_types_from_config(async_config: SQLAlchemyAsyncConfig, sync_config: SQLAlchemySyncConfig) -> None:
    if TYPE_CHECKING:
        alchemy = AdvancedAlchemy(config=[async_config, sync_config])
        assert alchemy.get_sync_config() is sync_config
        assert alchemy.get_async_config() is async_config

        assert_type(alchemy.get_sync_engine(), Engine)
        assert_type(alchemy.get_async_engine(), AsyncEngine)

        assert_type(alchemy.get_sync_config().create_session_maker(), Callable[[], Session])
        assert_type(alchemy.get_async_config().create_session_maker(), Callable[[], AsyncSession])

        with alchemy.with_sync_session() as db_session:
            assert_type(db_session, Session)
        async with alchemy.with_async_session() as async_session:
            assert_type(async_session, AsyncSession)


def test_init_app_not_called_raises(config: SQLAlchemySyncConfig) -> None:
    alchemy = AdvancedAlchemy(config)
    with pytest.raises(ImproperConfigurationError):
        alchemy.app


def test_inject_sync_engine() -> None:
    app = FastAPI()
    mock = MagicMock()
    config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
    alchemy = AdvancedAlchemy(config=config, app=app)

    @app.get("/")
    def handler(engine: Annotated[Engine, Depends(alchemy.provide_engine())]) -> Response:
        mock(engine)
        return Response(status_code=200)

    with TestClient(app=app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        call_args = mock.call_args[0]
        assert call_args[0] is config.get_engine()


def test_inject_async_engine() -> None:
    app = FastAPI()
    mock = MagicMock()
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    alchemy = AdvancedAlchemy(config=config, app=app)

    @app.get("/")
    def handler(engine: Annotated[AsyncEngine, Depends(alchemy.provide_engine())]) -> Response:
        mock(engine)
        return Response(status_code=200)

    with TestClient(app=app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        call_args = mock.call_args[0]
        assert call_args[0] is config.get_engine()


def test_inject_sync_session() -> None:
    app = FastAPI()
    mock = MagicMock()
    config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
    alchemy = AdvancedAlchemy(config=config, app=app)
    SessionDependency = Annotated[Session, Depends(alchemy.get_sync_session)]

    def some_dependency(session: SessionDependency) -> None:  # pyright: ignore[reportInvalidTypeForm,reportMissingTypeArgument,reportUnknownParameterType]
        mock(session)

    @app.get("/")
    def handler(session: SessionDependency, something: Annotated[None, Depends(some_dependency)]) -> None:  # pyright: ignore[reportInvalidTypeForm,reportMissingTypeArgument,reportUnknownParameterType,reportUnknownArgumentType]
        mock(session)

    with TestClient(app=app) as client:
        client.get("/")
        assert mock.call_count == 2
        call_1_args = mock.call_args_list[0].args
        call_2_args = mock.call_args_list[1].args
        assert call_1_args[0] is call_2_args[0]
        call_1_session = call_1_args[0]
        call_2_session = call_2_args[0]
        assert isinstance(call_1_session, Session)
        assert call_1_session is call_2_session


def test_inject_async_session() -> None:
    app = FastAPI()
    mock = MagicMock()
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    alchemy = AdvancedAlchemy(config=config, app=app)
    SessionDependency = Annotated[AsyncSession, Depends(alchemy.get_async_session)]

    def some_dependency(session: SessionDependency) -> None:  # pyright: ignore[reportInvalidTypeForm,reportMissingTypeArgument,reportUnknownParameterType]
        mock(session)

    @app.get("/")
    def handler(session: SessionDependency, something: Annotated[None, Depends(some_dependency)]) -> None:  # pyright: ignore[reportInvalidTypeForm,reportMissingTypeArgument,reportUnknownParameterType,reportUnknownArgumentType]
        mock(session)

    with TestClient(app=app) as client:
        client.get("/")
        assert mock.call_count == 2
        call_1_args = mock.call_args_list[0].args
        call_2_args = mock.call_args_list[1].args
        assert call_1_args[0] is call_2_args[0]
        call_1_session = call_1_args[0]
        call_2_session = call_2_args[0]
        assert isinstance(call_1_session, AsyncSession)
        assert call_1_session is call_2_session


@pytest.mark.parametrize(
    "status_code", [200, 201, 202, 204, 206, 300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900]
)
@pytest.mark.parametrize("autocommit_strategy", ["manual", "autocommit", "autocommit_include_redirect"])
def test_sync_commit_strategies(
    mocker: MockerFixture,
    status_code: int,
    autocommit_strategy: Literal["manual", "autocommit", "autocommit_include_redirect"],
) -> None:
    app = FastAPI()
    config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", commit_mode=autocommit_strategy)
    alchemy = AdvancedAlchemy(config=config, app=app)
    mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")
    SessionDependency = Annotated[Session, Depends(alchemy.provide_session())]

    @app.get("/")
    def handler(session: SessionDependency) -> Response:  # pyright: ignore[reportInvalidTypeForm,reportMissingTypeArgument,reportUnknownParameterType]
        return Response(status_code=status_code)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code

        if autocommit_strategy == "manual":
            mock_commit.call_count = 0
            mock_close.call_count = 1
            mock_rollback.call_count = 0
        elif autocommit_strategy == "autocommit" and status_code < 300:
            mock_commit.call_count = 1
            mock_close.call_count = 1
            mock_rollback.call_count = 0
        elif autocommit_strategy == "autocommit" and status_code >= 300:
            mock_commit.call_count = 0
            mock_close.call_count = 1
            mock_rollback.call_count = 1
        elif autocommit_strategy == "autocommit_include_redirect" and status_code < 400:
            mock_commit.call_count = 1
            mock_close.call_count = 1
            mock_rollback.call_count = 0
        elif autocommit_strategy == "autocommit_include_redirect" and status_code >= 400:
            mock_commit.call_count = 0
            mock_close.call_count = 1
            mock_rollback.call_count = 1


@pytest.mark.parametrize(
    "status_code", [200, 201, 202, 204, 206, 300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900]
)
@pytest.mark.parametrize("autocommit_strategy", ["manual", "autocommit", "autocommit_include_redirect"])
def test_async_commit_strategies(
    mocker: MockerFixture,
    status_code: int,
    autocommit_strategy: Literal["manual", "autocommit", "autocommit_include_redirect"],
) -> None:
    app = FastAPI()
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", commit_mode=autocommit_strategy)
    alchemy = AdvancedAlchemy(config=config, app=app)
    mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
    mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
    mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")

    @app.get("/")
    def handler(session: Annotated[AsyncSession, Depends(alchemy.provide_session())]) -> Response:
        return Response(status_code=status_code)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code

        if autocommit_strategy == "manual":
            mock_commit.call_count = 0
            mock_close.call_count = 1
            mock_rollback.call_count = 0
        elif autocommit_strategy == "autocommit" and status_code < 300:
            mock_commit.call_count = 1
            mock_close.call_count = 1
            mock_rollback.call_count = 0
        elif autocommit_strategy == "autocommit" and status_code >= 300:
            mock_commit.call_count = 0
            mock_close.call_count = 1
            mock_rollback.call_count = 1
        elif autocommit_strategy == "autocommit_include_redirect" and status_code < 400:
            mock_commit.call_count = 1
            mock_close.call_count = 1
            mock_rollback.call_count = 0
        elif autocommit_strategy == "autocommit_include_redirect" and status_code >= 400:
            mock_commit.call_count = 0
            mock_close.call_count = 1
            mock_rollback.call_count = 1


@pytest.mark.parametrize("autocommit_strategy", ["manual", "autocommit", "autocommit_include_redirect"])
def test_sync_session_close_on_exception(
    mocker: MockerFixture,
    autocommit_strategy: Literal["manual", "autocommit", "autocommit_include_redirect"],
) -> None:
    app = FastAPI()
    config = SQLAlchemySyncConfig(
        connection_string="sqlite+pysqlite://",
        commit_mode=autocommit_strategy,
    )
    alchemy = AdvancedAlchemy(config=config, app=app)
    mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")

    def provide_session(request: Request) -> Session:
        return alchemy.get_sync_session(request)

    @app.get("/")
    def handler(sync_db_session: Annotated[Session, Depends(provide_session)]) -> str:
        raise HTTPException(status_code=500, detail="Intentional error for testing")

    with TestClient(app=app, raise_server_exceptions=False) as client:
        _ = client.get("/")
        assert _.status_code == 500
        assert _.json().get("detail") == "Intentional error for testing"
        mock_commit.call_count = 0
        mock_close.call_count = 1
        mock_rollback.call_count = 0


@pytest.mark.parametrize("autocommit_strategy", ["manual", "autocommit", "autocommit_include_redirect"])
def test_async_session_close_on_exception(
    mocker: MockerFixture,
    autocommit_strategy: Literal["manual", "autocommit", "autocommit_include_redirect"],
) -> None:
    app = FastAPI()
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite://",
        commit_mode=autocommit_strategy,
    )
    alchemy = AdvancedAlchemy(config=config, app=app)
    mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
    mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
    mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")

    def provide_session(request: Request) -> AsyncSession:
        return alchemy.get_async_session(request)

    @app.get("/")
    def handler(async_db_session: Annotated[AsyncSession, Depends(provide_session)]) -> str:
        raise HTTPException(status_code=500, detail="Intentional error for testing")

    with TestClient(app=app, raise_server_exceptions=False) as client:
        _ = client.get("/")
        assert _.status_code == 500
        assert _.json().get("detail") == "Intentional error for testing"
        mock_commit.call_count = 0
        mock_close.call_count = 1
        mock_rollback.call_count = 0


def test_multiple_sync_instances(app: FastAPI) -> None:
    mock = MagicMock()
    config_1 = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
    config_2 = SQLAlchemySyncConfig(connection_string="sqlite:///temp.db", bind_key="config_2")

    alchemy_1 = AdvancedAlchemy([config_1, config_2], app=app)

    def provide_engine_1() -> Engine:
        return alchemy_1.get_sync_engine()

    def provide_engine_2() -> Engine:
        return alchemy_1.get_sync_engine("config_2")

    @app.get("/")
    def handler(
        session_1: Annotated[Session, Depends(lambda: alchemy_1.provide_session())],
        session_2: Annotated[Session, Depends(lambda: alchemy_1.provide_session("config_2"))],
        engine_1: Annotated[Engine, Depends(lambda: alchemy_1.provide_engine())],
        engine_2: Annotated[Engine, Depends(lambda: alchemy_1.provide_engine("config_2"))],
    ) -> None:
        assert session_1 is not session_2
        assert engine_1 is not engine_2
        mock(session=session_1, engine=engine_1)
        mock(session=session_2, engine=engine_2)

    with TestClient(app=app) as client:
        client.get("/")
        assert alchemy_1.get_sync_config().bind_key != alchemy_1.get_sync_config("config_2").bind_key
        assert alchemy_1.get_sync_config().session_maker != alchemy_1.get_sync_config("config_2").session_maker

        assert alchemy_1.get_sync_config().get_engine() is not alchemy_1.get_sync_config("config_2").get_engine()
        assert (
            alchemy_1.get_sync_config().create_session_maker()
            is not alchemy_1.get_sync_config("config_2").create_session_maker()
        )
        assert mock.call_args_list[0].kwargs["session"] is not mock.call_args_list[1].kwargs["session"]
        assert mock.call_args_list[0].kwargs["engine"] is not mock.call_args_list[1].kwargs["engine"]


async def test_lifespan_startup_shutdown_called_fastapi(mocker: MockerFixture, app: FastAPI, config: AnyConfig) -> None:
    mock_startup = mocker.patch.object(AdvancedAlchemy, "on_startup")
    mock_shutdown = mocker.patch.object(AdvancedAlchemy, "on_shutdown")
    _alchemy = AdvancedAlchemy(config, app=app)

    with TestClient(app=app) as _client:  # TestClient context manager triggers lifespan events
        pass  # App starts up and shuts down within this context

    mock_startup.assert_called_once()
    mock_shutdown.assert_called_once()


async def test_lifespan_with_custom_lifespan_fastapi(mocker: MockerFixture, app: FastAPI, config: AnyConfig) -> None:
    mock_aa_startup = mocker.patch.object(AdvancedAlchemy, "on_startup")
    mock_aa_shutdown = mocker.patch.object(AdvancedAlchemy, "on_shutdown")
    mock_custom_startup = mocker.MagicMock()
    mock_custom_shutdown = mocker.MagicMock()

    @asynccontextmanager
    async def custom_lifespan(app_in: FastAPI) -> AsyncGenerator[None, None]:
        mock_custom_startup()
        yield
        mock_custom_shutdown()

    app.router.lifespan_context = custom_lifespan  # type: ignore[assignment] # Set a custom lifespan on the app
    _alchemy = AdvancedAlchemy(config, app=app)

    with TestClient(app=app) as _client:  # TestClient context manager triggers lifespan events
        pass  # App starts up and shuts down within this context

    mock_aa_startup.assert_called_once()
    mock_aa_shutdown.assert_called_once()
    mock_custom_startup.assert_called_once()
    mock_custom_shutdown.assert_called_once()

    # Optionally assert the order of calls if needed, e.g., using mocker.call_order

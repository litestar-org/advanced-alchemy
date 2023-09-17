from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Union, cast
from unittest.mock import MagicMock

import pytest
from pytest import FixtureRequest
from pytest_mock import MockerFixture
from sanic import HTTPResponse, Request, Sanic
from sanic_ext import Extend
from sanic_testing.testing import SanicTestClient
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from typing_extensions import assert_type

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.extensions.sanic import SanicAdvancedAlchemy

AnyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]


@pytest.fixture()
def app() -> Sanic:
    return Sanic("TestSanic")


@pytest.fixture()
def client(app: Sanic) -> SanicTestClient:
    return SanicTestClient(app=app)


@pytest.fixture()
def sync_config() -> SQLAlchemySyncConfig:
    return SQLAlchemySyncConfig(connection_string="sqlite+pysqlite://")


@pytest.fixture()
def async_config() -> SQLAlchemyAsyncConfig:
    return SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite://")


@pytest.fixture(params=["sync_config", "async_config"])
def config(request: FixtureRequest) -> AnyConfig:
    return cast(AnyConfig, request.getfixturevalue(request.param))


@pytest.fixture()
def alchemy(config: AnyConfig, app: Sanic) -> SanicAdvancedAlchemy:
    alchemy = SanicAdvancedAlchemy(sqlalchemy_config=config)
    Extend.register(alchemy)
    return alchemy


@pytest.fixture()
def mock_close(mocker: MockerFixture, config: AnyConfig) -> MagicMock:
    if isinstance(config, SQLAlchemySyncConfig):
        return mocker.patch("sqlalchemy.orm.Session.close")
    return mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")


@pytest.fixture()
def mock_commit(mocker: MockerFixture, config: AnyConfig) -> MagicMock:
    if isinstance(config, SQLAlchemySyncConfig):
        return mocker.patch("sqlalchemy.orm.Session.commit")
    return mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")


@pytest.fixture()
def mock_rollback(mocker: MockerFixture, config: AnyConfig) -> MagicMock:
    if isinstance(config, SQLAlchemySyncConfig):
        return mocker.patch("sqlalchemy.orm.Session.rollback")
    return mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")


def test_infer_types_from_config(async_config: SQLAlchemyAsyncConfig, sync_config: SQLAlchemySyncConfig) -> None:
    if TYPE_CHECKING:
        sync_alchemy = SanicAdvancedAlchemy(sqlalchemy_config=sync_config)
        async_alchemy = SanicAdvancedAlchemy(sqlalchemy_config=async_config)

        assert_type(sync_alchemy.get_engine(), Engine)
        assert_type(async_alchemy.get_engine(), AsyncEngine)

        assert_type(sync_alchemy.get_sessionmaker(), Callable[[], Session])
        assert_type(async_alchemy.get_sessionmaker(), Callable[[], AsyncSession])


def test_inject_engine(app: Sanic, alchemy: SanicAdvancedAlchemy) -> None:
    @app.get("/")
    async def handler(request: Request) -> HTTPResponse:
        assert isinstance(getattr(request.app.ctx, alchemy.engine_key), (Engine, AsyncEngine))
        return HTTPResponse(status=200)

    client = SanicTestClient(app=app)
    assert client.get("/")[1].status == 200


"""
def test_inject_session(app: Sanic, alchemy: SanicAdvancedAlchemy, client: SanicTestClient) -> None:
    if isinstance(alchemy.sqlalchemy_config, SQLAlchemyAsyncConfig):
        app.ext.add_dependency(AsyncSession, alchemy.get_session_from_request)

        @app.get("/")
        async def handler(request: Request) -> HTTPResponse:
            assert isinstance(getattr(request.ctx, alchemy.session_key), AsyncSession)
            return HTTPResponse(status=200)

        assert client.get("/")[1].status == 200
    else:
        app.ext.add_dependency(Session, alchemy.get_session_from_request)

        @app.get("/")
        async def handler(request: Request) -> HTTPResponse:
            assert isinstance(getattr(request.ctx, alchemy.session_key), Session)
            return HTTPResponse(status=200)

        assert client.get("/")[1].status == 200
"""

"""
def test_session_no_autocommit(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
) -> None:
    alchemy.autocommit_strategy = None
    app.ext.add_dependency(Session, alchemy.get_session)

    @app.get("/")
    def handler(session: Session) -> None:
        pass

    assert client.get("/")[1].status == 200
    mock_commit.assert_not_called()
    mock_close.assert_called_once()
"""

"""
def test_session_autocommit_always(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
) -> None:
    alchemy.autocommit_strategy = "always"
    app.ext.add_dependency(Session, alchemy.get_session)

    @app.get("/")
    def handler(session: Session) -> None:
        pass

    assert client.get("/")[1].status == 200
    mock_commit.assert_called_once()
    mock_close.assert_called_once()
"""

"""
@pytest.mark.parametrize("status", [200, 201, 202, 204, 206])
def test_session_autocommit_match_status(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
    mock_rollback: MagicMock,
    status: int,
) -> None:
    alchemy.autocommit_strategy = "match_status"
    app.ext.add_dependency(Session, alchemy.get_session)

    @app.get("/")
    def handler(session: Session) -> HTTPResponse:
        return HTTPResponse(status=status)

    client.get("/")
    mock_commit.assert_called_once()
    mock_close.assert_called_once()
    mock_rollback.assert_not_called()
"""

"""
@pytest.mark.parametrize("status", [300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900])
def test_session_autocommit_rollback_for_status(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
    mock_rollback: MagicMock,
    status: int,
) -> None:
    alchemy.autocommit_strategy = "match_status"
    app.ext.add_dependency(Session, alchemy.get_session)

    @app.get("/")
    def handler(session: Session) -> HTTPResponse:
        return HTTPResponse(status=status)

    client.get("/")
    mock_commit.assert_not_called()
    mock_close.assert_called_once()
    mock_rollback.assert_called_once()
"""

"""
@pytest.mark.parametrize("autocommit_strategy", ["always", "match_status"])
def test_session_autocommit_close_on_exception(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
    autocommit_strategy: CommitStrategy,
) -> None:
    alchemy.autocommit_strategy = autocommit_strategy
    mock_commit.side_effect = ValueError
    app.ext.add_dependency(Session, alchemy.get_session)

    @app.get("/")
    def handler(session: Session) -> None:
        pass

    client.get("/")
    mock_commit.assert_called_once()
    mock_close.assert_called_once()
"""

"""
def test_multiple_instances(app: Sanic) -> None:
    mock = MagicMock()
    config_1 = SQLAlchemySyncConfig(connection_string="sqlite+aiosqlite://")
    config_2 = SQLAlchemySyncConfig(connection_string="sqlite+aiosqlite:///test.db")

    alchemy_1 = SanicAdvancedAlchemy(sqlalchemy_config=config_1)

    alchemy_2 = SanicAdvancedAlchemy(
        sqlalchemy_config=config_2,
        engine_key="other_engine",
        session_key="other_session",
        session_maker_key="other_sessionmaker",
    )
    Extend.register(alchemy_1)
    Extend.register(alchemy_2)
    app.ext.add_dependency(Session, alchemy_1.get_session)
    app.ext.add_dependency(Session, alchemy_2.get_session)
    app.ext.add_dependency(Engine, alchemy_1.get_engine)
    app.ext.add_dependency(Engine, alchemy_2.get_engine)

    @app.get("/")
    async def handler(
        session_1: Session,
        session_2: Session,
        engine_1: Engine,
        engine_2: Engine,
    ) -> None:
        assert session_1 != session_2
        assert engine_1 != engine_2
        mock(session=session_1, engine=engine_1)
        mock(session=session_2, engine=engine_2)

    client = SanicTestClient(app=app)
    _response = client.get("/")

    assert alchemy_1.engine_key != alchemy_2.engine_key
    assert alchemy_1.session_maker_key != alchemy_2.session_maker_key
    assert alchemy_1.session_key != alchemy_2.session_key

    assert alchemy_1.get_engine() is not alchemy_2.get_engine()
    assert alchemy_1.get_sessionmaker() is not alchemy_2.get_sessionmaker()
"""

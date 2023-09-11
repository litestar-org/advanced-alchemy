from typing import TYPE_CHECKING, Annotated, Generator, Union, cast
from unittest.mock import MagicMock

import pytest
from pytest import FixtureRequest
from pytest_mock import MockerFixture
from sanic import HTTPResponse, Sanic
from sanic_ext import Extend
from sanic_testing.testing import SanicTestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from typing_extensions import Callable, assert_type

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.config.types import CommitStrategy
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.sanic import SanicAdvancedAlchemy

AnyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]


@pytest.fixture()
def app() -> Sanic:
    return Sanic("TestSanic")


@pytest.fixture()
def client(app: Sanic) -> Generator[SanicTestClient, None, None]:
    with SanicTestClient(app=app, raise_server_exceptions=False) as client:
        yield client


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


def test_init_app_not_called_raises(client: SanicTestClient, config: SQLAlchemySyncConfig) -> None:
    alchemy = SanicAdvancedAlchemy(sqlalchemy_config=config)
    with pytest.raises(ImproperConfigurationError):
        alchemy.app


def test_inject_engine(app: Sanic) -> None:
    mock = MagicMock()
    config = SQLAlchemySyncConfig(engine_instance=create_engine("sqlite+aiosqlite://"))
    alchemy = SanicAdvancedAlchemy(sqlalchemy_config=config)

    @app.get("/")
    def handler(engine: Annotated[Engine, Depends(alchemy.get_engine)]) -> None:
        mock(engine)

    with SanicTestClient(app=app) as client:
        assert client.get("/").status_code == 200
        assert mock.call_args[0][0] is config.engine_instance


def test_inject_session(app: Sanic, alchemy: SanicAdvancedAlchemy, client: SanicTestClient) -> None:
    mock = MagicMock()
    SessionDependency = Annotated[Session, Depends(alchemy.get_session)]

    def some_dependency(session: SessionDependency) -> None:
        mock(session)

    @app.get("/")
    def handler(session: SessionDependency, something: Annotated[None, Depends(some_dependency)]) -> None:
        mock(session)

    assert client.get("/").status_code == 200
    assert mock.call_count == 2
    assert isinstance(
        mock.call_args_list[0].args[0],
        AsyncSession if isinstance(alchemy.config, SQLAlchemyAsyncConfig) else Session,
    )
    assert mock.call_args_list[1].args[0] is mock.call_args_list[0].args[0]


def test_session_no_autocommit(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
) -> None:
    alchemy.autocommit_strategy = None

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> None:
        pass

    assert client.get("/").status_code == 200
    mock_commit.assert_not_called()
    mock_close.assert_called_once()


def test_session_autocommit_always(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
) -> None:
    alchemy.autocommit_strategy = "always"

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> None:
        pass

    assert client.get("/").status_code == 200
    mock_commit.assert_called_once()
    mock_close.assert_called_once()


@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 206])
def test_session_autocommit_match_status(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
    mock_rollback: MagicMock,
    status_code: int,
) -> None:
    alchemy.autocommit_strategy = "match_status"

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> HTTPResponse:
        return HTTPResponse(status=status_code)

    client.get("/")
    mock_commit.assert_called_once()
    mock_close.assert_called_once()
    mock_rollback.assert_not_called()


@pytest.mark.parametrize("status_code", [300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900])
def test_session_autocommit_rollback_for_status(
    app: Sanic,
    alchemy: SanicAdvancedAlchemy,
    client: SanicTestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
    mock_rollback: MagicMock,
    status_code: int,
) -> None:
    alchemy.autocommit_strategy = "match_status"

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> HTTPResponse:
        return HTTPResponse(status=status_code)

    client.get("/")
    mock_commit.assert_not_called()
    mock_close.assert_called_once()
    mock_rollback.assert_called_once()


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

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> None:
        pass

    client.get("/")
    mock_commit.assert_called_once()
    mock_close.assert_called_once()


def test_multiple_instances(app: Sanic) -> None:
    mock = MagicMock()
    config_1 = SQLAlchemySyncConfig(connection_string="sqlite+aiosqlite://")
    config_2 = SQLAlchemySyncConfig(connection_string="sqlite+aiosqlite:///test.db")

    alchemy_1 = SanicAdvancedAlchemy(sqlalchemy_config=config_1)

    alchemy_2 = SanicAdvancedAlchemy(sqlalchemy_config=config_2)

    @app.get("/")
    def handler(
        session_1: Session = Depends(alchemy_1.get_session),
        session_2: Session = Depends(alchemy_2.get_session),
        engine_1: Engine = Depends(alchemy_1.get_engine),
        engine_2: Engine = Depends(alchemy_2.get_engine),
    ) -> None:
        mock(session=session_1, engine=engine_1)
        mock(session=session_2, engine=engine_2)

    with SanicTestClient(app=app) as client:
        client.get("/")

        assert alchemy_1.engine_key != alchemy_2.engine_key
        assert alchemy_1.sessionmaker_key != alchemy_2.sessionmaker_key
        assert alchemy_1.session_key != alchemy_2.session_key

        assert alchemy_1.get_engine() is not alchemy_2.get_engine()
        assert alchemy_1.get_sessionmaker() is not alchemy_2.get_sessionmaker()
        assert mock.call_args_list[0].kwargs["session"] is not mock.call_args_list[1].kwargs["session"]
        assert mock.call_args_list[0].kwargs["engine"] is not mock.call_args_list[1].kwargs["engine"]

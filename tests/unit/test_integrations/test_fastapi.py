from typing import Annotated, Generator
from unittest.mock import MagicMock

import pytest
from advanced_alchemy.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.integrations.fastapi import FastAPIAdvancedAlchemy
from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from sqlalchemy import Engine
from sqlalchemy.orm import Session


@pytest.fixture()
def app() -> FastAPI:
    return FastAPI()


@pytest.fixture()
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app=app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture()
def config() -> SQLAlchemySyncConfig:
    return SQLAlchemySyncConfig(connection_string="sqlite+aiosqlite://")


@pytest.fixture()
def alchemy(config: SQLAlchemySyncConfig, app: FastAPI) -> FastAPIAdvancedAlchemy:
    alchemy = FastAPIAdvancedAlchemy(config=config)
    alchemy.init_app(app)
    return alchemy


def test_inject_engine(app: FastAPI, alchemy: FastAPIAdvancedAlchemy, client: TestClient) -> None:
    mock = MagicMock()

    @app.get("/")
    def handler(engine: Annotated[Engine, Depends(alchemy.get_engine)]) -> None:
        mock(engine)

    assert client.get("/").status_code == 200
    assert mock.call_args[0][0] is alchemy.config.create_engine()


def test_inject_session(app: FastAPI, alchemy: FastAPIAdvancedAlchemy, client: TestClient) -> None:
    mock = MagicMock()
    SessionDependency = Annotated[Session, Depends(alchemy.get_session)]

    def some_dependency(session: SessionDependency) -> None:
        mock(session)

    @app.get("/")
    def handler(session: SessionDependency, something: Annotated[None, Depends(some_dependency)]) -> None:
        mock(session)

    assert client.get("/").status_code == 200
    assert mock.call_count == 2
    assert isinstance(mock.call_args_list[0].args[0], Session)
    assert mock.call_args_list[1].args[0] is mock.call_args_list[0].args[0]


@pytest.fixture()
def mock_commit(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("sqlalchemy.orm.Session.commit")


@pytest.mark.parametrize("autocommit", [True, False])
def test_session_autocommit(
    app: FastAPI,
    alchemy: FastAPIAdvancedAlchemy,
    client: TestClient,
    mock_commit: MagicMock,
    autocommit: bool,
) -> None:
    alchemy.autocommit = autocommit

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> None:
        pass

    assert client.get("/").status_code == 200
    if autocommit:
        mock_commit.assert_called_once()
    else:
        mock_commit.assert_not_called()


@pytest.mark.parametrize("status_code", range(200, 300))
def test_session_autocommit_for_status(
    app: FastAPI,
    alchemy: FastAPIAdvancedAlchemy,
    client: TestClient,
    mock_commit: MagicMock,
    mocker: MockerFixture,
    status_code: int,
) -> None:
    alchemy.autocommit = True
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> Response:
        return Response(status_code=status_code)

    client.get("/")
    mock_commit.assert_called_once()
    mock_close.assert_called_once()
    mock_rollback.assert_not_called()


@pytest.mark.parametrize("status_code", [*list(range(300, 501))])
def test_session_autocommit_rollback_for_status(
    app: FastAPI,
    alchemy: FastAPIAdvancedAlchemy,
    client: TestClient,
    mock_commit: MagicMock,
    mocker: MockerFixture,
    status_code: int,
) -> None:
    alchemy.autocommit = True
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> Response:
        return Response(status_code=status_code)

    client.get("/")
    mock_commit.assert_not_called()
    mock_close.assert_called_once()
    mock_rollback.assert_called_once()


def test_session_autocommit_close_on_exception(
    app: FastAPI,
    alchemy: FastAPIAdvancedAlchemy,
    client: TestClient,
    mock_commit: MagicMock,
    mocker: MockerFixture,
) -> None:
    alchemy.autocommit = True
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_commit.side_effect = ValueError

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> None:
        pass

    client.get("/")
    mock_commit.assert_called_once()
    mock_close.assert_called_once()

import sys
from typing import TYPE_CHECKING, Callable, Generator, Union, cast
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pytest import FixtureRequest
from pytest_mock import MockerFixture
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from typing_extensions import Annotated, assert_type

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.starlette import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

AnyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]


@pytest.fixture()
def app() -> Starlette:
    return Starlette()


@pytest.fixture()
def client(app: Starlette) -> Generator[TestClient, None, None]:
    with TestClient(app=app, raise_server_exceptions=False) as client:
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
def alchemy(config: AnyConfig, app: Starlette) -> Generator[AdvancedAlchemy, None, None]:
    alchemy = AdvancedAlchemy(config, app=app)
    yield alchemy


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


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
def test_infer_types_from_config(async_config: SQLAlchemyAsyncConfig, sync_config: SQLAlchemySyncConfig) -> None:
    if TYPE_CHECKING:
        sync_alchemy = AdvancedAlchemy(config=sync_config)
        async_alchemy = AdvancedAlchemy(config=async_config)

        assert_type(sync_alchemy.get_engine(), Engine)
        assert_type(async_alchemy.get_engine(), AsyncEngine)

        assert_type(sync_alchemy.get_sessionmaker(), Callable[[], Session])
        assert_type(async_alchemy.get_sessionmaker(), Callable[[], AsyncSession])

        request = Request(scope={})

        assert_type(sync_alchemy.get_session(request), Session)
        assert_type(async_alchemy.get_session(request), AsyncSession)


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
def test_init_app_not_called_raises(client: TestClient, config: SQLAlchemySyncConfig) -> None:
    alchemy = AdvancedAlchemy(config)
    with pytest.raises(ImproperConfigurationError):
        alchemy.app


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
def test_inject_engine(app: Starlette) -> None:
    mock = MagicMock()
    config = SQLAlchemySyncConfig(engine_instance=create_engine("sqlite+aiosqlite://"))
    alchemy = AdvancedAlchemy(config=config, app=app)

    @app.get("/")
    def handler(engine: Annotated[Engine, Depends(alchemy.get_engine)]) -> None:
        mock(engine)

    with TestClient(app=app) as client:
        assert client.get("/").status_code == 200
        assert mock.call_args[0][0] is config.engine_instance


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
def test_inject_session(app: Starlette, alchemy: AdvancedAlchemy, client: TestClient) -> None:
    mock = MagicMock()
    SessionDependency = Annotated[Session, Depends(alchemy.get_session)]

    def some_dependency(session: SessionDependency) -> None:  # pyright: ignore[reportInvalidTypeForm]
        mock(session)

    @app.get("/")
    def handler(session: SessionDependency, something: Annotated[None, Depends(some_dependency)]) -> None:  # pyright: ignore[reportInvalidTypeForm]
        mock(session)

    assert client.get("/").status_code == 200
    assert mock.call_count == 2
    call_1_session = mock.call_args_list[0].args[0]
    call_2_session = mock.call_args_list[1].args[0]
    assert isinstance(
        call_1_session,
        AsyncSession if isinstance(alchemy.config, SQLAlchemyAsyncConfig) else Session,
    )
    assert call_1_session is call_2_session


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
def test_session_no_autocommit(
    app: Starlette,
    alchemy: AdvancedAlchemy,
    client: TestClient,
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


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
def test_session_autocommit_always(
    app: Starlette,
    alchemy: AdvancedAlchemy,
    client: TestClient,
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


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 206])
def test_session_autocommit_match_status(
    app: Starlette,
    alchemy: AdvancedAlchemy,
    client: TestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
    mock_rollback: MagicMock,
    status_code: int,
) -> None:
    alchemy.autocommit_strategy = "match_status"

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> Response:
        return Response(status_code=status_code)

    client.get("/")
    mock_commit.assert_called_once()
    mock_close.assert_called_once()
    mock_rollback.assert_not_called()


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
@pytest.mark.parametrize("status_code", [300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900])
def test_session_autocommit_rollback_for_status(
    app: Starlette,
    alchemy: AdvancedAlchemy,
    client: TestClient,
    mock_commit: MagicMock,
    mock_close: MagicMock,
    mock_rollback: MagicMock,
    status_code: int,
) -> None:
    alchemy.autocommit_strategy = "match_status"

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.get_session)]) -> Response:
        return Response(status_code=status_code)

    client.get("/")
    mock_commit.assert_not_called()
    mock_close.assert_called_once()
    mock_rollback.assert_called_once()


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
@pytest.mark.parametrize("autocommit_strategy", ["always", "match_status"])
def test_session_autocommit_close_on_exception(
    app: Starlette,
    alchemy: AdvancedAlchemy,
    client: TestClient,
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


@pytest.mark.xfail(
    condition=sys.version_info < (3, 8),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Skipping on 3.8 for now until this is resolved.",
)
def test_multiple_instances(app: Starlette) -> None:
    mock = MagicMock()
    config_1 = SQLAlchemySyncConfig(connection_string="sqlite+aiosqlite://")
    config_2 = SQLAlchemySyncConfig(connection_string="sqlite+aiosqlite:///test.db")

    alchemy_1 = AdvancedAlchemy(config_1, app=app)

    alchemy_2 = AdvancedAlchemy(config_2, app=app)

    @app.get("/")
    def handler(
        session_1: Annotated[Session, Depends(alchemy_1.get_session)],
        session_2: Annotated[Session, Depends(alchemy_2.get_session)],
        engine_1: Annotated[Engine, Depends(alchemy_1.get_engine)],
        engine_2: Annotated[Engine, Depends(alchemy_2.get_engine)],
    ) -> None:
        mock(session=session_1, engine=engine_1)
        mock(session=session_2, engine=engine_2)

    with TestClient(app=app) as client:
        client.get("/")

        assert alchemy_1.engine_key != alchemy_2.engine_key
        assert alchemy_1.sessionmaker_key != alchemy_2.sessionmaker_key
        assert alchemy_1.session_key != alchemy_2.session_key

        assert alchemy_1.get_engine() is not alchemy_2.get_engine()
        assert alchemy_1.get_sessionmaker() is not alchemy_2.get_sessionmaker()
        assert mock.call_args_list[0].kwargs["session"] is not mock.call_args_list[1].kwargs["session"]
        assert mock.call_args_list[0].kwargs["engine"] is not mock.call_args_list[1].kwargs["engine"]

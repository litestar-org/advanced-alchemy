from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Callable, Union, cast
from unittest.mock import MagicMock

import pytest
from pytest import FixtureRequest
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from typing_extensions import Literal, assert_type

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.starlette import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

if TYPE_CHECKING:
    from pytest import FixtureRequest
    from pytest_mock import MockerFixture


AnyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]
pytestmark = pytest.mark.xfail(
    condition=sys.version_info < (3, 9),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities on various versions that have not been yanked.  Marking 3.8 as an acceptable failure for now.",
)


@pytest.fixture()
def app() -> Starlette:
    return Starlette()


@pytest.fixture()
def client(app: Starlette) -> Generator[TestClient, None, None]:
    with TestClient(app=app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture()
def sync_config() -> SQLAlchemySyncConfig:
    return SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:")


@pytest.fixture()
def async_config() -> SQLAlchemyAsyncConfig:
    return SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")


@pytest.fixture(params=["sync_config", "async_config"])
def config(request: FixtureRequest) -> AnyConfig:
    return cast(AnyConfig, request.getfixturevalue(request.param))


@pytest.fixture()
def alchemy(config: AnyConfig, app: Starlette) -> Generator[AdvancedAlchemy, None, None]:
    alchemy = AdvancedAlchemy(config, app=app)
    yield alchemy


@pytest.fixture()
def multi_alchemy(app: Starlette) -> Generator[AdvancedAlchemy, None, None]:
    alchemy = AdvancedAlchemy(
        [
            SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", bind_key="sync"),
            SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
        ],
        app=app,
    )
    yield alchemy


async def test_infer_types_from_config(async_config: SQLAlchemyAsyncConfig, sync_config: SQLAlchemySyncConfig) -> None:
    if TYPE_CHECKING:
        sync_alchemy = AdvancedAlchemy([sync_config])
        async_alchemy = AdvancedAlchemy([async_config])

        assert_type(sync_alchemy.get_sync_engine(), Engine)
        assert_type(async_alchemy.get_async_engine(), AsyncEngine)

        assert_type(sync_alchemy.get_sync_config().create_session_maker(), Callable[[], Session])
        assert_type(async_alchemy.get_async_config().create_session_maker(), Callable[[], AsyncSession])

        with sync_alchemy.with_sync_session() as session:
            assert_type(session, Session)
        async with async_alchemy.with_async_session() as session:
            assert_type(session, AsyncSession)


def test_init_app_not_called_raises(client: TestClient, config: SQLAlchemySyncConfig) -> None:
    alchemy = AdvancedAlchemy(config)
    with pytest.raises(ImproperConfigurationError):
        alchemy.app


def test_inject_engine(app: Starlette) -> None:
    mock = MagicMock()
    config = SQLAlchemySyncConfig(engine_instance=create_engine("sqlite+aiosqlite://"))
    alchemy = AdvancedAlchemy(config=config, app=app)

    async def handler(request: Request) -> Response:
        engine = alchemy.get_engine()
        mock(engine)
        return Response(status_code=200)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        assert client.get("/").status_code == 200
        assert mock.call_args[0][0] is config.engine_instance


def test_inject_session(app: Starlette, alchemy: AdvancedAlchemy, client: TestClient) -> None:
    mock = MagicMock()

    async def handler(request: Request) -> Response:
        session = alchemy.get_session(request)
        mock(session)
        return Response(status_code=200)

    app.router.routes.append(Route("/", endpoint=handler))

    call = client.get("/")
    assert call.status_code == 200
    assert mock.call_count == 1
    call_1_session = mock.call_args_list[0].args[0]
    assert isinstance(
        call_1_session,
        AsyncSession if isinstance(alchemy.config[0], SQLAlchemyAsyncConfig) else Session,
    )


def test_session_no_autocommit(
    app: Starlette,
    alchemy: AdvancedAlchemy,
    client: TestClient,
    mocker: MockerFixture,
) -> None:
    if isinstance(alchemy.config[0], SQLAlchemyAsyncConfig):
        mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
        mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
    else:
        mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
        mock_close = mocker.patch("sqlalchemy.orm.Session.close")

    app.middleware_stack = app.build_middleware_stack()

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=200)

    app.router.routes.append(Route("/", endpoint=handler))

    assert client.get("/").status_code == 200
    mock_commit.assert_not_called()
    mock_close.assert_called_once()


@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 206])
def test_sync_session_autocommit_success_status(
    mocker: MockerFixture,
    status_code: int,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")
    app = Starlette()
    config = SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", commit_mode="autocommit")
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        _ = client.get("/")
        mock_commit.assert_called_once()
        mock_close.assert_called_once()
        mock_rollback.assert_not_called()


@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 206])
def test_sync_session_autocommit_include_redirect_success_status(
    mocker: MockerFixture,
    status_code: int,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")
    app = Starlette()
    config = SQLAlchemySyncConfig(
        connection_string="sqlite+pysqlite:///:memory:", commit_mode="autocommit_include_redirect"
    )
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        _ = client.get("/")
        mock_commit.assert_called_once()
        mock_close.assert_called_once()
        mock_rollback.assert_not_called()


@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 206])
def test_async_session_autocommit_success_status(
    mocker: MockerFixture,
    status_code: int,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
    mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
    mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")
    app = Starlette()
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", commit_mode="autocommit")
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        _ = client.get("/")
        mock_commit.assert_called_once()
        mock_close.assert_called_once()
        mock_rollback.assert_not_called()


@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 206])
def test_async_session_autocommit_include_redirect_success_status(
    mocker: MockerFixture,
    status_code: int,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
    mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
    mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")
    app = Starlette()
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:", commit_mode="autocommit_include_redirect"
    )
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        _ = client.get("/")
        mock_commit.assert_called_once()
        mock_close.assert_called_once()
        mock_rollback.assert_not_called()


@pytest.mark.parametrize("status_code", [300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900])
def test_sync_session_autocommit_rollback_for_status(
    status_code: int,
    mocker: MockerFixture,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")
    app = Starlette()
    config = SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", commit_mode="autocommit")
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code
        if status_code >= 300:
            assert mock_commit.call_count == 0
            assert mock_rollback.call_count == 1
            assert mock_close.call_count == 1
        else:
            assert mock_commit.call_count == 1
            assert mock_close.call_count == 1
            assert mock_rollback.call_count == 0


@pytest.mark.parametrize("status_code", [300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900])
def test_sync_session_autocommit_include_redirect_rollback_for_status(
    status_code: int,
    mocker: MockerFixture,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")
    app = Starlette()
    config = SQLAlchemySyncConfig(
        connection_string="sqlite+pysqlite:///:memory:", commit_mode="autocommit_include_redirect"
    )
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code
        if status_code < 400:
            assert mock_commit.call_count == 1
            assert mock_rollback.call_count == 0
            assert mock_close.call_count == 1
        else:
            assert mock_commit.call_count == 0
            assert mock_rollback.call_count == 1
            assert mock_close.call_count == 1


@pytest.mark.parametrize("status_code", [300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900])
def test_async_session_autocommit_rollback_for_status(
    status_code: int,
    mocker: MockerFixture,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
    mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
    mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")
    app = Starlette()
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", commit_mode="autocommit")
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code
        if status_code >= 300:
            assert mock_commit.call_count == 0
            assert mock_rollback.call_count == 1
            assert mock_close.call_count == 1
        else:
            assert mock_commit.call_count == 1
            assert mock_close.call_count == 1
            assert mock_rollback.call_count == 0


@pytest.mark.parametrize("status_code", [300, 301, 305, 307, 308, 400, 401, 404, 450, 500, 900])
def test_async_session_autocommit_include_redirect_rollback_for_status(
    status_code: int,
    mocker: MockerFixture,
) -> None:
    mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
    mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
    mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")
    app = Starlette()
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:", commit_mode="autocommit_include_redirect"
    )
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=status_code)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code
        if status_code >= 400:
            assert mock_commit.call_count == 0
            assert mock_rollback.call_count == 1
            assert mock_close.call_count == 1
        else:
            assert mock_commit.call_count == 1
            assert mock_rollback.call_count == 0
            assert mock_close.call_count == 1


@pytest.mark.parametrize("autocommit_strategy", ["autocommit", "autocommit_include_redirect"])
def test_sync_session_autocommit_close_on_exception(
    mocker: MockerFixture,
    autocommit_strategy: Literal["autocommit", "autocommit_include_redirect"],
) -> None:
    mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
    mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")
    mock_close = mocker.patch("sqlalchemy.orm.Session.close")

    async def http_exception(request: Request, exc: HTTPException) -> Response:
        return Response(status_code=exc.status_code)

    app = Starlette(exception_handlers={HTTPException: http_exception})  # type: ignore
    config = SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", commit_mode=autocommit_strategy)
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> None:
        _session = alchemy.get_session(request)
        raise HTTPException(status_code=500, detail="Intentional error for testing")

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        client.get("/")
        mock_commit.assert_not_called()
        mock_rollback.assert_called_once()
        mock_close.assert_called_once()


@pytest.mark.parametrize("autocommit_strategy", ["autocommit", "autocommit_include_redirect"])
async def test_async_session_autocommit_close_on_exception(
    mocker: MockerFixture,
    autocommit_strategy: Literal["autocommit", "autocommit_include_redirect"],
) -> None:
    mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
    mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")
    mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")

    async def http_exception(request: Request, exc: HTTPException) -> Response:
        return Response(status_code=exc.status_code)

    app = Starlette(exception_handlers={HTTPException: http_exception})  # type: ignore
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", commit_mode=autocommit_strategy)
    alchemy = AdvancedAlchemy(config, app=app)

    async def handler(request: Request) -> None:
        _session = alchemy.get_session(request)
        raise HTTPException(status_code=500, detail="Intentional error for testing")

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        client.get("/")
        mock_commit.assert_not_called()
        mock_rollback.assert_called_once()
        mock_close.assert_called_once()


def test_multiple_instances(app: Starlette) -> None:
    mock = MagicMock()
    config_1 = SQLAlchemySyncConfig(connection_string="sqlite:///other.db")
    config_2 = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.db", bind_key="other")

    alchemy_1 = AdvancedAlchemy([config_1, config_2], app=app)

    async def handler(request: Request) -> Response:
        session_1 = alchemy_1.get_sync_session(request)
        engine_1 = alchemy_1.get_sync_engine()
        session_2 = alchemy_1.get_async_session(request, key="other")
        engine_2 = alchemy_1.get_async_engine(key="other")
        assert session_1 is not session_2  # type: ignore
        assert engine_1 is not engine_2
        mock(session=session_1, engine=engine_1)
        mock(session=session_2, engine=engine_2)
        return Response(status_code=200)

    app.router.routes.append(Route("/", endpoint=handler))

    with TestClient(app=app) as client:
        client.get("/")

        assert alchemy_1.get_sync_engine() is not alchemy_1.get_async_engine("other")


async def test_lifespan_startup_shutdown_called_starlette(
    mocker: MockerFixture, app: Starlette, config: AnyConfig
) -> None:
    mock_startup = mocker.patch.object(AdvancedAlchemy, "on_startup")
    mock_shutdown = mocker.patch.object(AdvancedAlchemy, "on_shutdown")
    _alchemy = AdvancedAlchemy(config, app=app)

    with TestClient(app=app) as _client:  # TestClient context manager triggers lifespan events
        pass  # App starts up and shuts down within this context

    mock_startup.assert_called_once()
    mock_shutdown.assert_called_once()


async def test_lifespan_with_custom_lifespan_starlette(
    mocker: MockerFixture, app: Starlette, config: AnyConfig
) -> None:
    mock_aa_startup = mocker.patch.object(AdvancedAlchemy, "on_startup")
    mock_aa_shutdown = mocker.patch.object(AdvancedAlchemy, "on_shutdown")
    mock_custom_startup = mocker.MagicMock()
    mock_custom_shutdown = mocker.MagicMock()

    @asynccontextmanager
    async def custom_lifespan(app_in: Starlette) -> AsyncGenerator[None, None]:
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

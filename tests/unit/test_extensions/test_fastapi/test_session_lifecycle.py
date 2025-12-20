"""Tests for session lifecycle with generator-managed dependencies.

This module tests the fix for GitHub issue #647 where asyncpg connections
were not properly returned to the pool when using provide_service().
"""

import sys
from typing import Annotated, Literal
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Session, mapped_column

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.fastapi.providers import _should_commit_for_status
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, SQLAlchemySyncRepositoryService

pytestmark = pytest.mark.xfail(
    condition=sys.version_info < (3, 9),
    reason=(
        "Certain versions of Starlette and FastAPI are stated to still support 3.8, "
        "but there are documented incompatibilities."
    ),
)

CommitMode = Literal["manual", "autocommit", "autocommit_include_redirect"]


class Widget(UUIDBase):
    """Minimal model for dependency tests."""

    __tablename__ = "fastapi_session_widget"

    name: Mapped[str] = mapped_column(String(length=50))


class WidgetAsyncRepository(SQLAlchemyAsyncRepository[Widget]):
    """Async repository for Widget."""

    model_type = Widget


class WidgetAsyncService(SQLAlchemyAsyncRepositoryService[Widget, WidgetAsyncRepository]):
    """Async service for Widget."""

    repository_type = WidgetAsyncRepository


class WidgetSyncRepository(SQLAlchemySyncRepository[Widget]):
    """Sync repository for Widget."""

    model_type = Widget


class WidgetSyncService(SQLAlchemySyncRepositoryService[Widget, WidgetSyncRepository]):
    """Sync service for Widget."""

    repository_type = WidgetSyncRepository


def _make_async_app(commit_mode: CommitMode = "manual") -> tuple[FastAPI, SQLAlchemyAsyncConfig, AdvancedAlchemy]:
    app = FastAPI()
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        commit_mode=commit_mode,
    )
    alchemy = AdvancedAlchemy(config=config, app=app)
    return app, config, alchemy


def _make_sync_app(commit_mode: CommitMode = "manual") -> tuple[FastAPI, SQLAlchemySyncConfig, AdvancedAlchemy]:
    app = FastAPI()
    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        commit_mode=commit_mode,
    )
    alchemy = AdvancedAlchemy(config=config, app=app)
    return app, config, alchemy


def _patch_async_session_methods(mocker: MockerFixture) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock)
    rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback", new_callable=AsyncMock)
    close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close", new_callable=AsyncMock)
    return commit, rollback, close


def _patch_sync_session_methods(mocker: MockerFixture) -> tuple[Mock, Mock, Mock]:
    commit = mocker.patch("sqlalchemy.orm.Session.commit")
    rollback = mocker.patch("sqlalchemy.orm.Session.rollback")
    close = mocker.patch("sqlalchemy.orm.Session.close")
    return commit, rollback, close


@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 299])
def test_should_commit_autocommit_on_2xx(status_code: int) -> None:
    """Verify autocommit mode commits on 2xx status codes."""
    assert _should_commit_for_status(status_code, "autocommit") is True


@pytest.mark.parametrize("status_code", [300, 301, 302, 399, 400, 401, 500])
def test_should_commit_autocommit_no_commit_on_non_2xx(status_code: int) -> None:
    """Verify autocommit mode does not commit on non-2xx status codes."""
    assert _should_commit_for_status(status_code, "autocommit") is False


@pytest.mark.parametrize("status_code", [200, 201, 299, 300, 301, 399])
def test_should_commit_autocommit_include_redirect_on_2xx_3xx(status_code: int) -> None:
    """Verify autocommit_include_redirect mode commits on 2xx and 3xx status codes."""
    assert _should_commit_for_status(status_code, "autocommit_include_redirect") is True


@pytest.mark.parametrize("status_code", [400, 401, 404, 500, 503])
def test_should_commit_autocommit_include_redirect_no_commit_on_4xx_5xx(status_code: int) -> None:
    """Verify autocommit_include_redirect mode does not commit on 4xx/5xx status codes."""
    assert _should_commit_for_status(status_code, "autocommit_include_redirect") is False


@pytest.mark.parametrize("status_code", [200, 201, 300, 400, 500])
def test_should_commit_manual_never_commits(status_code: int) -> None:
    """Verify manual mode never commits regardless of status code."""
    assert _should_commit_for_status(status_code, "manual") is False


def test_generator_session_marked_as_managed() -> None:
    """Verify generator-managed sessions mark request state."""
    app, config, alchemy = _make_async_app()

    @app.get("/")
    def handler(
        request: Request,
        service: Annotated[WidgetAsyncService, Depends(alchemy.provide_service(WidgetAsyncService))],
    ) -> dict[str, bool]:
        key = f"{config.session_key}_generator_managed"
        return {"managed": hasattr(request.state, key)}

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"managed": True}


def test_middleware_skips_generator_managed_sessions(mocker: MockerFixture) -> None:
    """Verify middleware does not close generator-managed sessions."""
    app, config, alchemy = _make_async_app(commit_mode="autocommit")
    mock_handler = mocker.patch.object(config, "session_handler", new_callable=AsyncMock)

    @app.get("/")
    def handler(
        service: Annotated[WidgetAsyncService, Depends(alchemy.provide_service(WidgetAsyncService))],
    ) -> Response:
        return Response(status_code=200)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200

    mock_handler.assert_not_awaited()


def test_generator_session_closed_after_cleanup(mocker: MockerFixture) -> None:
    """Verify generator-managed sessions close in the dependency finally block."""
    app, config, alchemy = _make_async_app(commit_mode="autocommit")
    mock_handler = mocker.patch.object(config, "session_handler", new_callable=AsyncMock)
    _commit, _rollback, close = _patch_async_session_methods(mocker)

    @app.get("/")
    def handler(
        service: Annotated[WidgetAsyncService, Depends(alchemy.provide_service(WidgetAsyncService))],
    ) -> Response:
        return Response(status_code=200)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200

    close.assert_awaited_once()
    mock_handler.assert_not_awaited()


@pytest.mark.parametrize(
    ("status_code", "commit_mode", "should_commit"),
    [
        (200, "autocommit", True),
        (201, "autocommit", True),
        (299, "autocommit", True),
        (300, "autocommit", False),
        (400, "autocommit", False),
        (200, "autocommit_include_redirect", True),
        (301, "autocommit_include_redirect", True),
        (399, "autocommit_include_redirect", True),
        (400, "autocommit_include_redirect", False),
        (200, "manual", False),
    ],
)
def test_async_generator_commit_strategy(
    mocker: MockerFixture,
    status_code: int,
    commit_mode: CommitMode,
    should_commit: bool,
) -> None:
    """Verify async generator-managed commit strategy matches commit_mode and status."""
    app, config, alchemy = _make_async_app(commit_mode=commit_mode)
    mock_handler = mocker.patch.object(config, "session_handler", new_callable=AsyncMock)
    commit, rollback, close = _patch_async_session_methods(mocker)

    @app.get("/")
    def handler(
        service: Annotated[WidgetAsyncService, Depends(alchemy.provide_service(WidgetAsyncService))],
    ) -> Response:
        return Response(status_code=status_code)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code

    if should_commit:
        commit.assert_awaited_once()
        rollback.assert_not_awaited()
    else:
        rollback.assert_awaited_once()
        commit.assert_not_awaited()

    close.assert_awaited_once()
    mock_handler.assert_not_awaited()


def test_async_generator_exception_triggers_rollback(mocker: MockerFixture) -> None:
    """Verify exceptions in handler trigger rollback in generator cleanup."""
    app, config, alchemy = _make_async_app(commit_mode="autocommit")
    mock_handler = mocker.patch.object(config, "session_handler", new_callable=AsyncMock)
    commit, rollback, close = _patch_async_session_methods(mocker)

    @app.get("/")
    def handler(
        service: Annotated[WidgetAsyncService, Depends(alchemy.provide_service(WidgetAsyncService))],
    ) -> Response:
        raise RuntimeError("boom")

    client = TestClient(app=app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 500

    commit.assert_not_awaited()
    rollback.assert_awaited_once()
    close.assert_awaited_once()
    mock_handler.assert_not_awaited()


@pytest.mark.parametrize(
    ("status_code", "commit_mode", "should_commit"),
    [
        (200, "autocommit", True),
        (400, "autocommit", False),
        (200, "manual", False),
    ],
)
def test_sync_generator_commit_strategy(
    mocker: MockerFixture,
    status_code: int,
    commit_mode: CommitMode,
    should_commit: bool,
) -> None:
    """Verify sync generator-managed commit strategy matches commit_mode and status."""
    app, config, alchemy = _make_sync_app(commit_mode=commit_mode)
    mock_handler = mocker.patch.object(config, "session_handler", new_callable=AsyncMock)
    commit, rollback, close = _patch_sync_session_methods(mocker)

    @app.get("/")
    def handler(
        service: Annotated[WidgetSyncService, Depends(alchemy.provide_service(WidgetSyncService))],
    ) -> Response:
        return Response(status_code=status_code)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == status_code

    if should_commit:
        commit.assert_called_once()
        rollback.assert_not_called()
    else:
        rollback.assert_called_once()
        commit.assert_not_called()

    close.assert_called_once()
    mock_handler.assert_not_awaited()


def test_non_generator_session_uses_middleware_async(mocker: MockerFixture) -> None:
    """Verify provide_session uses middleware cleanup for async sessions."""
    app, _config, alchemy = _make_async_app(commit_mode="autocommit")
    commit, _rollback, close = _patch_async_session_methods(mocker)

    @app.get("/")
    def handler(session: Annotated[AsyncSession, Depends(alchemy.provide_session())]) -> Response:
        return Response(status_code=200)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200

    commit.assert_awaited_once()
    close.assert_awaited_once()


def test_direct_session_uses_middleware_async(mocker: MockerFixture) -> None:
    """Verify direct session access uses middleware cleanup for async sessions."""
    app, _config, alchemy = _make_async_app(commit_mode="autocommit")
    commit, _rollback, close = _patch_async_session_methods(mocker)

    @app.get("/")
    def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=200)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200

    commit.assert_awaited_once()
    close.assert_awaited_once()


def test_non_generator_session_uses_middleware_sync(mocker: MockerFixture) -> None:
    """Verify provide_session uses middleware cleanup for sync sessions."""
    app, _config, alchemy = _make_sync_app(commit_mode="autocommit")
    commit, _rollback, close = _patch_sync_session_methods(mocker)

    @app.get("/")
    def handler(session: Annotated[Session, Depends(alchemy.provide_session())]) -> Response:
        return Response(status_code=200)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200

    commit.assert_called_once()
    close.assert_called_once()


def test_direct_session_uses_middleware_sync(mocker: MockerFixture) -> None:
    """Verify direct session access uses middleware cleanup for sync sessions."""
    app, _config, alchemy = _make_sync_app(commit_mode="autocommit")
    commit, _rollback, close = _patch_sync_session_methods(mocker)

    @app.get("/")
    def handler(request: Request) -> Response:
        _session = alchemy.get_session(request)
        return Response(status_code=200)

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200

    commit.assert_called_once()
    close.assert_called_once()


def test_multiple_generator_sessions_tracked_independently() -> None:
    """Verify multiple configs track generator-managed sessions separately."""
    app = FastAPI()
    config_one = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        bind_key="db1",
        session_key="db1_session",
    )
    config_two = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        bind_key="db2",
        session_key="db2_session",
    )
    alchemy = AdvancedAlchemy(config=[config_one, config_two], app=app)

    @app.get("/")
    def handler(
        request: Request,
        service_one: Annotated[WidgetAsyncService, Depends(alchemy.provide_service(WidgetAsyncService, key="db1"))],
        service_two: Annotated[WidgetAsyncService, Depends(alchemy.provide_service(WidgetAsyncService, key="db2"))],
    ) -> dict[str, bool]:
        return {
            "db1": hasattr(request.state, f"{config_one.session_key}_generator_managed"),
            "db2": hasattr(request.state, f"{config_two.session_key}_generator_managed"),
        }

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"db1": True, "db2": True}

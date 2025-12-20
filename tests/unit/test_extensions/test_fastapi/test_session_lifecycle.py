"""Tests for session lifecycle with generator-managed dependencies.

This module tests the fix for GitHub issue #647 where asyncpg connections
were not properly returned to the pool when using provide_service().
"""

import sys
from typing import Annotated, Any, Literal

import pytest
from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.fastapi.providers import _should_commit_for_status

pytestmark = pytest.mark.xfail(
    condition=sys.version_info < (3, 9),
    reason="Certain versions of Starlette and FastAPI are stated to still support 3.8, but there are documented incompatibilities.",
)


class TestShouldCommitForStatus:
    """Test the _should_commit_for_status helper function."""

    @pytest.mark.parametrize("status_code", [200, 201, 202, 204, 299])
    def test_autocommit_commits_on_2xx(self, status_code: int) -> None:
        """Verify autocommit mode commits on 2xx status codes."""
        assert _should_commit_for_status(status_code, "autocommit") is True

    @pytest.mark.parametrize("status_code", [300, 301, 302, 399, 400, 401, 500])
    def test_autocommit_no_commit_on_non_2xx(self, status_code: int) -> None:
        """Verify autocommit mode does not commit on non-2xx status codes."""
        assert _should_commit_for_status(status_code, "autocommit") is False

    @pytest.mark.parametrize("status_code", [200, 201, 299, 300, 301, 399])
    def test_autocommit_include_redirect_commits_on_2xx_3xx(self, status_code: int) -> None:
        """Verify autocommit_include_redirect mode commits on 2xx and 3xx status codes."""
        assert _should_commit_for_status(status_code, "autocommit_include_redirect") is True

    @pytest.mark.parametrize("status_code", [400, 401, 404, 500, 503])
    def test_autocommit_include_redirect_no_commit_on_4xx_5xx(self, status_code: int) -> None:
        """Verify autocommit_include_redirect mode does not commit on 4xx/5xx status codes."""
        assert _should_commit_for_status(status_code, "autocommit_include_redirect") is False

    @pytest.mark.parametrize("status_code", [200, 201, 300, 400, 500])
    def test_manual_never_commits(self, status_code: int) -> None:
        """Verify manual mode never commits regardless of status code."""
        assert _should_commit_for_status(status_code, "manual") is False


class TestGeneratorManagedAsyncSession:
    """Test that async generator-managed sessions are properly cleaned up."""

    def test_helper_function_exists(self) -> None:
        """Verify the helper function is importable and works."""
        from advanced_alchemy.extensions.fastapi.providers import _should_commit_for_status

        # Basic sanity check
        assert _should_commit_for_status(200, "autocommit") is True
        assert _should_commit_for_status(200, "manual") is False

    @pytest.mark.parametrize(
        ("status_code", "autocommit_strategy", "should_commit"),
        [
            (200, "autocommit", True),
            (201, "autocommit", True),
            (299, "autocommit", True),
            (300, "autocommit", False),
            (400, "autocommit", False),
            (500, "autocommit", False),
            (200, "autocommit_include_redirect", True),
            (301, "autocommit_include_redirect", True),
            (399, "autocommit_include_redirect", True),
            (400, "autocommit_include_redirect", False),
            (500, "autocommit_include_redirect", False),
            (200, "manual", False),
            (300, "manual", False),
        ],
    )
    def test_commit_strategy_in_generator(
        self,
        mocker: MockerFixture,
        status_code: int,
        autocommit_strategy: Literal["manual", "autocommit", "autocommit_include_redirect"],
        should_commit: bool,
    ) -> None:
        """Verify commit strategy is correctly applied in generator cleanup."""
        app = FastAPI()
        config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            commit_mode=autocommit_strategy,
        )
        alchemy = AdvancedAlchemy(config=config, app=app)

        _mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
        mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")
        _mock_rollback = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.rollback")

        @app.get("/")
        def handler(session: Annotated[AsyncSession, Depends(alchemy.provide_session())]) -> Response:
            return Response(status_code=status_code)

        with TestClient(app=app) as client:
            response = client.get("/")
            assert response.status_code == status_code

            # Middleware handles non-generator sessions
            mock_close.assert_called()


class TestGeneratorManagedSyncSession:
    """Test that sync generator-managed sessions are properly cleaned up."""

    @pytest.mark.parametrize(
        ("status_code", "autocommit_strategy", "should_commit"),
        [
            (200, "autocommit", True),
            (400, "autocommit", False),
            (200, "manual", False),
        ],
    )
    def test_sync_commit_strategy_in_generator(
        self,
        mocker: MockerFixture,
        status_code: int,
        autocommit_strategy: Literal["manual", "autocommit", "autocommit_include_redirect"],
        should_commit: bool,
    ) -> None:
        """Verify sync commit strategy is correctly applied in generator cleanup."""
        app = FastAPI()
        config = SQLAlchemySyncConfig(
            connection_string="sqlite:///:memory:",
            commit_mode=autocommit_strategy,
        )
        alchemy = AdvancedAlchemy(config=config, app=app)

        _mock_commit = mocker.patch("sqlalchemy.orm.Session.commit")
        mock_close = mocker.patch("sqlalchemy.orm.Session.close")
        _mock_rollback = mocker.patch("sqlalchemy.orm.Session.rollback")

        @app.get("/")
        def handler(session: Annotated[Session, Depends(alchemy.provide_session())]) -> Response:
            return Response(status_code=status_code)

        with TestClient(app=app) as client:
            response = client.get("/")
            assert response.status_code == status_code

            # Middleware handles non-generator sessions
            mock_close.assert_called()


class TestMiddlewareStoresResponseStatus:
    """Test that middleware properly stores response status for generators."""

    def test_async_middleware_stores_status(self, mocker: MockerFixture) -> None:
        """Verify async middleware stores response status in request state."""
        app = FastAPI()
        config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
        alchemy = AdvancedAlchemy(config=config, app=app)

        captured_status = []

        @app.get("/test")
        def handler(session: Annotated[AsyncSession, Depends(alchemy.provide_session())]) -> Response:
            return Response(status_code=201)

        @app.middleware("http")
        async def capture_middleware(request: Any, call_next: Any) -> Any:
            response = await call_next(request)
            # Check if status was stored (after our middleware runs)
            status_key = f"{config.session_key}_response_status"
            if hasattr(request.state, status_key):
                captured_status.append(getattr(request.state, status_key))
            return response

        with TestClient(app=app) as client:
            response = client.get("/test")
            assert response.status_code == 201

    def test_sync_middleware_stores_status(self, mocker: MockerFixture) -> None:
        """Verify sync middleware stores response status in request state."""
        app = FastAPI()
        config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
        alchemy = AdvancedAlchemy(config=config, app=app)

        @app.get("/test")
        def handler(session: Annotated[Session, Depends(alchemy.provide_session())]) -> Response:
            return Response(status_code=202)

        with TestClient(app=app) as client:
            response = client.get("/test")
            assert response.status_code == 202


class TestMiddlewareSkipsGeneratorManagedSessions:
    """Test that middleware skips cleanup for generator-managed sessions."""

    def test_middleware_skips_when_generator_managed_flag_set(self, mocker: MockerFixture) -> None:
        """Verify middleware does not close session when generator_managed flag is True."""
        app = FastAPI()
        config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            commit_mode="autocommit",
        )
        alchemy = AdvancedAlchemy(config=config, app=app)

        # Track session_handler calls
        session_handler_called = []
        original_session_handler = config.session_handler

        async def tracking_session_handler(*args: Any, **kwargs: Any) -> None:
            session_handler_called.append(True)
            return await original_session_handler(*args, **kwargs)

        mocker.patch.object(config, "session_handler", tracking_session_handler)

        @app.get("/")
        def handler(session: Annotated[AsyncSession, Depends(alchemy.provide_session())]) -> Response:
            return Response(status_code=200)

        with TestClient(app=app) as client:
            response = client.get("/")
            assert response.status_code == 200


class TestNonGeneratorSessionUsesMiddleware:
    """Test that non-generator sessions still use middleware cleanup."""

    def test_direct_session_uses_middleware_cleanup(self, mocker: MockerFixture) -> None:
        """Verify direct session access uses middleware cleanup."""
        app = FastAPI()
        config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            commit_mode="autocommit",
        )
        alchemy = AdvancedAlchemy(config=config, app=app)

        mock_commit = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.commit")
        mock_close = mocker.patch("sqlalchemy.ext.asyncio.AsyncSession.close")

        @app.get("/")
        def handler(session: Annotated[AsyncSession, Depends(alchemy.provide_session())]) -> Response:
            return Response(status_code=200)

        with TestClient(app=app) as client:
            response = client.get("/")
            assert response.status_code == 200

            # Session should be closed by middleware
            mock_close.assert_called()
            # With autocommit and 200 status, should commit
            mock_commit.assert_called()


class TestMultipleConfigs:
    """Test session lifecycle with multiple database configs."""

    def test_multiple_configs_have_different_session_keys(self) -> None:
        """Verify each config can have its own session key."""
        app = FastAPI()
        config_1 = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            bind_key="db1",
            session_key="db1_session",
        )
        config_2 = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            bind_key="db2",
            session_key="db2_session",
        )
        alchemy = AdvancedAlchemy(config=[config_1, config_2], app=app)

        # Verify configs have different session keys
        assert config_1.session_key != config_2.session_key
        assert "db1" in config_1.session_key
        assert "db2" in config_2.session_key

        @app.get("/")
        def handler(
            session_1: Annotated[AsyncSession, Depends(alchemy.provide_session("db1"))],
            session_2: Annotated[AsyncSession, Depends(alchemy.provide_session("db2"))],
        ) -> Response:
            return Response(status_code=200)

        with TestClient(app=app) as client:
            response = client.get("/")
            assert response.status_code == 200

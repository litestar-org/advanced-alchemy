from __future__ import annotations

import random
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from asgi_lifespan import LifespanManager
from litestar import Litestar, get
from litestar.testing import create_test_client
from litestar.types.asgi_types import HTTPResponseStartEvent
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.extensions.litestar._utils import set_aa_scope_state
from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyAsyncConfig, SQLAlchemyInitPlugin
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import (
    autocommit_before_send_handler,
    autocommit_handler_maker,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.common import SESSION_SCOPE_KEY

if TYPE_CHECKING:
    from typing import Any, Callable

    from litestar.types import Scope


def test_default_before_send_handler() -> None:
    """Test default_before_send_handler."""

    captured_scope_state: dict[str, Any] | None = None
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite://")
    plugin = SQLAlchemyInitPlugin(config=config)

    @get()
    def test_handler(db_session: AsyncSession, scope: Scope) -> None:
        nonlocal captured_scope_state
        captured_scope_state = scope["state"]
        assert db_session is captured_scope_state[config.session_dependency_key]

    with create_test_client(route_handlers=[test_handler], plugins=[plugin]) as client:
        client.get("/")
        assert captured_scope_state is not None
        assert config.session_dependency_key not in captured_scope_state  # pyright: ignore


async def test_create_all_default(monkeypatch: MonkeyPatch) -> None:
    """Test default_before_send_handler."""

    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite://")
    plugin = SQLAlchemyInitPlugin(config=config)
    app = Litestar(route_handlers=[], plugins=[plugin])
    with patch.object(
        config,
        "create_all_metadata",
    ) as create_all_metadata_mock:
        async with LifespanManager(app):
            create_all_metadata_mock.assert_not_called()


async def test_create_all(monkeypatch: MonkeyPatch) -> None:
    """Test default_before_send_handler."""
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite://", create_all=True)
    plugin = SQLAlchemyInitPlugin(config=config)
    app = Litestar(route_handlers=[], plugins=[plugin])
    with patch.object(
        config,
        "create_all_metadata",
    ) as create_all_metadata_mock:
        async with LifespanManager(app):
            create_all_metadata_mock.assert_called_once()


async def test_before_send_handler_success_response(create_scope: Callable[..., Scope]) -> None:
    """Test that the session is committed given a success response."""
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite://",
        before_send_handler=autocommit_before_send_handler,
    )
    app = Litestar(route_handlers=[], plugins=[SQLAlchemyInitPlugin(config)])
    mock_session = MagicMock(spec=AsyncSession)
    http_scope = create_scope(app=app)
    set_aa_scope_state(http_scope, SESSION_SCOPE_KEY, mock_session)
    http_response_start: HTTPResponseStartEvent = {
        "type": "http.response.start",
        "status": random.randint(200, 299),
        "headers": {},
    }
    await autocommit_before_send_handler(http_response_start, http_scope)
    mock_session.commit.assert_awaited_once()


async def test_before_send_handler_error_response(create_scope: Callable[..., Scope]) -> None:
    """Test that the session is rolled back given an error response."""
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite://",
        before_send_handler=autocommit_before_send_handler,
    )
    app = Litestar(route_handlers=[], plugins=[SQLAlchemyInitPlugin(config)])
    mock_session = MagicMock(spec=AsyncSession)
    http_scope = create_scope(app=app)
    set_aa_scope_state(http_scope, SESSION_SCOPE_KEY, mock_session)
    http_response_start: HTTPResponseStartEvent = {
        "type": "http.response.start",
        "status": random.randint(300, 599),
        "headers": {},
    }
    await autocommit_before_send_handler(http_response_start, http_scope)
    mock_session.rollback.assert_awaited_once()


async def test_autocommit_handler_maker_redirect_response(create_scope: Callable[..., Scope]) -> None:
    """Test that the handler created by the handler maker commits on redirect"""
    autocommit_redirect_handler = autocommit_handler_maker(commit_on_redirect=True)
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite://",
        before_send_handler=autocommit_redirect_handler,
    )
    app = Litestar(route_handlers=[], plugins=[SQLAlchemyInitPlugin(config)])
    mock_session = MagicMock(spec=AsyncSession)
    http_scope = create_scope(app=app)
    set_aa_scope_state(http_scope, SESSION_SCOPE_KEY, mock_session)
    http_response_start: HTTPResponseStartEvent = {
        "type": "http.response.start",
        "status": random.randint(300, 399),
        "headers": {},
    }
    await autocommit_redirect_handler(http_response_start, http_scope)
    mock_session.commit.assert_awaited_once()


async def test_autocommit_handler_maker_commit_statuses(create_scope: Callable[..., Scope]) -> None:
    """Test that the handler created by the handler maker commits on explicit statuses"""
    custom_autocommit_handler = autocommit_handler_maker(extra_commit_statuses={302, 303})
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite://",
        before_send_handler=custom_autocommit_handler,
    )
    app = Litestar(route_handlers=[], plugins=[SQLAlchemyInitPlugin(config)])
    mock_session = MagicMock(spec=AsyncSession)
    http_scope = create_scope(app=app)
    set_aa_scope_state(http_scope, SESSION_SCOPE_KEY, mock_session)
    http_response_start: HTTPResponseStartEvent = {
        "type": "http.response.start",
        "status": random.randint(302, 303),
        "headers": {},
    }
    await custom_autocommit_handler(http_response_start, http_scope)
    mock_session.commit.assert_awaited_once()


async def test_autocommit_handler_maker_rollback_statuses(create_scope: Callable[..., Scope]) -> None:
    """Test that the handler created by the handler maker rolls back on explicit statuses"""
    custom_autocommit_handler = autocommit_handler_maker(commit_on_redirect=True, extra_rollback_statuses={307, 308})
    config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite://",
        before_send_handler=custom_autocommit_handler,
    )
    app = Litestar(route_handlers=[], plugins=[SQLAlchemyInitPlugin(config)])
    mock_session = MagicMock(spec=AsyncSession)
    http_scope = create_scope(app=app)
    set_aa_scope_state(http_scope, SESSION_SCOPE_KEY, mock_session)
    http_response_start: HTTPResponseStartEvent = {
        "type": "http.response.start",
        "status": random.randint(307, 308),
        "headers": {},
    }
    await custom_autocommit_handler(http_response_start, http_scope)
    mock_session.rollback.assert_awaited_once()

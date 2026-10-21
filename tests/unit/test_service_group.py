"""Unit tests for ServiceGroup and provide_services multi-service acquisition."""

from collections.abc import AsyncGenerator, Generator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.config import SQLAlchemySyncConfig
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.repository import Empty
from advanced_alchemy.service import (
    AsyncServiceProvider,
    ServiceGroup,
    ServiceSpec,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
    SyncServiceProvider,
    provide_services,
)


def test_type_alias_exports() -> None:
    assert AsyncServiceProvider is not None
    assert SyncServiceProvider is not None
    assert ServiceSpec is not None


class FakeUserService:
    """Mock async service taking a session keyword argument."""

    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session


class FakeRoleService:
    """Mock async service taking a session keyword argument."""

    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session


class FakeSyncUserService:
    """Mock sync service taking a session keyword argument."""

    def __init__(self, *, session: Session) -> None:
        self.session = session


class FakeSyncRoleService:
    """Mock sync service taking a session keyword argument."""

    def __init__(self, *, session: Session) -> None:
        self.session = session


@pytest.mark.asyncio
async def test_provide_services_async_classes() -> None:
    session = MagicMock(spec=AsyncSession)

    async with provide_services(FakeUserService, FakeRoleService, session=session) as (users, roles):
        assert isinstance(users, FakeUserService)
        assert isinstance(roles, FakeRoleService)
        assert users.session is session
        assert roles.session is session


@pytest.mark.asyncio
async def test_provide_services_async_generators_lifo_cleanup() -> None:
    cleanup_log: list[str] = []
    session = MagicMock(spec=AsyncSession)

    async def provide_user(sess: AsyncSession) -> AsyncGenerator[FakeUserService, None]:
        try:
            yield FakeUserService(session=sess)
        finally:
            cleanup_log.append("user_cleanup")

    async def provide_role(sess: AsyncSession) -> AsyncGenerator[FakeRoleService, None]:
        try:
            yield FakeRoleService(session=sess)
        finally:
            cleanup_log.append("role_cleanup")

    async with provide_services(provide_user, provide_role, session=session) as (users, roles):
        assert isinstance(users, FakeUserService)
        assert isinstance(roles, FakeRoleService)
        assert not cleanup_log

    assert cleanup_log == ["role_cleanup", "user_cleanup"]


@pytest.mark.asyncio
async def test_provide_services_mixed_classes_and_providers() -> None:
    cleanup_ran = False
    session = MagicMock(spec=AsyncSession)

    async def provide_role(sess: AsyncSession) -> AsyncGenerator[FakeRoleService, None]:
        try:
            yield FakeRoleService(session=sess)
        finally:
            nonlocal cleanup_ran
            cleanup_ran = True

    async with provide_services(FakeUserService, provide_role, session=session) as (users, roles):
        assert isinstance(users, FakeUserService)
        assert isinstance(roles, FakeRoleService)

    assert cleanup_ran


def test_provide_services_sync_classes() -> None:
    session = MagicMock(spec=Session)

    with provide_services(FakeSyncUserService, FakeSyncRoleService, session=session) as (users, roles):
        assert isinstance(users, FakeSyncUserService)
        assert isinstance(roles, FakeSyncRoleService)
        assert users.session is session
        assert roles.session is session


def test_provide_services_sync_generators_lifo_cleanup() -> None:
    cleanup_log: list[str] = []
    session = MagicMock(spec=Session)

    def provide_sync_user(sess: Session) -> Generator[FakeSyncUserService, None, None]:
        try:
            yield FakeSyncUserService(session=sess)
        finally:
            cleanup_log.append("sync_user_cleanup")

    def provide_sync_role(sess: Session) -> Generator[FakeSyncRoleService, None, None]:
        try:
            yield FakeSyncRoleService(session=sess)
        finally:
            cleanup_log.append("sync_role_cleanup")

    with provide_services(provide_sync_user, provide_sync_role, session=session) as (users, roles):
        assert isinstance(users, FakeSyncUserService)
        assert isinstance(roles, FakeSyncRoleService)
        assert not cleanup_log

    assert cleanup_log == ["sync_role_cleanup", "sync_user_cleanup"]


@pytest.mark.asyncio
async def test_provide_services_with_async_config() -> None:
    session = MagicMock(spec=AsyncSession)
    config = MagicMock()
    config_session_ctx = AsyncMock()
    config_session_ctx.__aenter__.return_value = session
    config.get_session.return_value = config_session_ctx

    async with provide_services(FakeUserService, config=config) as (users,):
        assert isinstance(users, FakeUserService)
        assert users.session is session

    config.get_session.assert_called_once()
    config_session_ctx.__aenter__.assert_awaited_once()
    config_session_ctx.__aexit__.assert_awaited_once()


def test_provide_services_with_sync_config() -> None:
    session = MagicMock(spec=Session)
    config = MagicMock()
    config_session_ctx = MagicMock()
    config_session_ctx.__enter__.return_value = session
    config.get_session.return_value = config_session_ctx

    with provide_services(FakeSyncUserService, config=config) as (users,):
        assert isinstance(users, FakeSyncUserService)
        assert users.session is session

    config.get_session.assert_called_once()
    config_session_ctx.__enter__.assert_called_once()
    config_session_ctx.__exit__.assert_called_once()


@pytest.mark.asyncio
async def test_service_group_reusability() -> None:
    session = MagicMock(spec=AsyncSession)
    group = ServiceGroup(FakeUserService, FakeRoleService)

    async with group.new(session=session) as (users, roles):
        assert isinstance(users, FakeUserService)
        assert isinstance(roles, FakeRoleService)


def test_missing_session_and_config_raises_error() -> None:
    with pytest.raises(ImproperConfigurationError, match="session, config, or connection"):
        with provide_services(FakeSyncUserService):
            pass


@pytest.mark.asyncio
async def test_missing_session_and_config_async_raises_error() -> None:
    with pytest.raises(ImproperConfigurationError, match="session, config, or connection"):
        async with provide_services(FakeUserService):
            pass


@pytest.mark.asyncio
async def test_partial_failure_closes_entered_providers() -> None:
    cleanup_ran = False

    async def cleanup_provider(session: AsyncSession) -> AsyncGenerator[FakeUserService, None]:
        try:
            yield FakeUserService(session=session)
        finally:
            nonlocal cleanup_ran
            cleanup_ran = True

    async def failing_provider(session: AsyncSession) -> AsyncGenerator[Any, None]:
        if repr(session) == "unused":
            yield None
        raise RuntimeError("entry failure")

    session = MagicMock(spec=AsyncSession)

    with pytest.raises(RuntimeError, match="entry failure"):
        async with provide_services(cleanup_provider, failing_provider, session=session):
            pass

    assert cleanup_ran


@pytest.mark.asyncio
async def test_user_exception_inside_block_triggers_cleanup() -> None:
    cleanup_ran = False

    async def cleanup_provider(session: AsyncSession) -> AsyncGenerator[FakeUserService, None]:
        try:
            yield FakeUserService(session=session)
        finally:
            nonlocal cleanup_ran
            cleanup_ran = True

    session = MagicMock(spec=AsyncSession)

    async def raise_user_error() -> None:
        async with provide_services(cleanup_provider, session=session):
            raise ValueError("inner user error")

    with pytest.raises(ValueError, match="inner user error"):
        await raise_user_error()

    assert cleanup_ran


@pytest.mark.asyncio
async def test_provide_services_with_connection_and_config() -> None:
    session = MagicMock(spec=AsyncSession)
    config = MagicMock()
    config.provide_session.return_value = session

    connection = MagicMock()
    connection.app.state = MagicMock()
    connection.scope = {}

    async with provide_services(FakeUserService, connection=connection, config=config) as (users,):
        assert isinstance(users, FakeUserService)
        assert users.session is session

    config.provide_session.assert_called_once_with(connection.app.state, connection.scope)


def test_provide_services_sync_with_connection_and_config() -> None:
    session = MagicMock(spec=Session)
    config = MagicMock()
    config.provide_session.return_value = session

    connection = MagicMock()
    connection.app.state = MagicMock()
    connection.scope = {}

    with provide_services(FakeSyncUserService, connection=connection, config=config) as (users,):
        assert isinstance(users, FakeSyncUserService)
        assert users.session is session

    config.provide_session.assert_called_once_with(connection.app.state, connection.scope)


def test_framework_re_exports() -> None:
    from advanced_alchemy.extensions.fastapi.providers import (
        ServiceGroup as FastApiServiceGroup,
    )
    from advanced_alchemy.extensions.fastapi.providers import (
        provide_services as fastapi_provide_services,
    )
    from advanced_alchemy.extensions.litestar.providers import (
        ServiceGroup as LitestarProvidersServiceGroup,
    )
    from advanced_alchemy.extensions.litestar.providers import (
        provide_services as litestar_providers_provide_services,
    )
    from advanced_alchemy.extensions.litestar.service import (
        ServiceGroup as LitestarServiceGroup,
    )
    from advanced_alchemy.extensions.litestar.service import (
        SQLAlchemyAsyncRepositoryService as LitestarAsyncRepoService,
    )
    from advanced_alchemy.extensions.litestar.service import (
        provide_services as litestar_provide_services,
    )

    assert FastApiServiceGroup is ServiceGroup
    assert fastapi_provide_services is provide_services
    assert LitestarProvidersServiceGroup is ServiceGroup
    assert litestar_providers_provide_services is provide_services
    assert LitestarServiceGroup is ServiceGroup
    assert LitestarAsyncRepoService is SQLAlchemyAsyncRepositoryService
    assert litestar_provide_services is provide_services


@pytest.mark.asyncio
async def test_service_group_provide_async() -> None:
    session = MagicMock(spec=AsyncSession)
    group = ServiceGroup(FakeUserService, FakeRoleService)
    provider = group.provide()

    async for services in provider(db_session=session):
        users, roles = services
        assert isinstance(users, FakeUserService)
        assert isinstance(roles, FakeRoleService)
        assert users.session is session
        assert roles.session is session


def test_service_group_provide_sync() -> None:
    session = MagicMock(spec=Session)
    group = ServiceGroup(FakeSyncUserService, FakeSyncRoleService)
    sync_config = MagicMock(spec=SQLAlchemySyncConfig)
    type(sync_config).__name__ = "SQLAlchemySyncConfig"
    sync_config.session_dependency_key = "sync_session"
    provider = group.provide(config=cast(SQLAlchemySyncConfig, sync_config))

    for services in provider(sync_session=session):
        users, roles = services
        assert isinstance(users, FakeSyncUserService)
        assert isinstance(roles, FakeSyncRoleService)
        assert users.session is session
        assert roles.session is session


@pytest.mark.asyncio
async def test_sync_session_in_async_context_raises_error() -> None:
    session = MagicMock(spec=Session)
    with pytest.raises(ImproperConfigurationError, match="synchronous Session cannot be used in an async context"):
        async with provide_services(FakeUserService, session=session):
            pass


def test_async_session_in_sync_context_raises_error() -> None:
    session = MagicMock(spec=AsyncSession)
    with pytest.raises(ImproperConfigurationError, match="asynchronous AsyncSession cannot be used in a sync context"):
        with provide_services(FakeSyncUserService, session=session):
            pass


def test_async_provider_in_sync_context_raises_error() -> None:
    session = MagicMock(spec=Session)

    async def async_provider(sess: Any) -> AsyncGenerator[Any, None]:
        yield sess

    with pytest.raises(
        ImproperConfigurationError, match="asynchronous service provider cannot be used in a synchronous 'with' block"
    ):
        with provide_services(async_provider, session=session):
            pass


@pytest.mark.asyncio
async def test_sync_session_from_config_in_async_context_raises_error() -> None:
    config = MagicMock()
    config_session_ctx = MagicMock()
    del config_session_ctx.__aenter__
    config.get_session.return_value = config_session_ctx

    with pytest.raises(ImproperConfigurationError, match="Config returned a synchronous session context"):
        async with provide_services(FakeUserService, config=config):
            pass


def test_async_session_from_config_in_sync_context_raises_error() -> None:
    config = MagicMock()
    config_session_ctx = MagicMock()
    del config_session_ctx.__enter__
    config.get_session.return_value = config_session_ctx

    with pytest.raises(ImproperConfigurationError, match="Config returned an asynchronous session context"):
        with provide_services(FakeSyncUserService, config=config):
            pass


@pytest.mark.asyncio
async def test_provide_services_with_async_function_provider() -> None:
    session = MagicMock(spec=AsyncSession)

    async def provide_user_func(sess: AsyncSession) -> FakeUserService:
        return FakeUserService(session=sess)

    async with provide_services(provide_user_func, FakeRoleService, session=session) as (users, roles):
        assert isinstance(users, FakeUserService)
        assert isinstance(roles, FakeRoleService)
        assert users.session is session
        assert roles.session is session


def test_async_function_provider_in_sync_context_raises_error() -> None:
    session = MagicMock(spec=Session)

    async def async_fn(sess: Any) -> Any:
        return sess

    with pytest.raises(
        ImproperConfigurationError, match="asynchronous service provider cannot be used in a synchronous 'with' block"
    ):
        with provide_services(async_fn, session=session):
            pass


@pytest.mark.asyncio
async def test_provide_services_with_repository_services() -> None:
    session = MagicMock(spec=AsyncSession)
    session.bind = MagicMock()
    session.bind.dialect.name = "sqlite"

    class SampleAsyncService(SQLAlchemyAsyncRepositoryService[Any]):
        repository_type = MagicMock()

    async with provide_services(SampleAsyncService, FakeRoleService, session=session) as (svc, roles):
        assert isinstance(svc, SampleAsyncService)
        assert isinstance(roles, FakeRoleService)


def test_provide_services_sync_with_repository_services() -> None:
    session = MagicMock(spec=Session)
    session.bind = MagicMock()
    session.bind.dialect.name = "sqlite"

    class SampleSyncService(SQLAlchemySyncRepositoryService[Any]):
        repository_type = MagicMock()

    with provide_services(SampleSyncService, FakeSyncRoleService, session=session) as (svc, roles):
        assert isinstance(svc, SampleSyncService)
        assert isinstance(roles, FakeSyncRoleService)


def test_connection_without_config_raises_error() -> None:
    connection = MagicMock()
    with pytest.raises(ImproperConfigurationError, match="provide_session"):
        with provide_services(FakeSyncUserService, connection=connection):
            pass


@pytest.mark.asyncio
async def test_connection_without_config_async_raises_error() -> None:
    connection = MagicMock()
    with pytest.raises(ImproperConfigurationError, match="provide_session"):
        async with provide_services(FakeUserService, connection=connection):
            pass


@pytest.mark.asyncio
async def test_service_group_options_propagation() -> None:
    session = MagicMock(spec=AsyncSession)

    class MockServiceCls:
        new = MagicMock()

    mock_service_instance = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_service_instance
    MockServiceCls.new.return_value = mock_ctx

    group = ServiceGroup(
        MockServiceCls,
        statement=cast("Any", "statement_marker"),
        uniquify=True,
    )

    async with group.new(session=session, count_with_window_function=True) as (svc,):
        assert svc is mock_service_instance

    MockServiceCls.new.assert_called_once_with(
        session=session,
        statement="statement_marker",
        config=None,
        error_messages=Empty,
        load=None,
        execution_options=None,
        uniquify=True,
        count_with_window_function=True,
    )

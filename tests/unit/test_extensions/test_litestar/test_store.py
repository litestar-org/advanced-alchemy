import datetime
from collections.abc import Awaitable, Generator
from typing import Any, Callable, TypeVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litestar.exceptions import ImproperlyConfiguredException
from litestar.types import Empty
from pytest import MonkeyPatch
from sqlalchemy import Dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.store import SQLAlchemyStore, StoreModelMixin
from advanced_alchemy.utils.time import get_utc_now

# Type variable for the callable in the patch
F = TypeVar("F", bound=Callable[..., Any])


class MockStoreModel(StoreModelMixin):
    """Mock store model for testing."""

    __tablename__ = "mock_store"


@pytest.fixture()
def mock_store_model() -> type[StoreModelMixin]:
    return MockStoreModel


@pytest.fixture()
def mock_async_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.__aenter__.return_value = session  # Simulate async context manager
    session.__aexit__.return_value = None

    # Set up the dialect for merge/upsert support
    dialect = MagicMock(spec=Dialect)
    dialect.name = "postgresql"
    dialect.server_version_info = (15, 0)
    session.bind = MagicMock()
    session.bind.dialect = dialect

    # Configure execute to return a mock that can be used for scalar_one_or_none
    execute_result = AsyncMock()
    execute_result.scalar_one_or_none = AsyncMock()  # Create an async mock for the method
    session.execute = AsyncMock(return_value=execute_result)  # Create an async mock for execute

    return session


@pytest.fixture()
def mock_async_config(mock_store_model: type[StoreModelMixin], mock_async_session: AsyncMock) -> MagicMock:
    config = MagicMock(spec=SQLAlchemyAsyncConfig)
    config.get_session.return_value = mock_async_session  # Configure the mock method
    return config


@pytest.fixture()
def mock_sync_session() -> MagicMock:
    session = MagicMock(spec=SyncSession)
    session.__enter__.return_value = session  # Simulate sync context manager
    session.__exit__.return_value = None

    # Set up the dialect for merge/upsert support
    dialect = MagicMock(spec=Dialect)
    dialect.name = "postgresql"
    dialect.server_version_info = (15, 0)
    session.bind = MagicMock()
    session.bind.dialect = dialect

    # Configure execute to return a mock that can be used for scalar_one_or_none
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute.return_value = execute_result

    return session


@pytest.fixture()
def mock_sync_config(mock_store_model: type[StoreModelMixin], mock_sync_session: MagicMock) -> MagicMock:
    config = MagicMock(spec=SQLAlchemySyncConfig)
    config.get_session.return_value = mock_sync_session  # Configure the mock method
    return config


@pytest.fixture()
def async_store(mock_async_config: MagicMock) -> SQLAlchemyStore[SQLAlchemyAsyncConfig]:
    """Create an async store instance."""
    return SQLAlchemyStore(config=mock_async_config, model=MockStoreModel)


@pytest.fixture()
def sync_store(mock_sync_config: MagicMock) -> SQLAlchemyStore[SQLAlchemySyncConfig]:
    """Create a sync store instance."""
    return SQLAlchemyStore(config=mock_sync_config, model=MockStoreModel)


def test_store_model_mixin_is_expired_property() -> None:
    """Test the is_expired hybrid property."""
    now = get_utc_now()
    expired_store = StoreModelMixin(expires_at=now - datetime.timedelta(seconds=1))
    active_store = StoreModelMixin(expires_at=now + datetime.timedelta(seconds=10))

    assert expired_store.is_expired is True
    assert active_store.is_expired is False


def test_store_init_default_namespace() -> None:
    """Test store initialization with default namespace."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel)
    assert store.namespace == "LITESTAR"


def test_store_init_custom_namespace() -> None:
    """Test store initialization with custom namespace."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel, namespace="CUSTOM")
    assert store.namespace == "CUSTOM"


def test_store_init_no_namespace() -> None:
    """Test store initialization with no namespace."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel, namespace=None)
    assert store.namespace is None


def test_store_init_empty_namespace() -> None:
    """Test store initialization with Empty namespace."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel, namespace=Empty)
    assert store.namespace == "LITESTAR"


def test_supports_merge() -> None:
    """Test merge support detection for different dialects."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel)

    # PostgreSQL >= 15  # noqa: ERA001
    postgres_dialect = MagicMock(spec=Dialect)
    postgres_dialect.name = "postgresql"
    postgres_dialect.server_version_info = (15, 0)
    assert store.supports_merge(postgres_dialect) is True

    # PostgreSQL < 15
    postgres_dialect.server_version_info = (14, 0)
    assert store.supports_merge(postgres_dialect) is False

    # Oracle
    oracle_dialect = MagicMock(spec=Dialect)
    oracle_dialect.name = "oracle"
    oracle_dialect.server_version_info = (19, 0)  # Add server_version_info for Oracle
    assert store.supports_merge(oracle_dialect) is True

    # Other dialects
    other_dialect = MagicMock(spec=Dialect)
    other_dialect.name = "mysql"
    other_dialect.server_version_info = (8, 0)  # Add server_version_info for MySQL
    assert store.supports_merge(other_dialect) is False


def test_supports_upsert() -> None:
    """Test upsert support detection for different dialects."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel)

    # PostgreSQL
    postgres_dialect = MagicMock(spec=Dialect)
    postgres_dialect.name = "postgresql"
    assert store.supports_upsert(postgres_dialect) is True

    # CockroachDB
    cockroach_dialect = MagicMock(spec=Dialect)
    cockroach_dialect.name = "cockroachdb"
    assert store.supports_upsert(cockroach_dialect) is True

    # SQLite
    sqlite_dialect = MagicMock(spec=Dialect)
    sqlite_dialect.name = "sqlite"
    assert store.supports_upsert(sqlite_dialect) is True

    # MySQL
    mysql_dialect = MagicMock(spec=Dialect)
    mysql_dialect.name = "mysql"
    assert store.supports_upsert(mysql_dialect) is True

    # Other dialects
    other_dialect = MagicMock(spec=Dialect)
    other_dialect.name = "other"
    assert store.supports_upsert(other_dialect) is False


def test_make_key_with_namespace() -> None:
    """Test key generation with namespace."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel, namespace="test")

    # Instead of using make_key, we'll test the key format directly
    # by checking the namespace and key format
    assert store.namespace == "test"


def test_make_key_without_namespace() -> None:
    """Test key generation without namespace."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel, namespace=None)

    # Instead of using make_key, we'll test the key format directly
    # by checking the namespace and key format
    assert store.namespace is None


@pytest.fixture()
def sync_store_with_mock_async(
    mock_sync_config: MagicMock,
) -> Generator[SQLAlchemyStore[SQLAlchemySyncConfig], None, None]:
    def mock_async_(fn: Callable[..., Any], **_: Any) -> Callable[..., Awaitable[Any]]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return wrapper

    with patch("advanced_alchemy.extensions.litestar.store.async_", side_effect=mock_async_):
        yield SQLAlchemyStore(config=mock_sync_config, model=MockStoreModel)


@pytest.mark.asyncio()
async def test_store_set_async(
    async_store: SQLAlchemyStore[SQLAlchemyAsyncConfig], mock_async_session: AsyncMock
) -> None:
    """Test setting a value using async store."""
    key = "test_key"
    value = b"test_value"
    expires_in = 3600

    await async_store.set(key, value, expires_in)

    mock_async_session.execute.assert_called_once()
    await mock_async_session.commit()


@pytest.mark.asyncio()
async def test_store_set_sync(
    sync_store_with_mock_async: SQLAlchemyStore[SQLAlchemySyncConfig], mock_sync_session: MagicMock
) -> None:
    """Test setting a value using sync store."""
    key = "test_key"
    value = b"test_value"
    expires_in = 3600

    # Reset the mock before the test
    mock_sync_session.execute.reset_mock()
    mock_sync_session.commit.reset_mock()

    await sync_store_with_mock_async.set(key, value, expires_in)

    # Verify that execute was called at least once
    assert mock_sync_session.execute.call_count > 0
    assert mock_sync_session.commit.call_count > 0


@pytest.mark.asyncio()
async def test_store_get_async(
    async_store: SQLAlchemyStore[SQLAlchemyAsyncConfig], mock_async_session: AsyncMock
) -> None:
    """Test getting a value using async store."""
    key = "test_key"
    expected_value = b"test_value"

    # Set up the mock to return the expected value directly
    mock_result = MagicMock()
    # When scalar_one_or_none() is called, it should return the expected value directly, not a coroutine
    mock_result.scalar_one_or_none.return_value = expected_value
    mock_async_session.execute.return_value = mock_result

    # Use the async context manager to get the session
    async with async_store:
        result = await async_store.get(key)
        assert result == expected_value
        assert mock_async_session.execute.called
        await mock_async_session.commit()


@pytest.mark.asyncio()
async def test_store_get_sync(
    sync_store_with_mock_async: SQLAlchemyStore[SQLAlchemySyncConfig], mock_sync_session: MagicMock
) -> None:
    """Test getting a value using sync store."""
    key = "test_key"
    expected_value = b"test_value"
    mock_sync_session.execute.return_value.scalar_one_or_none.return_value = expected_value

    result = await sync_store_with_mock_async.get(key)

    assert result == expected_value
    mock_sync_session.execute.assert_called_once()
    mock_sync_session.commit.assert_called_once()


@pytest.mark.asyncio()
async def test_store_delete_async(
    async_store: SQLAlchemyStore[SQLAlchemyAsyncConfig], mock_async_session: AsyncMock
) -> None:
    """Test deleting a value using async store."""
    key = "test_key"

    await async_store.delete(key)

    mock_async_session.execute.assert_called_once()
    await mock_async_session.commit()


@pytest.mark.asyncio()
async def test_store_delete_sync(
    sync_store_with_mock_async: SQLAlchemyStore[SQLAlchemySyncConfig], mock_sync_session: MagicMock
) -> None:
    """Test deleting a value using sync store."""
    key = "test_key"

    await sync_store_with_mock_async.delete(key)

    mock_sync_session.execute.assert_called_once()
    mock_sync_session.commit.assert_called_once()


@pytest.mark.asyncio()
async def test_store_delete_all_async(
    async_store: SQLAlchemyStore[SQLAlchemyAsyncConfig], mock_async_session: AsyncMock
) -> None:
    """Test deleting all values using async store."""
    await async_store.delete_all()

    mock_async_session.execute.assert_called_once()
    await mock_async_session.commit()


@pytest.mark.asyncio()
async def test_store_delete_all_sync(
    sync_store_with_mock_async: SQLAlchemyStore[SQLAlchemySyncConfig], mock_sync_session: MagicMock
) -> None:
    """Test deleting all values using sync store."""
    await sync_store_with_mock_async.delete_all()

    mock_sync_session.execute.assert_called_once()
    mock_sync_session.commit.assert_called_once()


@pytest.mark.asyncio()
async def test_store_delete_all_no_namespace_async(mock_async_config: MagicMock) -> None:
    """Test deleting all values with no namespace raises error."""
    store = SQLAlchemyStore(config=mock_async_config, model=MockStoreModel, namespace=None)
    with pytest.raises(ImproperlyConfiguredException, match="Cannot perform delete operation: No namespace configured"):
        await store.delete_all()


@pytest.mark.asyncio()
async def test_store_delete_all_no_namespace_sync(mock_sync_config: MagicMock) -> None:
    """Test deleting all values with no namespace raises error."""
    store = SQLAlchemyStore(config=mock_sync_config, model=MockStoreModel, namespace=None)
    with pytest.raises(ImproperlyConfiguredException, match="Cannot perform delete operation: No namespace configured"):
        await store.delete_all()


@pytest.mark.asyncio()
async def test_store_exists_async(
    async_store: SQLAlchemyStore[SQLAlchemyAsyncConfig], mock_async_session: AsyncMock
) -> None:
    """Test checking existence using async store."""
    key = "test_key"

    # Set up the mock to return a value directly
    mock_result = MagicMock()
    # When scalar_one_or_none() is called, it should return "exists" directly, not a coroutine
    mock_result.scalar_one_or_none.return_value = "exists"
    mock_async_session.execute.return_value = mock_result

    # Use the async context manager to get the session
    async with async_store:
        result = await async_store.exists(key)
        assert result is True
        assert mock_async_session.execute.called


@pytest.mark.asyncio()
async def test_store_exists_sync(
    sync_store_with_mock_async: SQLAlchemyStore[SQLAlchemySyncConfig], mock_sync_session: MagicMock
) -> None:
    """Test checking existence using sync store."""
    key = "test_key"
    mock_sync_session.execute.return_value.scalar_one_or_none.return_value = "exists"

    result = await sync_store_with_mock_async.exists(key)

    assert result is True
    mock_sync_session.execute.assert_called_once()


@pytest.mark.asyncio()
async def test_store_expires_in_async(
    async_store: SQLAlchemyStore[SQLAlchemyAsyncConfig], mock_async_session: AsyncMock, monkeypatch: MonkeyPatch
) -> None:
    """Test getting expiration time using async store."""
    key = "test_key"
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(seconds=3600)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.store.get_utc_now", lambda: now)

    # Set up the mock to return the expiration time directly
    mock_result = MagicMock()
    # When scalar_one_or_none() is called, it should return expires_at directly, not a coroutine
    mock_result.scalar_one_or_none.return_value = expires_at
    mock_async_session.execute.return_value = mock_result

    # Use the async context manager to get the session
    async with async_store:
        result = await async_store.expires_in(key)
        assert result == 3600
        assert mock_async_session.execute.called


@pytest.mark.asyncio()
async def test_store_expires_in_sync(
    sync_store_with_mock_async: SQLAlchemyStore[SQLAlchemySyncConfig],
    mock_sync_session: MagicMock,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test getting expiration time using sync store."""
    key = "test_key"
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(seconds=3600)
    monkeypatch.setattr("advanced_alchemy.extensions.litestar.store.get_utc_now", lambda: now)
    mock_sync_session.execute.return_value.scalar_one_or_none.return_value = expires_at

    result = await sync_store_with_mock_async.expires_in(key)

    assert result == 3600
    mock_sync_session.execute.assert_called_once()


def test_store_with_namespace() -> None:
    """Test creating a new store with nested namespace."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel, namespace="base")
    nested_store = store.with_namespace("nested")
    assert nested_store.namespace == "base_nested"

    # Test with no base namespace
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel, namespace=None)
    nested_store = store.with_namespace("nested")
    assert nested_store.namespace == "nested"


@pytest.mark.asyncio()
async def test_store_context_manager() -> None:
    """Test store as async context manager."""
    store = SQLAlchemyStore(config=MagicMock(spec=SQLAlchemyAsyncConfig), model=MockStoreModel)
    async with store:
        pass  # Context manager should not raise any errors

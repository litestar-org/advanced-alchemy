"""Tests for deprecated method names scheduled for removal in 2.0.

All deprecation warnings for the list() -> get_many() rename live here.
"""

from typing import Any, cast
from unittest.mock import MagicMock, create_autospec

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy import base
from advanced_alchemy.repository._async import SQLAlchemyAsyncQueryRepository, SQLAlchemyAsyncRepository
from advanced_alchemy.repository._sync import SQLAlchemySyncQueryRepository, SQLAlchemySyncRepository
from advanced_alchemy.repository.memory._async import SQLAlchemyAsyncMockRepository
from advanced_alchemy.repository.memory._sync import SQLAlchemySyncMockRepository
from advanced_alchemy.repository.memory.base import InMemoryStore
from advanced_alchemy.service._async import SQLAlchemyAsyncRepositoryReadService
from advanced_alchemy.service._sync import SQLAlchemySyncRepositoryReadService
from tests.helpers import maybe_async


class DeprecationTestModel(base.UUIDAuditBase):
    __tablename__ = "deprecation_test_model"


def _make_async_session() -> AsyncSession:
    session = cast(AsyncSession, create_autospec(AsyncSession, instance=True))
    engine = cast(AsyncEngine, create_autospec(AsyncEngine, instance=True))
    engine.dialect.name = "mock"
    session.bind = engine
    session.get_bind.return_value = engine  # type: ignore[union-attr]
    return session


def _make_sync_session() -> Session:
    return MagicMock(spec=Session, bind=MagicMock())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def async_repo() -> SQLAlchemyAsyncRepository[MagicMock]:
    class Repo(SQLAlchemyAsyncRepository[MagicMock]):
        model_type = MagicMock(__name__="MagicMock")  # pyright: ignore[reportGeneralTypeIssues,reportAssignmentType]

    return Repo(session=_make_async_session(), statement=MagicMock())


@pytest.fixture()
def sync_repo() -> SQLAlchemySyncRepository[MagicMock]:
    class Repo(SQLAlchemySyncRepository[MagicMock]):
        model_type = MagicMock(__name__="MagicMock")  # pyright: ignore[reportGeneralTypeIssues,reportAssignmentType]

    return Repo(session=_make_sync_session(), statement=MagicMock())


@pytest.fixture()
async def async_query_repo() -> SQLAlchemyAsyncQueryRepository:
    return SQLAlchemyAsyncQueryRepository(session=_make_async_session(), statement=MagicMock())


@pytest.fixture()
def sync_query_repo() -> SQLAlchemySyncQueryRepository:
    return SQLAlchemySyncQueryRepository(session=_make_sync_session(), statement=MagicMock())


@pytest.fixture()
def async_mem_repo() -> SQLAlchemyAsyncMockRepository[Any]:
    class Repo(SQLAlchemyAsyncMockRepository[Any]):
        model_type = DeprecationTestModel

    return Repo(session=_make_async_session())


@pytest.fixture()
def sync_mem_repo() -> SQLAlchemySyncMockRepository[Any]:
    class Repo(SQLAlchemySyncMockRepository[Any]):
        model_type = DeprecationTestModel

    return Repo(session=_make_sync_session())


@pytest.fixture()
async def async_service(async_repo: SQLAlchemyAsyncRepository[Any]) -> SQLAlchemyAsyncRepositoryReadService[Any, Any]:
    class Service(SQLAlchemyAsyncRepositoryReadService[Any, Any]):
        repository_type = type(async_repo)  # type: ignore[assignment]

    service = Service.__new__(Service)
    service._repository_instance = async_repo  # type: ignore[assignment]
    return service


@pytest.fixture()
def sync_service(sync_repo: SQLAlchemySyncRepository[Any]) -> SQLAlchemySyncRepositoryReadService[Any, Any]:
    class Service(SQLAlchemySyncRepositoryReadService[Any, Any]):
        repository_type = type(sync_repo)  # type: ignore[assignment]

    service = Service.__new__(Service)
    service._repository_instance = sync_repo  # type: ignore[assignment]
    return service


@pytest.fixture()
def cache_manager() -> Any:
    try:
        from advanced_alchemy.cache.manager import CacheManager
    except Exception:
        pytest.skip("dogpile.cache not installed")

    cm = MagicMock(spec=CacheManager)
    # Bind the real deprecated methods so they fire warn_deprecation
    cm.get_list_sync = CacheManager.get_list_sync.__get__(cm)
    cm.set_list_sync = CacheManager.set_list_sync.__get__(cm)
    cm.get_list_and_count_sync = CacheManager.get_list_and_count_sync.__get__(cm)
    cm.set_list_and_count_sync = CacheManager.set_list_and_count_sync.__get__(cm)
    cm.get_list_async = CacheManager.get_list_async.__get__(cm)
    cm.set_list_async = CacheManager.set_list_async.__get__(cm)
    cm.get_list_and_count_async = CacheManager.get_list_and_count_async.__get__(cm)
    cm.set_list_and_count_async = CacheManager.set_list_and_count_async.__get__(cm)
    return cm


# ---------------------------------------------------------------------------
# Repository: list() -> get_many()
# ---------------------------------------------------------------------------


async def test_async_repo_list_emits_deprecation(
    async_repo: SQLAlchemyAsyncRepository[Any],
    mocker: Any,
) -> None:
    mocker.patch.object(async_repo, "get_many", return_value=[])
    with pytest.warns(DeprecationWarning, match="list"):
        await async_repo.list()


async def test_sync_repo_list_emits_deprecation(
    sync_repo: SQLAlchemySyncRepository[Any],
    mocker: Any,
) -> None:
    mocker.patch.object(sync_repo, "get_many", return_value=[])
    with pytest.warns(DeprecationWarning, match="list"):
        await maybe_async(sync_repo.list())


# ---------------------------------------------------------------------------
# Repository: list_and_count() -> get_many_and_count()
# ---------------------------------------------------------------------------


async def test_async_repo_list_and_count_emits_deprecation(
    async_repo: SQLAlchemyAsyncRepository[Any],
    mocker: Any,
) -> None:
    mocker.patch.object(async_repo, "get_many_and_count", return_value=([], 0))
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await async_repo.list_and_count()


async def test_sync_repo_list_and_count_emits_deprecation(
    sync_repo: SQLAlchemySyncRepository[Any],
    mocker: Any,
) -> None:
    mocker.patch.object(sync_repo, "get_many_and_count", return_value=([], 0))
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await maybe_async(sync_repo.list_and_count())


# ---------------------------------------------------------------------------
# QueryRepository: list() -> get_many()
# ---------------------------------------------------------------------------


async def test_async_query_repo_list_emits_deprecation(
    async_query_repo: SQLAlchemyAsyncQueryRepository,
    mocker: Any,
) -> None:
    mocker.patch.object(async_query_repo, "get_many", return_value=[])
    with pytest.warns(DeprecationWarning, match="list"):
        await async_query_repo.list(MagicMock())


async def test_sync_query_repo_list_emits_deprecation(
    sync_query_repo: SQLAlchemySyncQueryRepository,
    mocker: Any,
) -> None:
    mocker.patch.object(sync_query_repo, "get_many", return_value=[])
    with pytest.warns(DeprecationWarning, match="list"):
        await maybe_async(sync_query_repo.list(MagicMock()))


async def test_async_query_repo_list_and_count_emits_deprecation(
    async_query_repo: SQLAlchemyAsyncQueryRepository,
    mocker: Any,
) -> None:
    mocker.patch.object(async_query_repo, "get_many_and_count", return_value=([], 0))
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await async_query_repo.list_and_count(MagicMock())


async def test_sync_query_repo_list_and_count_emits_deprecation(
    sync_query_repo: SQLAlchemySyncQueryRepository,
    mocker: Any,
) -> None:
    mocker.patch.object(sync_query_repo, "get_many_and_count", return_value=([], 0))
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await maybe_async(sync_query_repo.list_and_count(MagicMock()))


# ---------------------------------------------------------------------------
# Memory repo: list() -> get_many(), list_and_count() -> get_many_and_count()
# ---------------------------------------------------------------------------


async def test_async_mem_repo_list_emits_deprecation(
    async_mem_repo: SQLAlchemyAsyncMockRepository[Any],
) -> None:
    with pytest.warns(DeprecationWarning, match="list"):
        await async_mem_repo.list()


async def test_sync_mem_repo_list_emits_deprecation(
    sync_mem_repo: SQLAlchemySyncMockRepository[Any],
) -> None:
    with pytest.warns(DeprecationWarning, match="list"):
        await maybe_async(sync_mem_repo.list())


async def test_async_mem_repo_list_and_count_emits_deprecation(
    async_mem_repo: SQLAlchemyAsyncMockRepository[Any],
) -> None:
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await async_mem_repo.list_and_count()


async def test_sync_mem_repo_list_and_count_emits_deprecation(
    sync_mem_repo: SQLAlchemySyncMockRepository[Any],
) -> None:
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await maybe_async(sync_mem_repo.list_and_count())


# ---------------------------------------------------------------------------
# InMemoryStore: list() -> get_all()
# ---------------------------------------------------------------------------


def test_in_memory_store_list_emits_deprecation() -> None:
    store: InMemoryStore[str] = InMemoryStore()
    with pytest.warns(DeprecationWarning, match="list"):
        store.list()


def test_in_memory_store_get_all_returns_values() -> None:
    store: InMemoryStore[str] = InMemoryStore()
    store._store["a"] = "hello"
    store._store["b"] = "world"
    assert store.get_all() == ["hello", "world"]


# ---------------------------------------------------------------------------
# Service: list() -> get_many(), list_and_count() -> get_many_and_count()
# ---------------------------------------------------------------------------


async def test_async_service_list_emits_deprecation(
    async_service: SQLAlchemyAsyncRepositoryReadService[Any, Any],
    mocker: Any,
) -> None:
    mocker.patch.object(async_service, "get_many", return_value=[])
    with pytest.warns(DeprecationWarning, match="list"):
        await async_service.list()


async def test_sync_service_list_emits_deprecation(
    sync_service: SQLAlchemySyncRepositoryReadService[Any, Any],
    mocker: Any,
) -> None:
    mocker.patch.object(sync_service, "get_many", return_value=[])
    with pytest.warns(DeprecationWarning, match="list"):
        await maybe_async(sync_service.list())


async def test_async_service_list_and_count_emits_deprecation(
    async_service: SQLAlchemyAsyncRepositoryReadService[Any, Any],
    mocker: Any,
) -> None:
    mocker.patch.object(async_service, "get_many_and_count", return_value=([], 0))
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await async_service.list_and_count()


async def test_sync_service_list_and_count_emits_deprecation(
    sync_service: SQLAlchemySyncRepositoryReadService[Any, Any],
    mocker: Any,
) -> None:
    mocker.patch.object(sync_service, "get_many_and_count", return_value=([], 0))
    with pytest.warns(DeprecationWarning, match="list_and_count"):
        await maybe_async(sync_service.list_and_count())


# ---------------------------------------------------------------------------
# CacheManager: get_list_*/set_list_* -> get_many_*/set_many_*
# ---------------------------------------------------------------------------


def test_cache_get_list_sync_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="get_list_sync"):
        cache_manager.get_list_sync("key", MagicMock)


def test_cache_set_list_sync_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="set_list_sync"):
        cache_manager.set_list_sync("key", [])


def test_cache_get_list_and_count_sync_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="get_list_and_count_sync"):
        cache_manager.get_list_and_count_sync("key", MagicMock)


def test_cache_set_list_and_count_sync_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="set_list_and_count_sync"):
        cache_manager.set_list_and_count_sync("key", [], 0)


async def test_cache_get_list_async_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="get_list_async"):
        await cache_manager.get_list_async("key", MagicMock)


async def test_cache_set_list_async_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="set_list_async"):
        await cache_manager.set_list_async("key", [])


async def test_cache_get_list_and_count_async_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="get_list_and_count_async"):
        await cache_manager.get_list_and_count_async("key", MagicMock)


async def test_cache_set_list_and_count_async_emits_deprecation(cache_manager: Any) -> None:
    with pytest.warns(DeprecationWarning, match="set_list_and_count_async"):
        await cache_manager.set_list_and_count_async("key", [], 0)

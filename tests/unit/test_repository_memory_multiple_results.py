"""The in-memory repositories raise the same error as the SQL ones when a single row is expected."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.exceptions import MultipleResultsFoundError
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository


class MultipleBase(DeclarativeBase):
    pass


class MultipleItem(MultipleBase):
    __tablename__ = "multiple_results_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    group: Mapped[int]


class AsyncSqlRepo(SQLAlchemyAsyncRepository[MultipleItem]):
    model_type = MultipleItem


class SyncSqlRepo(SQLAlchemySyncRepository[MultipleItem]):
    model_type = MultipleItem


class AsyncMockRepo(SQLAlchemyAsyncMockRepository[MultipleItem]):
    model_type = MultipleItem


class SyncMockRepo(SQLAlchemySyncMockRepository[MultipleItem]):
    model_type = MultipleItem


def _items() -> list[MultipleItem]:
    return [
        MultipleItem(id=1, name="a", group=1),
        MultipleItem(id=2, name="b", group=1),
        MultipleItem(id=3, name="c", group=2),
    ]


@pytest.fixture
def sync_repos() -> Iterator[tuple[SyncSqlRepo, SyncMockRepo]]:
    engine = create_engine("sqlite://")
    MultipleBase.metadata.create_all(engine)
    SyncMockRepo.__database_clear__()
    with Session(engine) as session:
        sql_repo = SyncSqlRepo(session=session)
        mock_repo = SyncMockRepo(session=MagicMock(spec=Session, bind=MagicMock()))
        sql_repo.add_many(_items())
        mock_repo.add_many(_items())
        yield sql_repo, mock_repo
    SyncMockRepo.__database_clear__()
    engine.dispose()


@pytest.fixture
async def async_repos() -> "Iterator[tuple[AsyncSqlRepo, AsyncMockRepo]]":
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(MultipleBase.metadata.create_all)
    AsyncMockRepo.__database_clear__()
    async with AsyncSession(engine) as session:
        sql_repo = AsyncSqlRepo(session=session)
        mock_repo = AsyncMockRepo(session=AsyncMock(spec=AsyncSession, bind=MagicMock()))
        await sql_repo.add_many(_items())
        await mock_repo.add_many(_items())
        yield sql_repo, mock_repo
    AsyncMockRepo.__database_clear__()
    await engine.dispose()


async def test_async_get_one_or_none_with_several_matches(
    async_repos: tuple[AsyncSqlRepo, AsyncMockRepo],
) -> None:
    for repo in async_repos:
        with pytest.raises(MultipleResultsFoundError):
            await repo.get_one_or_none(group=1)


async def test_async_get_one_with_several_matches(async_repos: tuple[AsyncSqlRepo, AsyncMockRepo]) -> None:
    for repo in async_repos:
        with pytest.raises(MultipleResultsFoundError):
            await repo.get_one(group=1)


def test_sync_get_one_or_none_with_several_matches(sync_repos: tuple[SyncSqlRepo, SyncMockRepo]) -> None:
    for repo in sync_repos:
        with pytest.raises(MultipleResultsFoundError):
            repo.get_one_or_none(group=1)


def test_sync_get_one_with_several_matches(sync_repos: tuple[SyncSqlRepo, SyncMockRepo]) -> None:
    for repo in sync_repos:
        with pytest.raises(MultipleResultsFoundError):
            repo.get_one(group=1)


async def test_async_single_and_missing_matches_are_unchanged(
    async_repos: tuple[AsyncSqlRepo, AsyncMockRepo],
) -> None:
    for repo in async_repos:
        found = await repo.get_one_or_none(name="c")
        assert found is not None
        assert found.id == 3
        assert await repo.get_one_or_none(name="missing") is None

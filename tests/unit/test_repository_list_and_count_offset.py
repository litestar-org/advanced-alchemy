"""``get_many_and_count`` reports the total for a page that lies past the last row."""

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.filters import FilterSet, LimitOffsetFilter, SearchFilter
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository

ROWS = 5


class OffsetBase(DeclarativeBase):
    pass


class OffsetItem(OffsetBase):
    __tablename__ = "list_and_count_offset_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class AsyncOffsetItemRepository(SQLAlchemyAsyncRepository[OffsetItem]):
    model_type = OffsetItem


class SyncOffsetItemRepository(SQLAlchemySyncRepository[OffsetItem]):
    model_type = OffsetItem


@pytest.fixture
def sync_repo() -> Iterator[SyncOffsetItemRepository]:
    engine = create_engine("sqlite://")
    OffsetBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([OffsetItem(id=i, name=f"item{i}") for i in range(1, ROWS + 1)])
        session.commit()
        yield SyncOffsetItemRepository(session=session)
    engine.dispose()


@pytest.fixture
async def async_repo() -> AsyncIterator[AsyncOffsetItemRepository]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(OffsetBase.metadata.create_all)
    async with AsyncSession(engine) as session:
        session.add_all([OffsetItem(id=i, name=f"item{i}") for i in range(1, ROWS + 1)])
        await session.commit()
        yield AsyncOffsetItemRepository(session=session)
    await engine.dispose()


async def test_async_offset_past_the_last_row_keeps_the_total(async_repo: AsyncOffsetItemRepository) -> None:
    items, total = await async_repo.get_many_and_count(LimitOffsetFilter(limit=2, offset=50))

    assert items == []
    assert total == ROWS


def test_sync_offset_past_the_last_row_keeps_the_total(sync_repo: SyncOffsetItemRepository) -> None:
    items, total = sync_repo.get_many_and_count(LimitOffsetFilter(limit=2, offset=50))

    assert items == []
    assert total == ROWS


async def test_async_offset_past_the_last_row_counts_only_the_matching_rows(
    async_repo: AsyncOffsetItemRepository,
) -> None:
    items, total = await async_repo.get_many_and_count(
        SearchFilter(field_name="name", value="item1"), LimitOffsetFilter(limit=2, offset=50)
    )

    assert items == []
    assert total == 1


async def test_async_filterset_offset_past_the_last_row_keeps_the_total(
    async_repo: AsyncOffsetItemRepository,
) -> None:
    class ItemFilters(FilterSet[OffsetItem]):
        pagination_type = "limit_offset"

    # page 26 of size 2 is an offset of 50, past the last row
    items, total = await async_repo.get_many_and_count(ItemFilters(page=26, page_size=2))

    assert items == []
    assert total == ROWS


async def test_async_limit_zero_keeps_the_total(async_repo: AsyncOffsetItemRepository) -> None:
    items, total = await async_repo.get_many_and_count(LimitOffsetFilter(limit=0, offset=0))

    assert items == []
    assert total == ROWS


def test_sync_limit_zero_keeps_the_total(sync_repo: SyncOffsetItemRepository) -> None:
    items, total = sync_repo.get_many_and_count(LimitOffsetFilter(limit=0, offset=0))

    assert items == []
    assert total == ROWS


async def test_async_page_inside_the_range_is_unchanged(async_repo: AsyncOffsetItemRepository) -> None:
    items, total = await async_repo.get_many_and_count(LimitOffsetFilter(limit=2, offset=4))

    assert [item.id for item in items] == [5]
    assert total == ROWS


async def test_async_no_match_without_offset_is_empty(async_repo: AsyncOffsetItemRepository) -> None:
    items, total = await async_repo.get_many_and_count(
        SearchFilter(field_name="name", value="missing"), LimitOffsetFilter(limit=2, offset=0)
    )

    assert items == []
    assert total == 0

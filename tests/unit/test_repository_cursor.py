"""Cursor pagination through SQL and in-memory repositories."""

import enum
from collections.abc import Iterator
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Enum as SAEnum
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import (
    CursorFilter,
    CursorKey,
    FilterSet,
    LimitOffsetFilter,
    OrderByFilter,
    SearchFilter,
    StatementFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.repository.memory import SQLAlchemySyncMockRepository


class CursorRepoBase(DeclarativeBase):
    pass


class ArticleStatus(enum.Enum):
    ARCHIVED = "z"
    DRAFT = "m"
    PUBLISHED = "a"


class NonOrderableTag(enum.Enum):
    ALPHA = {"rank": 1}
    BETA = {"rank": 2}


class Article(CursorRepoBase):
    __tablename__ = "cursor_repo_article"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    views: Mapped[int]
    rating: Mapped[Optional[int]]
    status: Mapped[ArticleStatus] = mapped_column(SAEnum(ArticleStatus), default=ArticleStatus.DRAFT)


class TaggedArticle(CursorRepoBase):
    __tablename__ = "cursor_repo_tagged_article"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[NonOrderableTag] = mapped_column(SAEnum(NonOrderableTag))


class Articles(FilterSet[Article]):
    filter_fields = {"views": {"ge"}}
    config = {"pagination_type": "limit_offset", "pagination_size": 5}


class ArticleRepository(SQLAlchemySyncRepository[Article]):
    pass


class TitleOrderedRepository(SQLAlchemySyncRepository[Article]):
    order_by = [(Article.title, True)]


class AsyncArticleRepository(SQLAlchemyAsyncRepository[Article]):
    pass


class ArticleMockRepository(SQLAlchemySyncMockRepository[Article]):
    pass


def seed() -> list[Article]:
    statuses = list(ArticleStatus)
    return [
        Article(
            id=i,
            title=f"t{i % 6}",
            views=i % 4,
            rating=None if i % 5 == 0 else i % 3,
            status=statuses[i % len(statuses)],
        )
        for i in range(1, 27)
    ]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    CursorRepoBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(seed())
        db.commit()
        yield db
    engine.dispose()


@pytest.fixture
def mock_repo() -> Iterator[ArticleMockRepository]:
    ArticleMockRepository.__database_clear__()
    repo = ArticleMockRepository(session=MagicMock(spec=Session))
    repo.add_many(seed())
    yield repo
    ArticleMockRepository.__database_clear__()


def walk(get_many: Any, keys: Any, limit: int, *extra: StatementFilter) -> tuple[list[int], list[int]]:
    """Walk every page forward, then back from the last page; return both id sequences."""
    forward: list[int] = []
    cursor: Optional[str] = None
    last: Any = None
    while True:
        cursor_filter = CursorFilter(keys, limit, cursor)
        page = cursor_filter.build_page(get_many(*extra, cursor_filter), model=Article)
        forward.extend(item.id for item in page.items)
        last = page
        if not page.has_next:
            break
        cursor = page.next_cursor
    backward: list[int] = [item.id for item in last.items]
    cursor = last.previous_cursor
    while cursor is not None:
        cursor_filter = CursorFilter(keys, limit, cursor)
        page = cursor_filter.build_page(get_many(*extra, cursor_filter), model=Article)
        backward = [item.id for item in page.items] + backward
        cursor = page.previous_cursor
    return forward, backward


@pytest.mark.parametrize(
    "conflict",
    [
        [OrderByFilter("title")],
        [LimitOffsetFilter(5, 0)],
        [CursorFilter("views", 5)],
        [Articles(views__ge=1)],
    ],
)
def test_conflicting_pagination_filters_are_rejected(session: Session, conflict: list[StatementFilter]) -> None:
    repo = ArticleRepository(session=session)

    with pytest.raises(ImproperConfigurationError):
        repo.get_many(CursorFilter("views", 5), *conflict)
    with pytest.raises(ImproperConfigurationError):
        repo.get_many_and_count(CursorFilter("views", 5), *conflict)


def test_conflicting_pagination_filters_are_rejected_in_memory(mock_repo: ArticleMockRepository) -> None:
    with pytest.raises(ImproperConfigurationError):
        mock_repo.get_many(CursorFilter("views", 5), OrderByFilter("title"))


def test_cursor_filter_position_does_not_change_the_query(session: Session) -> None:
    repo = ArticleRepository(session=session)
    search = SearchFilter("title", "t1")

    first = repo.get_many(CursorFilter("views", 3), search)
    last = repo.get_many(search, CursorFilter("views", 3))

    assert [a.id for a in first] == [a.id for a in last]
    assert all(a.title == "t1" for a in first)


def test_repository_default_order_by_is_replaced(session: Session) -> None:
    every_id = sorted(seed(), key=lambda a: (-a.views, -a.id))

    forward, backward = walk(TitleOrderedRepository(session=session).get_many, [("views", "desc")], 4)

    assert forward == backward == [a.id for a in every_id]


@pytest.mark.parametrize("count_with_window_function", [True, False])
def test_total_counts_the_full_filtered_set_on_every_page(session: Session, count_with_window_function: bool) -> None:
    repo = ArticleRepository(session=session, count_with_window_function=count_with_window_function)
    totals: list[int] = []
    cursor: Optional[str] = None
    while True:
        cursor_filter = CursorFilter("views", 7, cursor)
        rows, total = repo.get_many_and_count(SearchFilter("title", "t"), cursor_filter)
        totals.append(total)
        page = cursor_filter.build_page(rows, model=Article)
        if not page.has_next:
            break
        cursor = page.next_cursor

    assert totals == [26] * len(totals)
    assert len(totals) == 4


@pytest.mark.parametrize(
    "keys",
    [
        [],
        "title",
        [("views", "desc"), "title"],
        [CursorKey("rating")],
        [CursorKey("rating", "desc", "first")],
        [("status", "desc")],
    ],
)
def test_in_memory_walks_match_sql(session: Session, mock_repo: ArticleMockRepository, keys: Any) -> None:
    sql_forward, sql_backward = walk(ArticleRepository(session=session).get_many, keys, 4)
    memory_forward, memory_backward = walk(mock_repo.get_many, keys, 4)

    assert len(sql_forward) == 26
    assert memory_forward == sql_forward == sql_backward == memory_backward


def test_in_memory_paginate_items_handles_enums_with_non_orderable_values() -> None:
    items = [
        TaggedArticle(id=1, tag=NonOrderableTag.BETA),
        TaggedArticle(id=2, tag=NonOrderableTag.ALPHA),
        TaggedArticle(id=3, tag=NonOrderableTag.BETA),
    ]
    first_filter = CursorFilter("tag", 2)
    first_page = first_filter.build_page(first_filter.paginate_items(items, TaggedArticle), model=TaggedArticle)
    second_filter = CursorFilter("tag", 2, first_page.next_cursor)
    second_page = second_filter.build_page(second_filter.paginate_items(items, TaggedArticle), model=TaggedArticle)

    assert [item.id for item in first_page.items] == [2, 1]
    assert [item.id for item in second_page.items] == [3]


def test_in_memory_count_ignores_the_cursor(mock_repo: ArticleMockRepository) -> None:
    rows, total = mock_repo.get_many_and_count(CursorFilter("views", 5))

    assert total == 26
    assert len(rows) == 6


async def test_async_repository_walk_and_count() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(CursorRepoBase.metadata.create_all)
    async with AsyncSession(engine) as db:
        db.add_all(seed())
        await db.commit()
        repo = AsyncArticleRepository(session=db)
        ids: list[int] = []
        cursor: Optional[str] = None
        while True:
            cursor_filter = CursorFilter([("views", "desc")], 6, cursor)
            rows, total = await repo.get_many_and_count(cursor_filter)
            assert total == 26
            page = cursor_filter.build_page(rows, model=Article)
            ids.extend(a.id for a in page.items)
            if not page.has_next:
                break
            cursor = page.next_cursor
    await engine.dispose()

    assert ids == [a.id for a in sorted(seed(), key=lambda a: (-a.views, -a.id))]

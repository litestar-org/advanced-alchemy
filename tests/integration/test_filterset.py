"""FilterSet execution against the repository's supported database fixtures."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.filters import FilterSet
from tests.helpers import maybe_async
from tests.integration.test_repository import create_repository

pytestmark = [pytest.mark.integration]


def definition(model: type[Any]) -> type[FilterSet[Any]]:
    """Bind the same declaration to UUID and bigint fixture models."""

    class Authors(FilterSet[Any]):
        model_type = model
        filter_fields = {"name": {"eq"}, "books.title": {"eq"}}
        sort_fields = ("name",)
        config = {"pagination_type": "limit_offset", "pagination_size": 1}

    return Authors


async def test_filterset_database_async(seeded_test_session_async: tuple[AsyncSession, dict[str, type]]) -> None:
    """Native async drivers retain relationship filtering and unpaginated totals."""
    session, models = seeded_test_session_async
    repo = create_repository(session, models["author"])
    authors = await maybe_async(repo.get_many())
    target = authors[0]
    book = models["book"](title="FilterSet native probe", author_id=target.id)
    session.add(book)
    await maybe_async(session.flush())
    session.expire(target, ["books"])
    query = definition(models["author"])(name__eq=target.name, books__title__eq=book.title)
    rows, total = await maybe_async(repo.get_many_and_count(query))
    assert total == 1
    assert [author.id for author in rows] == [target.id]
    assert rows[0].books
    assert await maybe_async(repo.count(query)) == 1


def test_filterset_database_sync(seeded_test_session_sync: tuple[Session, dict[str, type]]) -> None:
    """Native sync drivers execute the same declaration and loading plan."""
    session, models = seeded_test_session_sync
    repo = create_repository(session, models["author"])
    authors = repo.get_many()
    target = authors[0]
    book = models["book"](title="FilterSet native probe", author_id=target.id)
    session.add(book)
    session.flush()
    session.expire(target, ["books"])
    query = definition(models["author"])(name__eq=target.name, books__title__eq=book.title)
    # Also exercise the two-query count path; DuckDB's UUID/window/EXISTS
    # combination currently raises an internal database error.
    rows, total = repo.get_many_and_count(query, count_with_window_function=False)
    assert total == 1
    assert [author.id for author in rows] == [target.id]
    assert rows[0].books
    assert repo.count(query) == 1

"""Cursor pagination against the repository's supported database fixtures."""

import datetime as dt
from typing import Any, Optional, Union

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.filters import CursorFilter, CursorKey, CursorKeys, OrderByFilter
from tests.helpers import maybe_async
from tests.integration.test_repository import create_repository

pytestmark = [pytest.mark.integration]

KEY_CASES: list[tuple[CursorKeys, list[tuple[str, str, Optional[str]]]]] = [
    ([("name", "asc")], [("name", "asc", None)]),
    ([CursorKey("dob", "desc", "last")], [("dob", "desc", "last")]),
    ([("created_at", "desc")], [("created_at", "desc", None)]),
]
KEY_CASE_IDS = ["name", "dob-nullable", "created-at"]


def _add_authors(session: Union[Session, AsyncSession], model: type[Any]) -> None:
    base = dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc)
    session.add_all(
        model(
            name=f"cursor-{index % 3}",
            dob=None if index % 4 == 0 else dt.date(1990, 1, 1 + index % 3),
            created_at=base + dt.timedelta(minutes=index % 5),
        )
        for index in range(11)
    )


async def _walk(repo: Any, model: type[Any], keys: CursorKeys) -> tuple[list[Any], list[Any], int]:
    forward: list[Any] = []
    cursor: Optional[str] = None
    total = 0
    page: Any = None
    while True:
        cursor_filter = CursorFilter(keys, 3, cursor)
        rows, total = await maybe_async(repo.get_many_and_count(cursor_filter))
        page = cursor_filter.build_page(rows, model=model)
        forward.extend(item.id for item in page.items)
        if not page.has_next:
            break
        cursor = page.next_cursor
    backward = [item.id for item in page.items]
    cursor = page.previous_cursor
    while cursor is not None:
        cursor_filter = CursorFilter(keys, 3, cursor)
        page = cursor_filter.build_page(await maybe_async(repo.get_many(cursor_filter)), model=model)
        backward = [item.id for item in page.items] + backward
        cursor = page.previous_cursor
    return forward, backward, total


async def _database_order(repo: Any, spec: list[tuple[str, str, Optional[str]]]) -> list[Any]:
    tiebreak = spec[-1][1]
    order = [OrderByFilter(name, order, nulls) for name, order, nulls in spec]  # type: ignore[arg-type]
    rows = await maybe_async(repo.get_many(*order, OrderByFilter("id", tiebreak)))  # type: ignore[arg-type]
    return [row.id for row in rows]


@pytest.mark.parametrize(("keys", "spec"), KEY_CASES, ids=KEY_CASE_IDS)
async def test_cursor_walk_async(
    seeded_test_session_async: tuple[AsyncSession, dict[str, type]],
    keys: CursorKeys,
    spec: list[tuple[str, str, Optional[str]]],
) -> None:
    """Keyset pages match the database's own ordering in both directions."""
    session, models = seeded_test_session_async
    if getattr(session.bind.dialect, "name", "").startswith("spanner"):
        pytest.skip("Spanner Emulator is not supported for cursor pagination tests")
    _add_authors(session, models["author"])
    await maybe_async(session.flush())
    repo = create_repository(session, models["author"])

    forward, backward, total = await _walk(repo, models["author"], keys)

    assert forward == backward == await _database_order(repo, spec)
    assert len(forward) == len(set(forward)) == total


@pytest.mark.parametrize(("keys", "spec"), KEY_CASES, ids=KEY_CASE_IDS)
async def test_cursor_walk_sync(
    seeded_test_session_sync: tuple[Session, dict[str, type]],
    keys: CursorKeys,
    spec: list[tuple[str, str, Optional[str]]],
) -> None:
    """Sync drivers produce the same keyset walk."""
    session, models = seeded_test_session_sync
    if getattr(session.bind.dialect, "name", "").startswith("spanner"):
        pytest.skip("Spanner Emulator is not supported for cursor pagination tests")
    _add_authors(session, models["author"])
    session.flush()
    repo = create_repository(session, models["author"])

    forward, backward, total = await _walk(repo, models["author"], keys)

    assert forward == backward == await _database_order(repo, spec)
    assert len(forward) == len(set(forward)) == total

"""Unit tests for the statement filters in :mod:`advanced_alchemy.filters`.

Covers the keyset (cursor) pagination filter and the LIKE wildcard escaping
helpers. The cursor filter is exercised end-to-end against an in-memory
SQLite database so the generated WHERE / ORDER BY / LIMIT clauses are checked
for real, without requiring an external database service.
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from typing import Any, Literal, Optional, cast

import pytest
from sqlalchemy import DateTime, Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.filters import (
    LIKE_ESCAPE_CHAR,
    Cursor,
    LimitOffset,
    MultiFilter,
    NotInSearchFilter,
    PaginationFilter,
    SearchFilter,
    escape_like_value,
)
from advanced_alchemy.service.pagination import CursorPagination

# ---------------------------------------------------------------------------
# Models and fixtures
# ---------------------------------------------------------------------------


class _CursorTestBase(DeclarativeBase):
    """Isolated declarative base so cursor test tables never collide with the shared registry."""


class ItemModel(_CursorTestBase):
    """Simple model with an auto-incrementing integer primary key."""

    __tablename__ = "cursor_test_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)


class CompositeItem(_CursorTestBase):
    """Model with a composite (pk1, pk2) primary key."""

    __tablename__ = "cursor_test_composite"

    pk1: Mapped[int] = mapped_column(Integer, primary_key=True)
    pk2: Mapped[int] = mapped_column(Integer, primary_key=True)
    score: Mapped[int] = mapped_column(Integer)


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    """An in-memory SQLite session with the cursor test tables created."""
    engine = create_engine("sqlite://")
    _CursorTestBase.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess
    engine.dispose()


def _walk_cursor(
    session: Session,
    model: type,
    field: str,
    limit: int,
    sort_order: Literal["asc", "desc"] = "asc",
    pk_attrs: tuple[str, ...] = ("id",),
) -> list[Any]:
    """Iterate every page with the Cursor filter and collect the rows in order.

    Args:
        session: The database session.
        model: The model to paginate.
        field: The field name to paginate on.
        limit: Page size.
        sort_order: "asc" or "desc".
        pk_attrs: Primary key attribute name(s) used to build the next cursor.

    Returns:
        The rows collected across all pages, in the order returned.
    """
    collected: list[Any] = []
    cursor: Optional[str] = None
    while True:
        filter_ = Cursor(limit=limit, cursor=cursor, field_name=field, sort_order=sort_order)
        rows: Any = session.execute(filter_.append_to_statement(select(model), model)).scalars().all()
        if not rows:
            break
        collected.extend(rows)
        if len(rows) < limit:
            break
        last = rows[-1]
        cursor = Cursor.encode_cursor_value(getattr(last, field), *(getattr(last, attr) for attr in pk_attrs))
    return collected


# ---------------------------------------------------------------------------
# Cursor value encoding / decoding
# ---------------------------------------------------------------------------


def test_cursor_encode_decode_roundtrip_single_value() -> None:
    cursor = Cursor.encode_cursor_value("10")
    assert Cursor.decode_cursor_value(cursor) == ("10",)


def test_cursor_encode_decode_roundtrip_multiple_values() -> None:
    cursor = Cursor.encode_cursor_value("10", "3", "99")
    assert Cursor.decode_cursor_value(cursor) == ("10", "3", "99")


def test_cursor_encode_coerces_values_to_str() -> None:
    """Non-string values (ints, datetimes) are stringified before encoding."""
    cursor = Cursor.encode_cursor_value(5, datetime.datetime(2024, 1, 1))
    assert Cursor.decode_cursor_value(cursor) == ("5", str(datetime.datetime(2024, 1, 1)))


def test_cursor_encode_is_url_safe() -> None:
    """The encoded cursor must be safe to carry in a query string."""
    cursor = Cursor.encode_cursor_value("a b", "c%d")
    assert isinstance(cursor, str)
    # urlsafe base64 never contains '+', '/' or raw spaces.
    assert "+" not in cursor
    assert "/" not in cursor
    assert " " not in cursor
    assert Cursor.decode_cursor_value(cursor) == ("a b", "c%d")


def test_cursor_decode_invalid_base64_raises() -> None:
    with pytest.raises(ValueError, match="Invalid cursor value"):
        Cursor.decode_cursor_value("not-valid-base64!!!")


# ---------------------------------------------------------------------------
# Cursor value coercion
# ---------------------------------------------------------------------------


def test_coerce_cursor_value_int() -> None:
    value = Cursor._coerce_cursor_value("42", ItemModel.score)  # pyright: ignore[reportPrivateUsage]
    assert value == 42
    assert isinstance(value, int)


def test_coerce_cursor_value_bool() -> None:
    col = type("FakeCol", (), {"type": type("FakeType", (), {"python_type": bool})})()
    assert Cursor._coerce_cursor_value("true", col) is True  # pyright: ignore[reportPrivateUsage]
    assert Cursor._coerce_cursor_value("TRUE", col) is True  # pyright: ignore[reportPrivateUsage]
    assert Cursor._coerce_cursor_value("false", col) is False  # pyright: ignore[reportPrivateUsage]


def test_coerce_cursor_value_datetime() -> None:
    value = Cursor._coerce_cursor_value("2024-01-01 00:00:00", ItemModel.created_at)  # pyright: ignore[reportPrivateUsage]
    assert value == datetime.datetime(2024, 1, 1)
    assert isinstance(value, datetime.datetime)


def test_coerce_cursor_value_int_falls_back_on_bad_input() -> None:
    value = Cursor._coerce_cursor_value("not-an-int", ItemModel.score)  # pyright: ignore[reportPrivateUsage]
    assert value == "not-an-int"


def test_coerce_cursor_value_without_python_type_returns_string() -> None:
    col = type("FakeCol", (), {"type": None})()
    assert Cursor._coerce_cursor_value("abc", col) == "abc"  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Cursor filter statement construction
# ---------------------------------------------------------------------------


def test_cursor_is_registered_in_multi_filter_map() -> None:
    assert MultiFilter._filter_map["cursor"] is Cursor  # pyright: ignore[reportPrivateUsage]


def test_cursor_is_a_limit_offset_sibling_pagination_filter() -> None:
    """Cursor and LimitOffset are both pagination filters."""
    assert issubclass(Cursor, PaginationFilter)
    assert issubclass(LimitOffset, PaginationFilter)


def test_cursor_append_to_non_select_returns_statement_unchanged() -> None:
    # A DELETE is not a Select, so the filter must leave it alone.
    delete_stmt = delete(ItemModel)
    result = Cursor(limit=2, cursor=None, field_name="score").append_to_statement(delete_stmt, ItemModel)
    assert result is delete_stmt


def test_cursor_appends_order_by_and_limit(session: Session) -> None:
    filter_ = Cursor(limit=3, cursor=None, field_name="score", sort_order="asc")
    stmt = cast("Any", filter_.append_to_statement(select(ItemModel), ItemModel))
    # ORDER BY score ASC, id ASC
    order_by = list(stmt._order_by_clause)  # pyright: ignore[reportPrivateUsage]
    assert len(order_by) == 2
    assert stmt._limit == 3  # pyright: ignore[reportPrivateUsage]


def test_cursor_descends_field_but_keeps_pk_ascending(session: Session) -> None:
    filter_ = Cursor(limit=3, cursor=None, field_name="score", sort_order="desc")
    stmt = cast("Any", filter_.append_to_statement(select(ItemModel), ItemModel))
    order_by = list(stmt._order_by_clause)  # pyright: ignore[reportPrivateUsage]
    # field.desc() renders as a UnaryExpression with the "desc" operator; the
    # primary-key tiebreaker always stays ascending for stable ordering.
    assert str(order_by[0]).endswith("DESC")
    assert str(order_by[1]).endswith("ASC")


def test_cursor_wrong_value_count_raises(session: Session) -> None:
    # ItemModel has a single PK, so the cursor must hold exactly 2 values (field + pk).
    bad_cursor = Cursor.encode_cursor_value("10")  # only the field value, no pk
    filter_ = Cursor(limit=3, cursor=bad_cursor, field_name="score")
    with pytest.raises(ValueError, match="Cursor must contain 2 value"):
        cast("Any", filter_.append_to_statement(select(ItemModel), ItemModel))


def test_cursor_rejects_invalid_cursor_string(session: Session) -> None:
    filter_ = Cursor(limit=3, cursor="!!!not-base64!!!", field_name="score")
    with pytest.raises(ValueError, match="Invalid cursor value"):
        cast("Any", filter_.append_to_statement(select(ItemModel), ItemModel))


# ---------------------------------------------------------------------------
# Cursor pagination end-to-end (in-memory SQLite)
# ---------------------------------------------------------------------------


def test_cursor_walk_unique_int_field_asc(session: Session) -> None:
    items = [ItemModel(score=i, name=f"n{i}", created_at=datetime.datetime(2024, 1, 1)) for i in range(1, 11)]
    session.add_all(items)
    session.commit()

    collected = _walk_cursor(session, ItemModel, "score", limit=3, sort_order="asc")
    assert [item.id for item in collected] == list(range(1, 11))


def test_cursor_walk_unique_int_field_desc(session: Session) -> None:
    items = [ItemModel(score=i, name=f"n{i}", created_at=datetime.datetime(2024, 1, 1)) for i in range(1, 11)]
    session.add_all(items)
    session.commit()

    collected = _walk_cursor(session, ItemModel, "score", limit=4, sort_order="desc")
    assert [item.id for item in collected] == list(range(10, 0, -1))


def test_cursor_walk_non_unique_field_with_pk_tiebreak(session: Session) -> None:
    """Rows sharing a field value must still be paginated without loss or duplication.

    A naive ``score > cursor`` comparison would drop the other rows with the
    same score; the primary-key tiebreaker is what keeps them reachable.
    """
    data = [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)]
    items = [
        ItemModel(id=pk, score=score, name=f"n{pk}", created_at=datetime.datetime(2024, 1, 1)) for pk, score in data
    ]
    session.add_all(items)
    session.commit()

    collected = _walk_cursor(session, ItemModel, "score", limit=2, sort_order="asc")
    assert [item.id for item in collected] == [1, 2, 3, 4, 5, 6]


def test_cursor_walk_non_unique_field_desc_with_pk_tiebreak(session: Session) -> None:
    data = [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)]
    items = [
        ItemModel(id=pk, score=score, name=f"n{pk}", created_at=datetime.datetime(2024, 1, 1)) for pk, score in data
    ]
    session.add_all(items)
    session.commit()

    collected = _walk_cursor(session, ItemModel, "score", limit=2, sort_order="desc")
    # ORDER BY score DESC, id ASC -> 6 (score 3), 4,5 (score 2), 1,2,3 (score 1).
    # The primary-key tiebreaker is always ascending, so ids within a score group
    # come out in ascending order even when the field itself is descending.
    assert [item.id for item in collected] == [6, 4, 5, 1, 2, 3]


def test_cursor_walk_composite_pk(session: Session) -> None:
    """Composite primary keys must be encoded into the cursor as a tiebreaker chain."""
    data = [(1, 1, 1), (1, 2, 1), (2, 1, 1), (2, 2, 2)]
    items = [CompositeItem(pk1=a, pk2=b, score=s) for a, b, s in data]
    session.add_all(items)
    session.commit()

    collected = _walk_cursor(
        session,
        CompositeItem,
        "score",
        limit=2,
        sort_order="asc",
        pk_attrs=("pk1", "pk2"),
    )
    assert [(item.pk1, item.pk2) for item in collected] == [(1, 1), (1, 2), (2, 1), (2, 2)]


def test_cursor_walk_datetime_field(session: Session) -> None:
    """Paginating on a datetime column round-trips the coerced value on the wire."""
    items = [
        ItemModel(
            id=i,
            score=0,
            name=f"n{i}",
            created_at=datetime.datetime(2024, 1, i, 12, 0, 0),
        )
        for i in range(1, 5)
    ]
    session.add_all(items)
    session.commit()

    collected = _walk_cursor(session, ItemModel, "created_at", limit=2, sort_order="asc")
    assert [item.id for item in collected] == [1, 2, 3, 4]


def test_cursor_first_page_without_cursor(session: Session) -> None:
    """A ``None`` cursor (first page) applies only ordering and limit, no WHERE."""
    session.add_all([ItemModel(score=i, name=f"n{i}", created_at=datetime.datetime(2024, 1, 1)) for i in range(1, 6)])
    session.commit()

    filter_ = Cursor(limit=2, cursor=None, field_name="score", sort_order="asc")
    stmt = cast("Any", filter_.append_to_statement(select(ItemModel), ItemModel))
    assert stmt.whereclause is None
    rows = session.execute(stmt).scalars().all()
    assert [item.id for item in rows] == [1, 2]


def test_cursor_limit_respects_page_size(session: Session) -> None:
    session.add_all([ItemModel(score=i, name=f"n{i}", created_at=datetime.datetime(2024, 1, 1)) for i in range(1, 11)])
    session.commit()

    filter_ = Cursor(limit=5, cursor=None, field_name="score", sort_order="asc")
    stmt = cast("Any", filter_.append_to_statement(select(ItemModel), ItemModel))
    rows = session.execute(stmt).scalars().all()
    assert len(rows) == 5
    assert [item.id for item in rows] == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# LIKE wildcard escaping
# ---------------------------------------------------------------------------


def test_escape_like_value_escapes_wildcards_and_escape_char() -> None:
    assert escape_like_value("plain") == "plain"
    assert escape_like_value("100%") == f"100{LIKE_ESCAPE_CHAR}%"
    assert escape_like_value("a_b") == f"a{LIKE_ESCAPE_CHAR}_b"
    # The escape character itself is escaped first so it cannot consume the
    # escapes added for the wildcards.
    assert escape_like_value("a/b") == f"a{LIKE_ESCAPE_CHAR * 2}b"
    assert escape_like_value("a%/_b") == f"a{LIKE_ESCAPE_CHAR}%{LIKE_ESCAPE_CHAR * 2}{LIKE_ESCAPE_CHAR}_b"


def test_escape_like_value_custom_escape_char() -> None:
    assert escape_like_value("50%", escape_char="\\") == "50\\%"
    assert escape_like_value("a\\b", escape_char="\\") == "a\\\\b"


def test_search_filter_compile_with_escape(session: Session) -> None:
    """Compiled SQL uses an ESCAPE clause only when escaping is enabled."""
    escaped = SearchFilter(field_name="name", value="50%", escape_wildcards=True)
    stmt = cast("Any", escaped.append_to_statement(select(ItemModel), ItemModel))
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ESCAPE" in sql.upper()

    plain = SearchFilter(field_name="name", value="50%")
    plain_stmt = cast("Any", plain.append_to_statement(select(ItemModel), ItemModel))
    plain_sql = str(plain_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ESCAPE" not in plain_sql.upper()


def test_not_in_search_filter_compile_with_escape(session: Session) -> None:
    escaped = NotInSearchFilter(field_name="name", value="a_b", escape_wildcards=True)
    stmt = cast("Any", escaped.append_to_statement(select(ItemModel), ItemModel))
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ESCAPE" in sql.upper()
    assert "NOT" in sql.upper()


def test_search_filter_literal_match_in_memory(session: Session) -> None:
    """End-to-end: escaped ``%``/``_`` match literally; unescaped act as wildcards."""
    session.add_all(
        [
            ItemModel(id=1, score=0, name="50% off deal", created_at=datetime.datetime(2024, 1, 1)),
            ItemModel(id=2, score=0, name="50x off deal", created_at=datetime.datetime(2024, 1, 1)),
        ]
    )
    session.commit()

    escaped = SearchFilter(field_name="name", value="50%", escape_wildcards=True)
    rows = session.execute(cast("Any", escaped.append_to_statement(select(ItemModel), ItemModel))).scalars().all()
    assert [item.id for item in rows] == [1]

    unescaped = SearchFilter(field_name="name", value="50%")
    rows = session.execute(cast("Any", unescaped.append_to_statement(select(ItemModel), ItemModel))).scalars().all()
    assert [item.id for item in rows] == [1, 2]


def test_cursor_pagination_dataclass() -> None:
    """CursorPagination carries the page items and the opaque next cursor."""
    page = CursorPagination(items=[1, 2, 3], next_cursor="abc")
    assert list(page.items) == [1, 2, 3]
    assert page.next_cursor == "abc"

    empty: CursorPagination[int] = CursorPagination(items=[], next_cursor=None)
    assert list(empty.items) == []
    assert empty.next_cursor is None


# ---------------------------------------------------------------------------
# Smoke check that the filter is constructible through the public alias
# ---------------------------------------------------------------------------


def test_cursor_is_importable_from_public_api() -> None:
    import advanced_alchemy.filters as filters_module

    assert hasattr(filters_module, "Cursor")
    assert hasattr(filters_module, "escape_like_value")
    assert hasattr(filters_module, "LIKE_ESCAPE_CHAR")

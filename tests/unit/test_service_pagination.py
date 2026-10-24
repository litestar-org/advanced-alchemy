"""Unit tests for cursor-based pagination in the service layer.

Covers :class:`~advanced_alchemy.service.pagination.CursorPagination` and the
``to_schema`` / ``_create_pagination`` helpers that build it from query results,
including the ``next_cursor`` derivation from the last row's sorted field value
and primary key.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import Integer
from sqlalchemy.engine.row import RowMapping
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.filters import Cursor, LimitOffset
from advanced_alchemy.service._util import (  # pyright: ignore[reportPrivateUsage]
    ResultConverter,
    _create_cursor_pagination,
    _create_pagination,
    _get_pk_values,
)
from advanced_alchemy.service.pagination import CursorPagination, OffsetPagination
from advanced_alchemy.utils.serialization import PYDANTIC_INSTALLED

pytestmark = [pytest.mark.unit]


class ItemModel(BigIntBase):
    """Model with an auto-incrementing bigint primary key."""

    __tablename__ = "cursor_service_item"

    score: Mapped[int] = mapped_column(Integer)


class ItemConverter(ResultConverter):
    """A bare result converter bound to :class:`ItemModel`."""

    model_type = ItemModel


class _FakeRowMapping(RowMapping):
    """Minimal stand-in for a SQLAlchemy row mapping backed by a dict.

    ``_data`` is avoided because the Cython ``RowMapping`` exposes it as a
    read-only C slot.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._values = data

    def __getitem__(self, key: str) -> Any:  # type: ignore[override]
        return self._values[key]

    def __len__(self) -> int:
        return len(self._values)


def _items(count: int = 3) -> list[ItemModel]:
    return [ItemModel(id=i, score=i) for i in range(1, count + 1)]


# ---------------------------------------------------------------------------
# CursorPagination dataclass
# ---------------------------------------------------------------------------


def test_cursor_pagination_dataclass() -> None:
    page = CursorPagination(items=[1, 2, 3], next_cursor="abc")
    assert list(page.items) == [1, 2, 3]
    assert page.next_cursor == "abc"

    empty: CursorPagination[int] = CursorPagination(items=[], next_cursor=None)
    assert list(empty.items) == []
    assert empty.next_cursor is None


# ---------------------------------------------------------------------------
# to_schema with cursor pagination
# ---------------------------------------------------------------------------


def test_to_schema_cursor_pagination_from_model_items() -> None:
    items = _items(3)
    cursor = Cursor(limit=3, cursor=None, field_name="score")

    result = ItemConverter().to_schema(items, filters=[cursor], pagination_type="cursor")

    assert isinstance(result, CursorPagination)
    assert list(result.items) == items
    # The next cursor is derived from the last item: (score=3, id=3).
    assert result.next_cursor is not None
    assert Cursor.decode_cursor_value(result.next_cursor) == ("3", "3")


def test_to_schema_auto_detects_cursor_from_filters() -> None:
    """When no explicit pagination_type is given, a Cursor filter selects cursor pagination."""
    items = _items(3)
    cursor = Cursor(limit=3, cursor=None, field_name="score")

    result = ItemConverter().to_schema(items, filters=[cursor])

    assert isinstance(result, CursorPagination)
    assert result.next_cursor is not None
    assert Cursor.decode_cursor_value(result.next_cursor) == ("3", "3")


def test_to_schema_defaults_to_offset_without_cursor() -> None:
    """Without a Cursor filter and no explicit type, offset pagination is used."""
    items = _items(3)
    limit_offset = LimitOffset(limit=3, offset=0)

    result = ItemConverter().to_schema(items, total=3, filters=[limit_offset])

    assert isinstance(result, OffsetPagination)
    assert result.limit == 3
    assert result.offset == 0
    assert result.total == 3


def test_to_schema_explicit_offset_ignores_present_cursor() -> None:
    """An explicit ``pagination_type='offset'`` wins even when a Cursor filter is present."""
    items = _items(3)
    cursor = Cursor(limit=3, cursor=None, field_name="score")
    limit_offset = LimitOffset(limit=3, offset=0)

    result = ItemConverter().to_schema(items, total=3, filters=[cursor, limit_offset], pagination_type="offset")

    assert isinstance(result, OffsetPagination)
    assert result.limit == 3


def test_to_schema_cursor_pagination_empty_items() -> None:
    """An empty page yields no next cursor."""
    cursor = Cursor(limit=3, cursor=None, field_name="score")

    result: Any = ItemConverter().to_schema([], filters=[cursor], pagination_type="cursor")

    assert isinstance(result, CursorPagination)
    assert list(result.items) == []
    assert result.next_cursor is None


def test_to_schema_cursor_pagination_field_defaults_to_id_without_cursor() -> None:
    """With no cursor filter the sorted field falls back to ``id`` for cursor derivation."""
    items = _items(2)

    result = ItemConverter().to_schema(items, pagination_type="cursor")

    assert isinstance(result, CursorPagination)
    # Field defaults to "id"; last item id=2, pk id=2 -> ("2", "2").
    assert result.next_cursor is not None
    assert Cursor.decode_cursor_value(result.next_cursor) == ("2", "2")


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
def test_to_schema_cursor_pagination_with_schema_type() -> None:
    """The next cursor is derived from the original models, not the converted DTOs."""

    class ItemDTO(BaseModel):
        score: int

    items = _items(2)
    cursor = Cursor(limit=2, cursor=None, field_name="score")

    result = ItemConverter().to_schema(items, filters=[cursor], schema_type=ItemDTO, pagination_type="cursor")

    assert isinstance(result, CursorPagination)
    assert [item.score for item in result.items] == [1, 2]
    assert all(isinstance(item, ItemDTO) for item in result.items)
    # Cursor still comes from the last original model (score=2, id=2).
    assert result.next_cursor is not None
    assert Cursor.decode_cursor_value(result.next_cursor) == ("2", "2")


def test_to_schema_cursor_pagination_from_row_mappings() -> None:
    """Row-mapping results (no ORM models) still produce a next cursor."""
    rows = [_FakeRowMapping({"id": i, "score": i}) for i in range(1, 4)]
    cursor = Cursor(limit=3, cursor=None, field_name="score")

    result = ItemConverter().to_schema(rows, filters=[cursor], pagination_type="cursor")

    assert isinstance(result, CursorPagination)
    assert result.next_cursor is not None
    assert Cursor.decode_cursor_value(result.next_cursor) == ("3", "3")


# ---------------------------------------------------------------------------
# _create_pagination helpers
# ---------------------------------------------------------------------------


def test_create_pagination_returns_cursor_when_filter_present() -> None:
    items = _items(1)
    cursor = Cursor(limit=1, cursor=None, field_name="score")

    result = _create_pagination(items, items, [cursor], None, None, model_type=ItemModel)

    assert isinstance(result, CursorPagination)


def test_create_pagination_returns_offset_when_no_cursor() -> None:
    items = _items(1)
    limit_offset = LimitOffset(limit=1, offset=0)

    result = _create_pagination(items, items, [limit_offset], 1, None, model_type=ItemModel)

    assert isinstance(result, OffsetPagination)
    assert result.total == 1


def test_create_cursor_pagination_without_cursor_uses_id_field() -> None:
    items = _items(2)

    result = _create_cursor_pagination(None, items, items, [], model_type=ItemModel)

    assert isinstance(result, CursorPagination)
    assert result.next_cursor is not None
    assert Cursor.decode_cursor_value(result.next_cursor) == ("2", "2")


def test_create_cursor_pagination_no_items_no_cursor() -> None:
    result = _create_cursor_pagination(None, [], [], [], model_type=ItemModel)

    assert isinstance(result, CursorPagination)
    assert result.next_cursor is None


# ---------------------------------------------------------------------------
# _get_pk_values
# ---------------------------------------------------------------------------


def test_get_pk_values_from_model() -> None:
    item = ItemModel(id=5, score=9)
    assert _get_pk_values(item, ItemModel) == (5,)


def test_get_pk_values_from_model_falls_back_to_own_class() -> None:
    """When model_type is None the item's own class supplies the table."""
    item = ItemModel(id=8, score=1)
    assert _get_pk_values(item, None) == (8,)


def test_get_pk_values_from_row_mapping() -> None:
    row = _FakeRowMapping({"id": 4, "score": 2})
    assert _get_pk_values(row, ItemModel) == (4,)


def test_get_pk_values_unknown_type_returns_none() -> None:
    class NotAModel:
        id = 1

    assert _get_pk_values(NotAModel(), None) is None


def test_get_pk_values_composite_pk() -> None:
    """Composite primary keys are returned in table column order."""

    class _Base(DeclarativeBase):
        pass

    class _Composite(_Base):
        __tablename__ = "cursor_service_composite"
        pk1: Mapped[int] = mapped_column(Integer, primary_key=True)
        pk2: Mapped[int] = mapped_column(Integer, primary_key=True)

    item = _Composite(pk1=1, pk2=2)
    assert _get_pk_values(item, _Composite) == (1, 2)

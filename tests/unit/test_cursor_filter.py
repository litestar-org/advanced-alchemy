"""CursorFilter statement construction, page building, and full keyset walks on SQLite."""

import base64
import datetime as dt
import enum
import functools
import json
import pickle
import re
from collections.abc import Iterator, Sequence
from decimal import Decimal
from typing import Any, Optional

import pytest
from sqlalchemy import (
    Boolean,
    DateTime,
    Delete,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    TypeDecorator,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, column_property, mapped_column, relationship

from advanced_alchemy.exceptions import ImproperConfigurationError, InvalidCursorError, MissingDependencyError
from advanced_alchemy.filters import CursorFilter, CursorKey, OrderByFilter, normalize_cursor_keys
from advanced_alchemy.filters._cursor import order_fingerprint
from advanced_alchemy.service.pagination import CursorPagination


class Base(DeclarativeBase):
    pass


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class Owner(Base):
    __tablename__ = "cursor_owner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class Item(Base):
    __tablename__ = "cursor_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    color: Mapped[Color] = mapped_column(SAEnum(Color))
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cursor_owner.id"), nullable=True)
    owner: Mapped[Optional[Owner]] = relationship(Owner)


class CompositeItem(Base):
    __tablename__ = "cursor_composite"

    tenant: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(20))


class Renamed(Base):
    __tablename__ = "cursor_renamed"

    ident: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    amount: Mapped[int] = mapped_column("amount_col", Integer)


class Level(enum.Enum):
    LOW = 1
    HIGH = 2


class LevelType(TypeDecorator[Level]):
    impl = Integer
    cache_ok = True

    @property
    def python_type(self) -> type[Level]:
        return Level

    def process_bind_param(self, value: Optional[Level], dialect: Any) -> Optional[int]:
        return None if value is None else value.value

    def process_result_value(self, value: Optional[int], dialect: Any) -> Optional[Level]:
        return None if value is None else Level(value)


class UntypedLevelType(TypeDecorator[Level]):
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Optional[Level], dialect: Any) -> Optional[int]:
        return None if value is None else value.value

    def process_result_value(self, value: Optional[int], dialect: Any) -> Optional[Level]:
        return None if value is None else Level(value)


class Job(Base):
    __tablename__ = "cursor_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[Level] = mapped_column(LevelType())
    untyped_level: Mapped[Level] = mapped_column(UntypedLevelType())
    weight: Mapped[int] = mapped_column(Integer)
    half: Mapped[Optional[int]] = column_property(func.nullif(weight, 0))


class TypedColumns(Base):
    __tablename__ = "cursor_typed_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean)
    optional_active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ratio: Mapped[float] = mapped_column(Float)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))


BASE_TIME = dt.datetime(2026, 1, 1, 12, 0, 0)
PG_DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call,unused-ignore]


@pytest.fixture(scope="module")
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        colors = list(Color)
        db.add_all(
            Item(
                id=i,
                name=f"item-{i % 13:02d}",
                score=i % 5,
                created_at=BASE_TIME if i <= 30 else BASE_TIME + dt.timedelta(minutes=i),
                rank=None if i % 4 == 0 else i % 7,
                color=colors[i % 3],
            )
            for i in range(1, 56)
        )
        db.add_all(CompositeItem(tenant=t, seq=s, label=f"{(t * s) % 4}") for t in range(1, 5) for s in range(1, 8))
        db.add_all(Renamed(ident=i, amount=i % 6) for i in range(1, 24))
        levels = list(Level)
        db.add_all(Job(id=i, level=levels[i % 2], untyped_level=levels[i % 2], weight=i % 3) for i in range(1, 10))
        db.add_all(
            TypedColumns(
                id=i,
                active=bool(i % 2),
                optional_active=None if i % 3 == 0 else bool(i % 2),
                ratio=float(i) / 2.0,
                price=Decimal(f"{i}.50"),
            )
            for i in range(1, 13)
        )
        db.commit()
        yield db


def _compare(a: Any, b: Any) -> int:
    return int(a > b) - int(a < b)


def expected_order(rows: Sequence[Any], spec: Sequence[tuple[str, str, Optional[str]]]) -> list[Any]:
    """Sort like the database: each key with its direction and explicit NULL placement."""

    def cmp(left: Any, right: Any) -> int:
        for attr, order, nulls in spec:
            lv, rv = getattr(left, attr), getattr(right, attr)
            if lv is None or rv is None:
                if lv is None and rv is None:
                    continue
                left_first = (lv is None) == (nulls == "first")
                return -1 if left_first else 1
            result = _compare(lv, rv)
            if result:
                return result if order == "asc" else -result
        return 0

    return sorted(rows, key=functools.cmp_to_key(cmp))


def walk_forward(db: Session, model: Any, keys: Any, limit: int, **kwargs: Any) -> list[CursorPagination[Any]]:
    pages: list[CursorPagination[Any]] = []
    cursor: Optional[str] = None
    while True:
        cursor_filter = CursorFilter(keys, limit, cursor, **kwargs)
        rows = db.execute(cursor_filter.append_to_statement(select(model), model)).scalars().all()
        page = cursor_filter.build_page(rows)
        pages.append(page)
        if not page.has_next:
            return pages
        assert page.next_cursor is not None
        cursor = page.next_cursor


def walk_backward(db: Session, model: Any, keys: Any, limit: int, start: str, **kwargs: Any) -> list[Any]:
    collected: list[list[Any]] = []
    cursor: Optional[str] = start
    while cursor is not None:
        cursor_filter = CursorFilter(keys, limit, cursor, **kwargs)
        rows = db.execute(cursor_filter.append_to_statement(select(model), model)).scalars().all()
        page = cursor_filter.build_page(rows)
        collected.insert(0, list(page.items))
        cursor = page.previous_cursor
        assert page.has_previous is (cursor is not None)
    return [item for items in collected for item in items]


def flatten(pages: Sequence[CursorPagination[Any]]) -> list[Any]:
    return [item for page in pages for item in page.items]


def compiled(statement: Any, dialect: Any = None) -> str:
    return str(statement.compile(dialect=dialect or sqlite.dialect()))


@pytest.mark.parametrize(
    ("keys", "spec"),
    [
        ([], [("id", "asc", None)]),
        ("name", [("name", "asc", None), ("id", "asc", None)]),
        ([("score", "desc")], [("score", "desc", None), ("id", "desc", None)]),
        (["score", ("name", "desc")], [("score", "asc", None), ("name", "desc", None), ("id", "desc", None)]),
        ([("created_at", "desc")], [("created_at", "desc", None), ("id", "desc", None)]),
        ([CursorKey("rank")], [("rank", "asc", "last"), ("id", "asc", None)]),
        ([CursorKey("rank", "desc", "first")], [("rank", "desc", "first"), ("id", "desc", None)]),
        (
            [CursorKey("rank", "asc", "first"), "name"],
            [("rank", "asc", "first"), ("name", "asc", None), ("id", "asc", None)],
        ),
        ([CursorKey("rank", "desc", "last")], [("rank", "desc", "last"), ("id", "desc", None)]),
        ([("color", "desc")], [("color", "desc", None), ("id", "desc", None)]),
    ],
)
def test_forward_and_backward_walks_visit_every_row_once_in_order(
    session: Session, keys: Any, spec: list[tuple[str, str, Optional[str]]]
) -> None:
    every_row = session.execute(select(Item)).scalars().all()
    if spec[0][0] == "color":
        expected = sorted(
            every_row,
            key=functools.cmp_to_key(lambda a, b: -(_compare(a.color.name, b.color.name) or _compare(a.id, b.id))),
        )
    else:
        expected = expected_order(every_row, spec)

    pages = walk_forward(session, Item, keys, 7)

    assert flatten(pages) == expected
    assert all(len(page.items) == 7 for page in pages[:-1])
    assert pages[-1].next_cursor is None
    assert pages[0].previous_cursor is None
    assert pages[0].has_previous is False
    assert all(page.has_previous for page in pages[1:])
    assert pages[-1].previous_cursor is not None
    assert walk_backward(session, Item, keys, 7, pages[-1].previous_cursor) + list(pages[-1].items) == expected


def test_page_sizes_and_end_of_data_signal(session: Session) -> None:
    pages = walk_forward(session, Item, [("created_at", "desc")], 20)

    assert [len(page.items) for page in pages] == [20, 20, 15]
    assert [page.has_next for page in pages] == [True, True, False]
    assert [page.limit for page in pages] == [20, 20, 20]


def test_ties_on_the_sort_key_are_broken_by_primary_key(session: Session) -> None:
    tied = session.execute(select(Item).where(Item.created_at == BASE_TIME)).scalars().all()
    assert len(tied) == 30

    pages = walk_forward(session, Item, "created_at", 4)
    seen = [item.id for item in flatten(pages)]

    assert len(seen) == len(set(seen)) == 55
    assert seen[:30] == sorted(item.id for item in tied)


def test_rows_inserted_before_the_cursor_do_not_shift_later_pages(session: Session) -> None:
    first = CursorFilter("id", 10)
    page = first.build_page(session.execute(first.append_to_statement(select(Item), Item)).scalars().all())
    session.add(Item(id=0, name="early", score=0, created_at=BASE_TIME, color=Color.RED))
    session.flush()
    try:
        second = CursorFilter("id", 10, page.next_cursor)
        rows = session.execute(second.append_to_statement(select(Item), Item)).scalars().all()
        assert [row.id for row in second.build_page(rows).items] == list(range(11, 21))
    finally:
        session.rollback()


def test_composite_primary_key_tiebreaker(session: Session) -> None:
    every_row = session.execute(select(CompositeItem)).scalars().all()
    expected = expected_order(every_row, [("label", "desc", None), ("tenant", "desc", None), ("seq", "desc", None)])

    pages = walk_forward(session, CompositeItem, [("label", "desc")], 5)

    assert flatten(pages) == expected
    assert (
        walk_backward(session, CompositeItem, [("label", "desc")], 5, pages[-1].previous_cursor or "")
        + list(pages[-1].items)
        == expected
    )


def test_attribute_keys_that_differ_from_column_names(session: Session) -> None:
    every_row = session.execute(select(Renamed)).scalars().all()
    expected = expected_order(every_row, [("amount", "asc", None), ("ident", "asc", None)])

    assert flatten(walk_forward(session, Renamed, [Renamed.amount], 4)) == expected


def test_signed_ttl_and_encrypted_walks(session: Session) -> None:
    every_row = session.execute(select(Item)).scalars().all()
    expected = expected_order(every_row, [("score", "asc", None), ("id", "asc", None)])

    for kwargs in ({"secret": "s3cret"}, {"secret": b"k", "ttl": 60}, {"secret": "k", "encrypted": True}):
        assert flatten(walk_forward(session, Item, "score", 9, **kwargs)) == expected


def test_first_page_replaces_existing_ordering_limit_and_offset() -> None:
    statement = select(Item).order_by(Item.name.desc()).limit(3).offset(9)

    paginated = CursorFilter([("score", "desc")], 5).append_to_statement(statement, Item)
    sql = compiled(paginated, PG_DIALECT)

    assert "ORDER BY cursor_item.score DESC, cursor_item.id DESC" in sql
    assert "cursor_item.name DESC" not in sql
    assert "OFFSET" not in sql
    assert "WHERE" not in sql
    assert list(paginated.compile(dialect=PG_DIALECT).params.values()) == [6]


def test_keyset_predicate_uses_nested_form_with_bound_values(session: Session) -> None:
    rows = session.execute(select(Item).order_by(Item.score.desc(), Item.id.desc()).limit(3)).scalars().all()
    token = CursorFilter([("score", "desc")], 2).build_page(rows, model=Item).next_cursor

    statement = CursorFilter([("score", "desc")], 2, token).append_to_statement(select(Item), Item)
    sql = compiled(statement)
    params = statement.compile(dialect=sqlite.dialect()).params

    assert "cursor_item.score <= ? AND (cursor_item.score < ? OR cursor_item.id < ?)" in sql
    assert rows[1].id in params.values()
    assert str(rows[1].id) not in sql.replace("?", "")


def test_nulls_placement_renders_natively_on_postgresql() -> None:
    sql = compiled(
        CursorFilter([CursorKey("rank", "desc", "last")], 5).append_to_statement(select(Item), Item),
        PG_DIALECT,
    )

    assert "cursor_item.rank DESC NULLS LAST, cursor_item.id DESC" in sql


def test_nullable_key_defaults_to_nulls_last() -> None:
    sql = compiled(CursorFilter("rank", 5).append_to_statement(select(Item), Item), PG_DIALECT)

    assert "cursor_item.rank ASC NULLS LAST" in sql


def test_order_by_filter_shares_null_placement_rendering() -> None:
    order_sql = compiled(OrderByFilter("rank", "desc", "last").append_to_statement(select(Item), Item), PG_DIALECT)

    assert "cursor_item.rank DESC NULLS LAST" in order_sql


def test_empty_page_has_no_tokens() -> None:
    page = CursorFilter("name", 5).build_page([], model=Item)

    assert page == CursorPagination(
        items=[], limit=5, next_cursor=None, previous_cursor=None, has_next=False, has_previous=False
    )


def test_build_page_accepts_mapping_rows(session: Session) -> None:
    cursor_filter = CursorFilter("score", 3)
    statement = cursor_filter.append_to_statement(select(Item.id, Item.score, Item.name), Item)
    rows = session.execute(statement).mappings().all()

    page = cursor_filter.build_page(rows)
    tuples = cursor_filter.build_page(session.execute(statement).all())
    dicts = cursor_filter.build_page([dict(row) for row in rows])

    assert page.next_cursor == tuples.next_cursor == dicts.next_cursor is not None


def test_non_select_statements_are_unchanged() -> None:
    statement = delete(Item)

    result = CursorFilter("name", 5).append_to_statement(statement, Item)

    assert isinstance(result, Delete)
    assert result is statement


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [
        (("", 5), {}),
        (("owner.id", 5), {}),
        ((["name", "name"], 5), {}),
        (([CursorKey("name"), ("name", "desc")], 5), {}),
        (([42], 5), {}),
        (("name", 0), {}),
        (("name", True), {}),
        (("name", 5), {"secret": ""}),
        (("name", 5), {"encrypted": True}),
        (("name", 5), {"ttl": -1}),
    ],
)
def test_invalid_configuration_raises_value_error(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        CursorFilter(*args, **kwargs)


def test_cursor_key_rejects_bad_direction_and_nulls() -> None:
    with pytest.raises(ValueError, match="sort_order"):
        CursorKey("name", "sideways")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nulls"):
        CursorKey("name", "asc", "middle")  # type: ignore[arg-type]


def test_token_from_another_ordering_is_rejected_at_construction(session: Session) -> None:
    pages = walk_forward(session, Item, "name", 30)

    with pytest.raises(InvalidCursorError, match="ordering mismatch"):
        CursorFilter("score", 30, pages[0].next_cursor)
    with pytest.raises(InvalidCursorError, match="ordering mismatch"):
        CursorFilter([("name", "desc")], 30, pages[0].next_cursor)


def test_token_with_wrong_value_count_is_rejected_at_bind(session: Session) -> None:
    token = walk_forward(session, Item, [], 30)[0].next_cursor

    cursor_filter = CursorFilter([], 30, token)

    with pytest.raises(InvalidCursorError, match="ordering mismatch"):
        cursor_filter.append_to_statement(select(CompositeItem), CompositeItem)


def _forged_token(keys: Any, values: list[list[Any]]) -> str:
    names = [key.name for key in normalize_cursor_keys(keys)]
    fingerprint = order_fingerprint([(key.name, key.sort_order, key.nulls) for key in normalize_cursor_keys(keys)])
    assert names
    payload = {"v": 1, "d": "f", "o": fingerprint, "k": values}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    ("keys", "values"),
    [
        ("score", [["s", "not-a-number"], ["i", 1]]),
        ("score", [["b", True], ["i", 1]]),
        ("score", [["b", False], ["i", 1]]),
        ("score", [["n", None], ["i", 1]]),
        ("color", [["e", "PURPLE"], ["i", 1]]),
        ("name", [["e", "RED"], ["i", 1]]),
        ("score", [["i", 2**100], ["i", 1]]),
        ("score", [["i", 1], ["i", -(2**70)]]),
    ],
)
def test_values_that_do_not_fit_the_columns_are_rejected(keys: Any, values: list[list[Any]]) -> None:
    cursor_filter = CursorFilter(keys, 5, _forged_token(keys, values))

    with pytest.raises(InvalidCursorError):
        cursor_filter.append_to_statement(select(Item), Item)


@pytest.mark.parametrize("column", ["id", "ratio", "price"])
@pytest.mark.parametrize("flag", [True, False])
def test_boolean_cursor_values_are_rejected_for_numeric_columns(column: str, flag: bool) -> None:
    keys = [column]
    values = [["b", flag]] if column == "id" else [["b", flag], ["i", 1]]
    cursor_filter = CursorFilter(keys, 5, _forged_token(keys, values))

    with pytest.raises(InvalidCursorError, match="does not match"):
        cursor_filter.append_to_statement(select(TypedColumns), TypedColumns)


@pytest.mark.parametrize(
    ("keys", "spec"),
    [
        ("active", [("active", "asc", None), ("id", "asc", None)]),
        ([("active", "desc")], [("active", "desc", None), ("id", "desc", None)]),
        ([CursorKey("optional_active", "asc", "last")], [("optional_active", "asc", "last"), ("id", "asc", None)]),
        ([CursorKey("optional_active", "desc", "first")], [("optional_active", "desc", "first"), ("id", "desc", None)]),
    ],
)
def test_boolean_columns_walk_forward_and_backward(
    session: Session, keys: Any, spec: list[tuple[str, str, Optional[str]]]
) -> None:
    every_row = session.execute(select(TypedColumns)).scalars().all()
    expected = expected_order(every_row, spec)

    pages = walk_forward(session, TypedColumns, keys, 3)

    assert flatten(pages) == expected
    assert pages[-1].previous_cursor is not None
    assert walk_backward(session, TypedColumns, keys, 3, pages[-1].previous_cursor) + list(pages[-1].items) == expected


@pytest.mark.parametrize(
    "dialect_module",
    [sqlite, postgresql, mysql, mssql, oracle],
    ids=["sqlite", "postgresql", "mysql", "mssql", "oracle"],
)
@pytest.mark.parametrize("flag", [True, False])
def test_boolean_cursor_values_compare_by_equality_on_every_dialect(dialect_module: Any, flag: bool) -> None:
    cursor_filter = CursorFilter("active", 5, _forged_token("active", [["b", flag], ["i", 1]]))

    statement = cursor_filter.append_to_statement(select(TypedColumns), TypedColumns)
    sql = compiled(statement, dialect_module.dialect())

    assert "active = " in sql
    assert re.search(r"\bIS (?!NULL|NOT NULL)", sql) is None


@pytest.mark.parametrize(("model", "key"), [(Item, "color"), (Job, "level")])
def test_in_memory_enum_order_matches_sql(session: Session, model: Any, key: str) -> None:
    rows = session.execute(select(model)).scalars().all()
    cursor_filter = CursorFilter(key, len(rows))
    expected = session.execute(cursor_filter.append_to_statement(select(model), model)).scalars().all()

    assert CursorFilter(key, len(rows)).paginate_items(rows, model) == list(expected)


@pytest.mark.parametrize("key", ["owner", "missing"])
def test_keys_that_are_not_column_attributes_are_rejected(key: str) -> None:
    with pytest.raises(ImproperConfigurationError, match="not a column attribute"):
        CursorFilter(key, 5).append_to_statement(select(Item), Item)


def test_token_with_an_unhashable_direction_is_rejected() -> None:
    payload = {"v": 1, "d": [], "o": order_fingerprint([("name", "asc", None)]), "k": []}
    token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    with pytest.raises(InvalidCursorError, match="malformed"):
        CursorFilter("name", 5, token)


def test_build_page_infers_the_model_from_mapped_rows(session: Session) -> None:
    rows = list(session.scalars(select(Item).order_by(Item.score, Item.id).limit(4)))

    page = CursorFilter("score", 3).build_page(rows)

    assert (len(page.items), page.has_next, page.next_cursor is not None) == (3, True, True)
    assert CursorFilter("score", 3).build_page([]).items == []


def test_build_page_needs_a_model_for_unmapped_rows() -> None:
    with pytest.raises(ImproperConfigurationError, match="needs the model"):
        CursorFilter("name", 5).build_page([{"name": "a", "id": 1}])


def test_enum_type_decorator_keys_page_past_the_first_page(session: Session) -> None:
    pages = walk_forward(session, Job, "level", 2)

    assert sorted(job.id for job in flatten(pages)) == list(range(1, 10))


def test_enum_key_without_a_known_enum_class_fails_when_tokens_are_issued(session: Session) -> None:
    cursor_filter = CursorFilter("untyped_level", 2)
    rows = list(session.scalars(cursor_filter.append_to_statement(select(Job), Job)))

    with pytest.raises(ImproperConfigurationError, match="python_type"):
        cursor_filter.build_page(rows)


def test_nullable_expression_keys_page_past_null_rows(session: Session) -> None:
    pages = walk_forward(session, Job, "half", 2)

    assert sorted(job.id for job in flatten(pages)) == list(range(1, 10))


def test_build_page_rejects_rows_missing_a_key(session: Session) -> None:
    rows = session.execute(select(Item.id, Item.name).limit(3)).mappings().all()

    with pytest.raises(ImproperConfigurationError, match="no cursor key 'score'"):
        CursorFilter("score", 2).build_page(rows, model=Item)


def test_equality_pickling_and_repr_never_expose_the_secret(session: Session) -> None:
    token = walk_forward(session, Item, "name", 30, secret="hidden-secret", ttl=60)[0].next_cursor
    cursor_filter = CursorFilter("name", 30, token, "hidden-secret", ttl=60)

    restored = pickle.loads(pickle.dumps(cursor_filter))

    assert restored == cursor_filter
    assert hash(restored) == hash(cursor_filter)
    assert restored.cursor == token
    assert restored.backward is False
    assert restored.ttl == 60
    assert "hidden-secret" not in repr(cursor_filter)
    assert cursor_filter != CursorFilter("name", 30, token, "hidden-secret")


def test_cursor_keys_compare_by_name_direction_and_nulls() -> None:
    assert CursorKey(Item.name) == CursorKey("name")
    assert CursorKey(Item.name) != CursorKey(Item.score)
    assert len({CursorKey(Item.name), CursorKey("name"), CursorKey("name", "desc")}) == 2
    assert CursorFilter([Item.name], 5) == CursorFilter("name", 5)


def test_null_placement_is_dropped_for_non_nullable_columns() -> None:
    sql = compiled(
        CursorFilter([CursorKey("score", "desc", "first")], 5).append_to_statement(select(Item), Item), sqlite.dialect()
    )

    assert "ORDER BY cursor_item.score DESC, cursor_item.id DESC" in sql
    assert "CASE" not in sql


def test_key_resolution_is_shared_across_filter_instances() -> None:
    first = CursorFilter([("score", "desc")], 5)._resolve(Item)
    second = CursorFilter([("score", "desc")], 9)._resolve(Item)

    assert first is second


def test_cursor_filter_is_a_dataclass_without_the_secret() -> None:
    import dataclasses

    cursor_filter = CursorFilter([("score", "desc")], 5, secret="hidden-secret", ttl=30)

    assert dataclasses.asdict(cursor_filter) == {
        "keys": ({"field_name": "score", "sort_order": "desc", "nulls": None},),
        "limit": 5,
        "cursor": None,
        "ttl": 30,
        "encrypted": False,
    }


@pytest.mark.parametrize(
    ("keys", "expected_duplicates"),
    [
        (["name", "name"], "name"),
        (["name", "name", "id", "name"], "name"),
        (["score", "name", "score", "name"], "score, name"),
    ],
)
def test_normalize_cursor_keys_deduplicates_duplicate_names_in_error(keys: list[str], expected_duplicates: str) -> None:
    with pytest.raises(ValueError, match=f"duplicate keys: {expected_duplicates}$"):
        normalize_cursor_keys(keys)


def test_cursor_filter_encrypted_requires_cryptography(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("advanced_alchemy.filters._pagination.CRYPTOGRAPHY_INSTALLED", False)

    with pytest.raises(MissingDependencyError, match="cryptography"):
        CursorFilter("score", 5, secret="k", encrypted=True)

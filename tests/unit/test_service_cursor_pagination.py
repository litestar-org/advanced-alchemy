"""to_schema cursor pagination: typed overloads, schema conversion, and pagination mismatches."""

from collections.abc import Iterator, Sequence
from typing import Any, Optional

import msgspec
import pytest
from attrs import define
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from typing_extensions import assert_type

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import CursorFilter, FilterSet, LimitOffsetFilter, StatementFilter
from advanced_alchemy.service import (
    CursorPagination,
    OffsetPagination,
    ResultConverter,
    SQLAlchemySyncRepositoryService,
)


class ConvertBase(DeclarativeBase):
    pass


class Note(ConvertBase):
    __tablename__ = "cursor_convert_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str]
    priority: Mapped[int]


class NoteStruct(msgspec.Struct):
    id: int
    body: str


VALIDATED: list[int] = []


class NoteModel(BaseModel):
    id: int
    body: str

    @field_validator("id")
    @classmethod
    def record(cls, value: int) -> int:
        VALIDATED.append(value)
        return value


@define
class NoteAttrs:
    id: int
    body: str


class NoteService(SQLAlchemySyncRepositoryService[Note]):
    pass


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    ConvertBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(Note(id=i, body=f"note {i}", priority=i % 3) for i in range(1, 12))
        db.commit()
        yield db
    engine.dispose()


def first_page(session: Session, limit: int = 4) -> tuple[list[Note], CursorFilter]:
    cursor_filter = CursorFilter([("priority", "desc")], limit)
    rows = list(session.execute(cursor_filter.append_to_statement(select(Note), Note)).scalars())
    return rows, cursor_filter


def test_existing_call_forms_still_narrow_to_offset_pagination(session: Session) -> None:
    converter = ResultConverter()
    rows = list(session.execute(select(Note)).scalars())
    filters: Sequence[StatementFilter] = [LimitOffsetFilter(5, 0)]

    assert_type(converter.to_schema(rows), OffsetPagination[Note])
    assert_type(converter.to_schema(rows, 11, filters=filters), OffsetPagination[Note])
    assert_type(converter.to_schema(rows, schema_type=NoteStruct), OffsetPagination[NoteStruct])
    assert_type(converter.to_schema(rows, 11, filters=filters, schema_type=NoteStruct), OffsetPagination[NoteStruct])
    assert_type(converter.to_schema(rows[0], schema_type=NoteStruct), NoteStruct)
    assert_type(
        converter.to_schema(rows, 11, filters=filters, schema_type=NoteStruct, pagination_type="limit_offset"),
        OffsetPagination[NoteStruct],
    )


def test_cursor_call_forms_narrow_to_cursor_pagination(session: Session) -> None:
    converter = ResultConverter()
    rows, cursor_filter = first_page(session)

    models = converter.to_schema(rows, filters=[cursor_filter], pagination_type="cursor")
    structs = converter.to_schema(rows, filters=[cursor_filter], schema_type=NoteStruct, pagination_type="cursor")

    assert_type(models, CursorPagination[Note])
    assert_type(structs, CursorPagination[NoteStruct])
    assert [note.id for note in models.items] == [s.id for s in structs.items]


def returns_offset(converter: ResultConverter, rows: list[Note]) -> OffsetPagination[NoteStruct]:
    return converter.to_schema(rows, len(rows), schema_type=NoteStruct)


def returns_cursor(converter: ResultConverter, rows: list[Note], f: CursorFilter) -> CursorPagination[NoteStruct]:
    return converter.to_schema(rows, filters=[f], schema_type=NoteStruct, pagination_type="cursor")


@pytest.mark.parametrize("schema_type", [None, NoteStruct, NoteModel, NoteAttrs])
def test_cursor_page_converts_only_the_trimmed_items(session: Session, schema_type: Optional[type[Any]]) -> None:
    rows, cursor_filter = first_page(session)
    VALIDATED.clear()

    page = ResultConverter().to_schema(rows, filters=[cursor_filter], schema_type=schema_type, pagination_type="cursor")

    assert len(rows) == 5
    assert len(page.items) == 4
    assert page.limit == 4
    assert page.has_next is True
    assert page.has_previous is False
    assert page.next_cursor is not None
    assert page.previous_cursor is None
    if schema_type is None:
        assert page.items == rows[:4]
    else:
        assert all(isinstance(item, schema_type) for item in page.items)
        assert [item.id for item in page.items] == [row.id for row in rows[:4]]
    if schema_type is NoteModel:
        assert len(VALIDATED) == 4


def test_service_walk_uses_the_service_model(session: Session) -> None:
    service = NoteService(session=session)
    seen: list[int] = []
    cursor: Optional[str] = None
    while True:
        cursor_filter = CursorFilter([("priority", "desc")], 3, cursor)
        rows = service.get_many(cursor_filter)
        page = service.to_schema(rows, filters=[cursor_filter], schema_type=NoteStruct, pagination_type="cursor")
        seen.extend(item.id for item in page.items)
        if not page.has_next:
            break
        cursor = page.next_cursor

    assert seen == [n.id for n in sorted(service.get_many(), key=lambda n: (-n.priority, -n.id))]


def test_total_is_ignored_for_cursor_pages(session: Session) -> None:
    rows, cursor_filter = first_page(session)

    page = NoteService(session=session).to_schema(rows, 999, filters=[cursor_filter], pagination_type="cursor")

    assert isinstance(page, CursorPagination)


def test_empty_cursor_page(session: Session) -> None:
    _, cursor_filter = first_page(session)

    page: CursorPagination[Note] = NoteService(session=session).to_schema(
        [], filters=[cursor_filter], pagination_type="cursor"
    )

    assert (page.items, page.has_next, page.has_previous, page.next_cursor) == ([], False, False, None)


def test_cursor_filter_is_detected_without_pagination_type(session: Session) -> None:
    rows, cursor_filter = first_page(session)
    service = NoteService(session=session)

    detected: Any = service.to_schema(rows, filters=[cursor_filter], schema_type=NoteStruct)
    explicit = service.to_schema(rows, filters=[cursor_filter], schema_type=NoteStruct, pagination_type="cursor")

    assert isinstance(detected, CursorPagination)
    assert detected == explicit
    assert len(detected.items) == cursor_filter.limit


def test_cursor_filter_inside_filterset_is_detected(session: Session) -> None:
    class NoteFilters(FilterSet[Note]):
        config = {"pagination_type": "cursor", "pagination_size": 2, "sort_field": "priority"}

    filterset = NoteFilters()
    service = NoteService(session=session)
    rows = service.get_many(filterset)

    detected: Any = service.to_schema(rows, filters=[filterset], schema_type=NoteStruct)
    explicit = service.to_schema(rows, filters=[filterset], schema_type=NoteStruct, pagination_type="cursor")

    assert isinstance(detected, CursorPagination)
    assert detected == explicit
    assert (len(detected.items), detected.has_next) == (2, True)


def test_limit_offset_filter_inside_filterset_sets_offset(session: Session) -> None:
    class NoteFilters(FilterSet[Note]):
        config = {"pagination_type": "limit_offset", "pagination_size": 2}

    filterset = NoteFilters(page=2)
    service = NoteService(session=session)
    rows, total = service.get_many_and_count(filterset)

    page = service.to_schema(rows, total, filters=[filterset])

    assert (page.limit, page.offset) == (2, 2)


def test_cursor_filter_with_limit_offset_pagination_type_is_rejected(session: Session) -> None:
    rows, cursor_filter = first_page(session)

    with pytest.raises(ImproperConfigurationError, match="contain a CursorFilter"):
        NoteService(session=session).to_schema(rows, filters=[cursor_filter], pagination_type="limit_offset")


def test_cursor_pagination_type_without_cursor_filter_is_rejected(session: Session) -> None:
    rows, _ = first_page(session)

    with pytest.raises(ImproperConfigurationError, match="requires a CursorFilter"):
        NoteService(session=session).to_schema(rows, filters=[LimitOffsetFilter(4, 0)], pagination_type="cursor")


def test_cursor_pagination_type_with_single_object_is_rejected(session: Session) -> None:
    rows, cursor_filter = first_page(session)

    with pytest.raises(ImproperConfigurationError, match="sequence of rows"):
        NoteService(session=session).to_schema(rows[0], filters=[cursor_filter], pagination_type="cursor")  # type: ignore[call-overload]


def test_single_object_conversion_ignores_cursor_filters(session: Session) -> None:
    rows, cursor_filter = first_page(session)

    converted = NoteService(session=session).to_schema(rows[0], filters=[cursor_filter], schema_type=NoteStruct)

    assert converted == NoteStruct(id=rows[0].id, body=rows[0].body)

"""Search filters preserve existing SQL unless literal escaping is requested."""

from typing import Any

import pytest
from google.cloud.sqlalchemy_spanner.sqlalchemy_spanner import SpannerDialect
from sqlalchemy import String, select
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.filters import NotInSearchFilter, SearchFilter

pytestmark = pytest.mark.unit


class Base(DeclarativeBase):
    pass


class Movie(Base):
    __tablename__ = "search_filter_movie"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))


@pytest.mark.parametrize(
    "dialect",
    [
        sqlite.dialect(),  # type: ignore[no-untyped-call]
        postgresql.dialect(),  # type: ignore[no-untyped-call]
        mysql.dialect(),  # type: ignore[no-untyped-call]
        oracle.dialect(),  # type: ignore[no-untyped-call]
        mssql.dialect(),  # type: ignore[no-untyped-call]
        SpannerDialect(),
    ],
)
@pytest.mark.parametrize(
    ("filter_type", "ignore_case", "operator"),
    [
        (SearchFilter, False, "like"),
        (SearchFilter, True, "ilike"),
        (NotInSearchFilter, False, "not_like"),
        (NotInSearchFilter, True, "not_ilike"),
    ],
)
@pytest.mark.parametrize("value", ["plain", "50%_/"])
def test_search_filter_preserves_default_sql(
    dialect: Any, filter_type: type[SearchFilter], ignore_case: bool, operator: str, value: str
) -> None:
    expected = select(Movie).where(getattr(Movie.title, operator)(f"%{value}%")).compile(dialect=dialect)
    for search_filter in (
        filter_type("title", value, ignore_case=ignore_case),
        filter_type("title", value, ignore_case=ignore_case, escape_wildcards=False),
    ):
        compiled = search_filter.append_to_statement(select(Movie), Movie).compile(dialect=dialect)
        assert str(compiled) == str(expected)
        assert compiled.params == expected.params

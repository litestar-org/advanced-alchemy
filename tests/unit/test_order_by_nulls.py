"""NULL placement in :class:`OrderBy` compiles per dialect.

The integration suite cannot cover this: ``tests/integration/test_filters.py`` skips on SQL Server,
and MySQL is only reachable through the async engines. Both are exactly the backends that reject
``NULLS FIRST``/``NULLS LAST``, so the emulation is pinned here instead.
"""

from collections.abc import Generator
from typing import Any, Literal

import pytest
from sqlalchemy import ForeignKey, String, create_engine, select
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, joinedload, mapped_column, relationship

from advanced_alchemy.filters import OrderBy

pytestmark = pytest.mark.unit


class Base(DeclarativeBase):
    pass


class Movie(Base):
    __tablename__ = "order_by_nulls_movie"

    id: Mapped[int] = mapped_column(primary_key=True)
    director: Mapped[str] = mapped_column(String(length=50), nullable=True)
    credits: Mapped[list["Credit"]] = relationship()


class Credit(Base):
    __tablename__ = "order_by_nulls_credit"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey(Movie.id))


@pytest.fixture
def movie_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                Movie(id=index, director=director, credits=[Credit(), Credit()])
                for index, director in enumerate((None, "z", "a"), start=1)
            )
            session.commit()
            yield session
    finally:
        engine.dispose()


NATIVE_DIALECTS = [
    postgresql.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
    sqlite.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
    oracle.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
]
EMULATED_DIALECTS = [
    mysql.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
    mssql.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
]

NATIVE = pytest.mark.parametrize("dialect", NATIVE_DIALECTS)
EMULATED = pytest.mark.parametrize("dialect", EMULATED_DIALECTS)


def _compiled(dialect: Any, **kwargs: Any) -> str:
    statement = OrderBy(field_name="director", **kwargs).append_to_statement(select(Movie), Movie)
    return str(statement.compile(dialect=dialect))


@NATIVE
@pytest.mark.parametrize(("nulls", "clause"), [("first", "NULLS FIRST"), ("last", "NULLS LAST")])
def test_dialects_with_the_syntax_get_the_native_clause(dialect: Any, nulls: str, clause: str) -> None:
    """Keeping the native clause is what lets an index on the column still satisfy the ordering."""
    assert clause in _compiled(dialect, sort_order="desc", nulls=nulls)


@EMULATED
@pytest.mark.parametrize("nulls", ["first", "last"])
def test_dialects_without_the_syntax_get_a_nullity_key(dialect: Any, nulls: str) -> None:
    """MySQL and SQL Server reject `NULLS FIRST`/`NULLS LAST` outright, so it must not be emitted."""
    compiled = _compiled(dialect, sort_order="desc", nulls=nulls)

    assert "NULLS" not in compiled
    assert "CASE WHEN" in compiled
    assert compiled.rstrip().endswith("DESC")


@EMULATED
@pytest.mark.parametrize(("nulls", "when_null"), [("last", "THEN 1 ELSE 0"), ("first", "THEN 0 ELSE 1")])
def test_the_nullity_key_sorts_the_right_way(dialect: Any, nulls: str, when_null: str) -> None:
    """The key ascends, so NULLs need the higher value to land last and the lower one to land first."""
    assert when_null in _compiled(dialect, sort_order="desc", nulls=nulls)


@pytest.mark.parametrize("dialect", NATIVE_DIALECTS + EMULATED_DIALECTS)
def test_the_default_is_untouched(dialect: Any) -> None:
    """Without `nulls` the emitted SQL must be exactly what it was before the option existed."""
    compiled = _compiled(dialect, sort_order="desc")

    assert "NULLS" not in compiled
    assert "CASE" not in compiled


@pytest.mark.parametrize("sort_order", ["asc", "desc"])
@pytest.mark.parametrize("nulls", ["first", "last"])
def test_nulls_placement_with_paginated_eager_loading(
    movie_session: Session, sort_order: Literal["asc", "desc"], nulls: Literal["first", "last"]
) -> None:
    statement = OrderBy("director", sort_order, nulls).append_to_statement(
        select(Movie).options(joinedload(Movie.credits)).limit(2).offset(1), Movie
    )
    movies = movie_session.scalars(statement).unique().all()

    expected = [3, 2] if sort_order == "asc" else [2, 3]
    expected = [1, *expected] if nulls == "first" else [*expected, 1]
    assert [movie.id for movie in movies] == expected[1:]
    assert all(len(movie.credits) == 2 for movie in movies)


@EMULATED
def test_emulated_eager_loading_adapts_the_ordering_column(dialect: Any) -> None:
    statement = OrderBy("director", nulls="last").append_to_statement(
        select(Movie).options(joinedload(Movie.credits)).limit(2), Movie
    )
    compiled = str(statement.compile(dialect=dialect))

    assert "ASC AS" not in compiled
    assert compiled.endswith("ORDER BY CASE WHEN (anon_1.director IS NULL) THEN 1 ELSE 0 END, anon_1.director ASC")


def test_nulls_placement_reuses_distinct_compiled_statements(movie_session: Session) -> None:
    cache: dict[Any, Any] = {}
    for _ in range(2):
        for field in ("director", "id"):
            for sort_order in ("asc", "desc"):
                for nulls in ("first", "last"):
                    statement = OrderBy(field, sort_order, nulls).append_to_statement(select(Movie.id), Movie)
                    result = movie_session.scalars(statement, execution_options={"compiled_cache": cache}).all()
                    if field == "id":
                        expected = [1, 2, 3] if sort_order == "asc" else [3, 2, 1]
                    else:
                        expected = [3, 2] if sort_order == "asc" else [2, 3]
                        expected = [1, *expected] if nulls == "first" else [*expected, 1]
                    assert result == expected
        assert len(cache) == 8

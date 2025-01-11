from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    ExistsFilter,
    LimitOffset,
    NotExistsFilter,
    NotInCollectionFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
)


class Movie(BigIntBase):
    __tablename__ = "movies"

    title: Mapped[str] = mapped_column(String(length=100))
    release_date: Mapped[datetime] = mapped_column()
    genre: Mapped[str] = mapped_column(String(length=50))


@pytest.fixture()
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path}/test_filters.sqlite", echo=True)
    Movie.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    # Add test data
    movie1 = Movie(title="The Matrix", release_date=datetime(1999, 3, 31, tzinfo=timezone.utc), genre="Action")
    movie2 = Movie(title="The Hangover", release_date=datetime(2009, 6, 1, tzinfo=timezone.utc), genre="Comedy")
    movie3 = Movie(
        title="Shawshank Redemption", release_date=datetime(1994, 10, 14, tzinfo=timezone.utc), genre="Drama"
    )
    session.add_all([movie1, movie2, movie3])
    session.commit()
    yield session
    session.close()
    engine.dispose()
    Path(tmp_path / "test_filters.sqlite").unlink(missing_ok=True)


def test_before_after_filter(db_session: Session) -> None:
    before_after_filter = BeforeAfter(
        field_name="release_date", before=datetime(1999, 3, 31, tzinfo=timezone.utc), after=None
    )
    statement = before_after_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1


def test_on_before_after_filter(db_session: Session) -> None:
    on_before_after_filter = OnBeforeAfter(
        field_name="release_date", on_or_before=None, on_or_after=datetime(1999, 3, 31, tzinfo=timezone.utc)
    )
    statement = on_before_after_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2


def test_collection_filter(db_session: Session) -> None:
    collection_filter = CollectionFilter(field_name="title", values=["The Matrix", "Shawshank Redemption"])
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2


def test_not_in_collection_filter(db_session: Session) -> None:
    not_in_collection_filter = NotInCollectionFilter(field_name="title", values=["The Hangover"])
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2


def test_exists_filter_basic(db_session: Session) -> None:
    exists_filter_1 = ExistsFilter(values=[Movie.genre == "Action"])
    statement = exists_filter_1.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1

    exists_filter_2 = ExistsFilter(values=[Movie.genre.startswith("Action"), Movie.genre.startswith("Drama")])
    statement = exists_filter_2.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2


def test_exists_filter(db_session: Session) -> None:
    exists_filter_1 = ExistsFilter(values=[Movie.title.startswith("The")])
    statement = exists_filter_1.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 3

    exists_filter_2 = ExistsFilter(
        values=[Movie.title.startswith("Shawshank Redemption"), Movie.title.startswith("The")],
        operator="and",
    )
    statement = exists_filter_2.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 0

    exists_filter_3 = ExistsFilter(
        values=[Movie.title.startswith("The"), Movie.title.startswith("Shawshank")],
        operator="or",
    )
    statement = exists_filter_3.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 3


def test_not_exists_filter(db_session: Session) -> None:
    not_exists_filter = NotExistsFilter(values=[Movie.title.like("%Hangover%")])
    statement = not_exists_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2


def test_limit_offset_filter(db_session: Session) -> None:
    limit_offset_filter = LimitOffset(limit=2, offset=1)
    statement = limit_offset_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2


def test_order_by_filter(db_session: Session) -> None:
    order_by_filter = OrderBy(field_name="release_date", sort_order="asc")
    statement = order_by_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert results[0].title == "Shawshank Redemption"
    order_by_filter = OrderBy(field_name="release_date", sort_order="desc")
    statement = order_by_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert results[0].title == "The Hangover"


def test_search_filter(db_session: Session) -> None:
    search_filter = SearchFilter(field_name="title", value="Hangover")
    statement = search_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1

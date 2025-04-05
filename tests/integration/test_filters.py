from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.filters import (
    AGGridFilter,
    BeforeAfter,
    CollectionFilter,
    ExistsFilter,
    FilterGroup,
    LimitOffset,
    MultiFilter,
    NotExistsFilter,
    NotInCollectionFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
    TanStackFilter,
    and_,
    or_,
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


def test_exists_filter(db_session: Session) -> None:
    # Test EXISTS with a condition that is true for at least one row
    # Should return all rows because the subquery finds a match
    exists_filter_1 = ExistsFilter(values=[Movie.genre == "Action"])
    # For correlated subquery: Should return only rows where the condition is true
    statement = exists_filter_1.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1

    # Test EXISTS with multiple conditions using AND (default) that are true for different rows
    # The combination (Action AND Drama) is never true for a single row, so subquery is empty
    exists_filter_2 = ExistsFilter(values=[Movie.genre == "Action", Movie.genre == "Drama"])
    # For correlated subquery: Should return only rows where BOTH conditions are true (none)
    statement = exists_filter_2.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 0

    # Test EXISTS with a condition that is never true
    # Should return no rows because the subquery is empty
    exists_filter_3 = ExistsFilter(values=[Movie.genre == "SciFi"])
    # For correlated subquery: Should return only rows where the condition is true (none)
    statement = exists_filter_3.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 0


def test_exists_filter_operators(db_session: Session) -> None:
    # Test EXISTS with OR operator - condition is true
    exists_filter_or = ExistsFilter(values=[Movie.genre == "Action", Movie.genre == "SciFi"], operator="or")
    # For correlated subquery: Should return rows where EITHER condition is true (only Action movie)
    statement = exists_filter_or.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1

    exists_filter_or_2 = ExistsFilter(values=[Movie.genre == "Action", Movie.genre == "Drama"], operator="or")
    # For correlated subquery: Should return rows where EITHER condition is true (only Action movie)
    statement = exists_filter_or_2.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2

    # Test EXISTS with AND operator - conditions never true simultaneously
    exists_filter_and = ExistsFilter(
        values=[Movie.title.startswith("The Matrix"), Movie.title.startswith("Shawshank")], operator="and"
    )
    # For correlated subquery: Should return rows where BOTH conditions are true (none)
    statement = exists_filter_and.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 0


def test_not_exists_filter(db_session: Session) -> None:
    # Test NOT EXISTS with a condition that is true for at least one row
    # Should return no rows because the subquery finds a match
    not_exists_filter_true = NotExistsFilter(values=[Movie.title.like("%Hangover%")])
    # For correlated subquery: Should return rows where condition is FALSE (Matrix, Shawshank)
    statement = not_exists_filter_true.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2

    # Test NOT EXISTS with a condition that is never true
    # Should return all rows because the subquery is empty
    not_exists_filter_false = NotExistsFilter(values=[Movie.title == "NonExistentMovie"])
    # For correlated subquery: Should return rows where condition is FALSE (all movies)
    statement = not_exists_filter_false.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 3


def test_not_exists_filter_operators(db_session: Session) -> None:
    # Test NOT EXISTS with OR operator - Should return rows where NEITHER condition is true
    not_exists_filter_or = NotExistsFilter(values=[Movie.genre == "Comedy", Movie.genre == "SciFi"], operator="or")
    # For correlated subquery: Should return rows where NEITHER condition is true (Action, Drama)
    statement = not_exists_filter_or.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2

    # Test NOT EXISTS with AND operator - Should return rows where NOT BOTH conditions are true
    not_exists_filter_and = NotExistsFilter(
        values=[Movie.title.startswith("The Matrix"), Movie.title.startswith("Shawshank")], operator="and"
    )
    # For correlated subquery: Should return rows where NOT BOTH conditions are true (all)
    statement = not_exists_filter_and.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 3


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


def test_filter_group_logical_operators(db_session: Session) -> None:
    # Test AND operator
    before_2000 = BeforeAfter(field_name="release_date", before=datetime(2000, 1, 1, tzinfo=timezone.utc), after=None)
    has_the_in_title = SearchFilter(field_name="title", value="The", ignore_case=True)

    # Should match only "The Matrix" (before 2000 AND has "The" in title)
    and_filter_group = FilterGroup(
        logical_operator=and_,
        filters=[before_2000, has_the_in_title],
    )

    statement = and_filter_group.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1
    assert results[0].title == "The Matrix"

    # Test OR operator
    drama_filter = SearchFilter(field_name="genre", value="Drama", ignore_case=True)

    # Should match "The Matrix", "Shawshank Redemption" (before 2000 OR is drama)
    or_filter_group = FilterGroup(
        logical_operator=or_,
        filters=[before_2000, drama_filter],
    )

    statement = or_filter_group.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_multi_filter_basic(db_session: Session) -> None:
    # Test basic MultiFilter with AND condition
    multi_filter = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "before_after",
                    "field_name": "release_date",
                    "before": datetime(2000, 1, 1, tzinfo=timezone.utc),
                    "after": None,
                },
                {"type": "search", "field_name": "title", "value": "The", "ignore_case": True},
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1
    assert results[0].title == "The Matrix"

    # Test basic MultiFilter with OR condition
    multi_filter = MultiFilter(
        filters={
            "or_": [
                {
                    "type": "before_after",
                    "field_name": "release_date",
                    "before": datetime(2000, 1, 1, tzinfo=timezone.utc),
                    "after": None,
                },
                {"type": "search", "field_name": "genre", "value": "Drama", "ignore_case": True},
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_multi_filter_nested(db_session: Session) -> None:
    # Test nested AND/OR conditions
    multi_filter = MultiFilter(
        filters={
            "or_": [
                # Match any comedy movie
                {"type": "search", "field_name": "genre", "value": "Comedy", "ignore_case": True},
                # OR match any movie from before 2000 that has "The" in title
                {
                    "and_": [
                        {
                            "type": "before_after",
                            "field_name": "release_date",
                            "before": datetime(2000, 1, 1, tzinfo=timezone.utc),
                            "after": None,
                        },
                        {"type": "search", "field_name": "title", "value": "The", "ignore_case": True},
                    ]
                },
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "The Hangover"}


def test_tanstack_filter_conversion(db_session: Session) -> None:
    # Test TanStackFilter adapter
    tanstack_filters = [
        {"field": "release_date", "operator": "lessThan", "value": datetime(2000, 1, 1, tzinfo=timezone.utc)},
        {"field": "title", "operator": "contains", "value": "The"},
        {"field": "genre", "operator": "equals", "value": "Action"},
    ]

    adapter = TanStackFilter(tanstack_filters=tanstack_filters)  # type: ignore
    multi_filter_dict = adapter.to_multifilter_format()

    # Convert to MultiFilter and apply
    multi_filter = MultiFilter(filters=multi_filter_dict)
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()

    # Should match "The Matrix" (before 2000, contains "The", and Action genre)
    assert len(results) == 1
    assert results[0].title == "The Matrix"


def test_tanstack_filter_with_nested_logic(db_session: Session) -> None:
    # Test TanStackFilter with nested logical conditions
    tanstack_filters = [
        {
            "logical": "or_",
            "filters": [
                {"field": "genre", "operator": "equals", "value": "Comedy"},
                {
                    "logical": "and_",
                    "filters": [
                        {
                            "field": "release_date",
                            "operator": "lessThan",
                            "value": datetime(2000, 1, 1, tzinfo=timezone.utc),
                        },
                        {"field": "title", "operator": "contains", "value": "The"},
                    ],
                },
            ],
        }
    ]

    adapter = TanStackFilter(tanstack_filters=tanstack_filters)
    multi_filter_dict = adapter.to_multifilter_format()

    # Convert to MultiFilter and apply
    multi_filter = MultiFilter(filters=multi_filter_dict)
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()

    # Should match "The Matrix" and "The Hangover" as in test_multi_filter_nested
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "The Hangover"}


def test_aggrid_filter_conversion(db_session: Session) -> None:
    # Test AG Grid filter adapter
    aggrid_filters = {
        "release_date": {"type": "lessThan", "filter": datetime(2000, 1, 1, tzinfo=timezone.utc)},
        "title": {"type": "contains", "filter": "The"},
        "genre": {"type": "equals", "filter": "Action"},
    }

    adapter = AGGridFilter(aggrid_filters=aggrid_filters)  # type: ignore
    multi_filter_dict = adapter.to_multifilter_format()

    # Convert to MultiFilter and apply
    multi_filter = MultiFilter(filters=multi_filter_dict)
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()

    # Should match "The Matrix" (before 2000, contains "The", and Action genre)
    assert len(results) == 1
    assert results[0].title == "The Matrix"


def test_aggrid_range_filter(db_session: Session) -> None:
    # Test AG Grid range filter
    aggrid_filters = {
        "release_date": {
            "type": "inRange",
            "filter": datetime(1994, 1, 1, tzinfo=timezone.utc),
            "filterTo": datetime(2000, 1, 1, tzinfo=timezone.utc),
        },
    }

    adapter = AGGridFilter(aggrid_filters=aggrid_filters)
    multi_filter_dict = adapter.to_multifilter_format()

    # Convert to MultiFilter and apply
    multi_filter = MultiFilter(filters=multi_filter_dict)
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()

    # Should match "The Matrix" and "Shawshank Redemption" (both in 1994-2000 range)
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_empty_filters(db_session: Session) -> None:
    # Test empty filters
    multi_filter = MultiFilter(filters={})
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()

    # Should match all movies since no filters are applied
    assert len(results) == 3

    # Test empty tanstack filter
    adapter = TanStackFilter(tanstack_filters=[])
    multi_filter_dict = adapter.to_multifilter_format()
    assert not multi_filter_dict  # Should be empty

    # Test empty aggrid filter
    adapter = AGGridFilter(aggrid_filters={})  # type: ignore
    multi_filter_dict = adapter.to_multifilter_format()
    assert not multi_filter_dict  # Should be empty

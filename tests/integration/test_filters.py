from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    ComparisonFilter,
    ExistsFilter,
    FilterGroup,
    LimitOffset,
    MultiFilter,
    NotExistsFilter,
    NotInCollectionFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
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


def test_multi_filter_empty_filters(db_session: Session) -> None:
    """Test MultiFilter with empty filter lists."""
    # Test with empty filter list
    multi_filter = MultiFilter(filters={"and_": []})
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should return all movies since no filters are applied
    assert len(results) == 3

    # Test with empty filters dict
    multi_filter = MultiFilter(filters={})
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should return all movies since no filters are applied
    assert len(results) == 3


def test_multi_filter_invalid_filter_type(db_session: Session) -> None:
    """Test MultiFilter with invalid filter types."""
    # Test with non-existent filter type
    multi_filter = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "non_existent_filter",
                    "field_name": "title",
                    "value": "The Matrix",
                }
            ]
        }
    )
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should return all movies since invalid filter is ignored
    assert len(results) == 3

    # Test with missing type field
    multi_filter = MultiFilter(
        filters={
            "and_": [
                {
                    "field_name": "title",
                    "value": "The Matrix",
                }
            ]
        }
    )
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should return all movies since invalid filter is ignored
    assert len(results) == 3


def test_multi_filter_invalid_filter_args(db_session: Session) -> None:
    """Test MultiFilter with invalid filter arguments."""
    # Test with missing required field
    multi_filter = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "search",
                    # Missing field_name
                    "value": "The Matrix",
                }
            ]
        }
    )
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should return all movies since invalid filter is ignored
    assert len(results) == 3

    multi_filter = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "search",
                    "field_name": "non_existent_field",
                    "value": "The Matrix",
                }
            ]
        }
    )
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should return all movies since invalid filter is ignored
    assert len(results) == 3


def test_multi_filter_invalid_logical_operator(db_session: Session) -> None:
    """Test MultiFilter with invalid logical operators."""
    # Test with non-existent logical operator
    multi_filter = MultiFilter(
        filters={
            "invalid_operator": [
                {
                    "type": "search",
                    "field_name": "title",
                    "value": "The Matrix",
                }
            ]
        }
    )
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should return all movies since invalid operator is ignored
    assert len(results) == 3


def test_multi_filter_complex_nested(db_session: Session) -> None:
    """Test MultiFilter with complex nested conditions."""
    multi_filter = MultiFilter(
        filters={
            "and_": [
                # First condition: Movie is from before 2000
                {
                    "type": "before_after",
                    "field_name": "release_date",
                    "before": datetime(2000, 1, 1, tzinfo=timezone.utc),
                    "after": None,
                },
                # Second condition: Nested OR group
                {
                    "or_": [
                        # Movie has "The" in title
                        {"type": "search", "field_name": "title", "value": "The", "ignore_case": True},
                        # OR movie is a drama
                        {"type": "search", "field_name": "genre", "value": "Drama", "ignore_case": True},
                    ]
                },
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should match "The Matrix" (before 2000 AND has "The" in title)
    # and "Shawshank Redemption" (before 2000 AND is a drama)
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_multi_filter_all_filter_types(db_session: Session) -> None:
    """Test MultiFilter with all supported filter types."""
    multi_filter = MultiFilter(
        filters={
            "or_": [
                # BeforeAfter filter
                {
                    "type": "before_after",
                    "field_name": "release_date",
                    "before": datetime(2000, 1, 1, tzinfo=timezone.utc),
                    "after": None,
                },
                # OnBeforeAfter filter
                {
                    "type": "on_before_after",
                    "field_name": "release_date",
                    "on_or_before": datetime(2009, 6, 1, tzinfo=timezone.utc),
                    "on_or_after": None,
                },
                # CollectionFilter
                {
                    "type": "collection",
                    "field_name": "title",
                    "values": ["The Matrix", "Shawshank Redemption"],
                },
                # NotInCollectionFilter
                {
                    "type": "not_in_collection",
                    "field_name": "title",
                    "values": ["The Hangover"],
                },
                # SearchFilter
                {
                    "type": "search",
                    "field_name": "title",
                    "value": "Matrix",
                    "ignore_case": True,
                },
                # NotInSearchFilter
                {
                    "type": "not_in_search",
                    "field_name": "title",
                    "value": "Hangover",
                    "ignore_case": True,
                },
                # ComparisonFilter
                {
                    "type": "comparison",
                    "field_name": "genre",
                    "operator": "eq",
                    "value": "Action",
                },
                # ExistsFilter
                {
                    "type": "exists",
                    "values": [Movie.genre == "Comedy"],
                },
                # NotExistsFilter
                {
                    "type": "not_exists",
                    "values": [Movie.genre == "SciFi"],
                },
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    # Should match all movies since at least one condition is true for each
    assert len(results) == 3
    assert {r.title for r in results} == {"The Matrix", "The Hangover", "Shawshank Redemption"}


def test_comparison_filter(db_session: Session) -> None:
    """Test ComparisonFilter with various operators."""
    # Test equality operator
    eq_filter = ComparisonFilter(field_name="genre", operator="eq", value="Action")
    statement = eq_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1
    assert results[0].title == "The Matrix"

    # Test inequality operator
    ne_filter = ComparisonFilter(field_name="genre", operator="ne", value="Action")
    statement = ne_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Hangover", "Shawshank Redemption"}

    # Test greater than operator
    gt_filter = ComparisonFilter(
        field_name="release_date", operator="gt", value=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    statement = gt_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 1
    assert results[0].title == "The Hangover"

    # Test less than operator
    lt_filter = ComparisonFilter(
        field_name="release_date", operator="lt", value=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    statement = lt_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test greater than or equal operator
    ge_filter = ComparisonFilter(
        field_name="release_date", operator="ge", value=datetime(1999, 3, 31, tzinfo=timezone.utc)
    )
    statement = ge_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "The Hangover"}

    # Test less than or equal operator
    le_filter = ComparisonFilter(
        field_name="release_date", operator="le", value=datetime(1999, 3, 31, tzinfo=timezone.utc)
    )
    statement = le_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test invalid operator (should raise ValueError)
    invalid_filter = ComparisonFilter(field_name="genre", operator="invalid", value="Action")
    with pytest.raises(ValueError) as exc_info:
        invalid_filter.append_to_statement(select(Movie), Movie)
    assert "Invalid operator 'invalid'" in str(exc_info.value)
    assert "Must be one of:" in str(exc_info.value)

    # Test invalid operator with common mistake (using '=' instead of 'eq')
    invalid_filter = ComparisonFilter(field_name="genre", operator="=", value="Action")
    with pytest.raises(ValueError) as exc_info:
        invalid_filter.append_to_statement(select(Movie), Movie)
    assert "Invalid operator '='" in str(exc_info.value)
    assert "Must be one of:" in str(exc_info.value)

    # Test invalid operator with empty string
    invalid_filter = ComparisonFilter(field_name="genre", operator="", value="Action")
    with pytest.raises(ValueError) as exc_info:
        invalid_filter.append_to_statement(select(Movie), Movie)
    assert "Invalid operator ''" in str(exc_info.value)
    assert "Must be one of:" in str(exc_info.value)


def test_collection_filter_prefer_any(db_session: Session) -> None:
    """Test CollectionFilter with prefer_any parameter."""
    # Test with prefer_any=False (default, using IN)
    collection_filter: CollectionFilter[str] = CollectionFilter(
        field_name="title", values=["The Matrix", "Shawshank Redemption"]
    )
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with prefer_any=True (using ANY)
    # Skip this test for SQLite since it doesn't support the ANY function
    from sqlalchemy.dialects import sqlite

    if not isinstance(db_session.get_bind().dialect, sqlite.dialect):
        collection_filter = CollectionFilter[str](field_name="title", values=["The Matrix", "Shawshank Redemption"])
        statement = collection_filter.append_to_statement(select(Movie), Movie, prefer_any=True)
        results = db_session.execute(statement).scalars().all()
        assert len(results) == 2
        assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with empty collection
    collection_filter = CollectionFilter[str](field_name="title", values=[])
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 0

    # Test with None values
    collection_filter = CollectionFilter[str](field_name="title", values=None)
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 3  # Should return all movies


def test_not_in_collection_filter_prefer_any(db_session: Session) -> None:
    """Test NotInCollectionFilter with prefer_any parameter."""
    # Test with prefer_any=False (default, using NOT IN)
    not_in_collection_filter: NotInCollectionFilter[str] = NotInCollectionFilter(
        field_name="title", values=["The Hangover"]
    )
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with prefer_any=True (using != ANY)
    # Skip this test for SQLite since it doesn't support the ANY function
    from sqlalchemy.dialects import sqlite

    if not isinstance(db_session.get_bind().dialect, sqlite.dialect):
        not_in_collection_filter = NotInCollectionFilter[str](field_name="title", values=["The Hangover"])
        statement = not_in_collection_filter.append_to_statement(select(Movie), Movie, prefer_any=True)
        results = db_session.execute(statement).scalars().all()
        assert len(results) == 2
        assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with empty collection
    not_in_collection_filter = NotInCollectionFilter[str](field_name="title", values=[])
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 3  # Should return all movies

    # Test with None values
    not_in_collection_filter = NotInCollectionFilter[str](field_name="title", values=None)
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = db_session.execute(statement).scalars().all()
    assert len(results) == 3  # Should return all movies

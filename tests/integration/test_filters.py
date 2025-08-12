from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Engine, String, select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.base import BigIntBase, UUIDAuditBase
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
from tests.integration.helpers import async_clean_tables, clean_tables, get_worker_id

if TYPE_CHECKING:
    from pytest import FixtureRequest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("filters"),
]


# Module-level cache for Movie model and counter for unique names
_movie_model_cache: dict[str, type] = {}
_movie_class_counter = 0


def get_movie_model_for_engine(engine_dialect_name: str, worker_id: str) -> type[DeclarativeBase]:
    """Create appropriate Movie model based on engine dialect."""
    global _movie_class_counter
    cache_key = f"movie_{worker_id}_{engine_dialect_name}"

    if cache_key not in _movie_model_cache:
        # Create unique base class with its own metadata for each engine
        class TestBase(DeclarativeBase):
            pass

        # Use UUID base for CockroachDB and Spanner, BigInt for others
        base_class = UUIDAuditBase if engine_dialect_name.startswith(("cockroach", "spanner")) else BigIntBase

        # Create class with globally unique name to avoid SQLAlchemy registry conflicts
        _movie_class_counter += 1
        unique_suffix = f"{_movie_class_counter}_{worker_id}_{engine_dialect_name}"

        # Create the class normally, not with type() to ensure proper annotation resolution
        class Movie(base_class, TestBase):  # type: ignore[valid-type,misc]
            __tablename__ = f"test_movies_{worker_id}_{engine_dialect_name}"
            __mapper_args__ = {"concrete": True}

            title: Mapped[str] = mapped_column(String(length=100))
            release_date: Mapped[datetime] = mapped_column()
            genre: Mapped[str] = mapped_column(String(length=50))

        # Set unique name to avoid registry conflicts
        Movie.__name__ = f"Movie_{unique_suffix}"
        Movie.__qualname__ = f"Movie_{unique_suffix}"

        _movie_model_cache[cache_key] = Movie

    return _movie_model_cache[cache_key]


@pytest.fixture(scope="session")
def cached_movie_model(request: FixtureRequest) -> type[DeclarativeBase]:
    """Create Movie model once per session/worker - placeholder."""
    # This will be replaced by movie_model_sync/async fixtures
    return None  # type: ignore[return-value]


@pytest.fixture
def movie_model_sync(
    engine: Engine,
    request: FixtureRequest,
) -> Generator[type[DeclarativeBase], None, None]:
    """Setup movie table for sync engines with fast cleanup."""
    worker_id = get_worker_id(request)
    engine_dialect_name = getattr(engine.dialect, "name", "mock")

    # Get the appropriate model for this engine type
    movie_model = get_movie_model_for_engine(engine_dialect_name, worker_id)

    # Skip for mock engines
    if engine_dialect_name != "mock":
        # Create table once per engine type
        movie_model.metadata.create_all(engine)

    yield movie_model

    # Fast data-only cleanup between tests
    if engine_dialect_name != "mock":
        clean_tables(engine, movie_model.metadata)


@pytest.fixture
async def movie_model_async(
    cached_movie_model: type[DeclarativeBase],
    async_engine: AsyncEngine,
) -> AsyncGenerator[type[DeclarativeBase], None]:
    """Setup movie table for async engines with fast cleanup."""
    # Skip for mock engines
    if getattr(async_engine.dialect, "name", "") != "mock":
        # Create table once per engine type
        async with async_engine.begin() as conn:
            await conn.run_sync(cached_movie_model.metadata.create_all)

    yield cached_movie_model

    # Fast data-only cleanup between tests
    if getattr(async_engine.dialect, "name", "") != "mock":
        await async_clean_tables(async_engine, cached_movie_model.metadata)


def setup_movie_data(session: Session, movie_model: type[DeclarativeBase]) -> None:
    """Add test data to the session."""
    dialect_name = getattr(session.bind.dialect, "name", "")
    if dialect_name == "mock":
        # For mock engines, configure the mock to return expected data
        mock_movies = [
            type(
                "Movie",
                (),
                {"title": "The Matrix", "release_date": datetime(1999, 3, 31, tzinfo=timezone.utc), "genre": "Action"},
            ),
            type(
                "Movie",
                (),
                {"title": "The Hangover", "release_date": datetime(2009, 6, 1, tzinfo=timezone.utc), "genre": "Comedy"},
            ),
            type(
                "Movie",
                (),
                {
                    "title": "Shawshank Redemption",
                    "release_date": datetime(1994, 10, 14, tzinfo=timezone.utc),
                    "genre": "Drama",
                },
            ),
        ]
        session.execute.return_value.scalars.return_value.all.return_value = mock_movies
        return

    Movie = movie_model

    # CockroachDB and Spanner require UUID primary keys to be provided
    dialect_name = getattr(session.bind.dialect, "name", "")
    movie_data = [
        {"title": "The Matrix", "release_date": datetime(1999, 3, 31, tzinfo=timezone.utc), "genre": "Action"},
        {"title": "The Hangover", "release_date": datetime(2009, 6, 1, tzinfo=timezone.utc), "genre": "Comedy"},
        {
            "title": "Shawshank Redemption",
            "release_date": datetime(1994, 10, 14, tzinfo=timezone.utc),
            "genre": "Drama",
        },
    ]

    if dialect_name.startswith(("cockroach", "spanner")):
        # For UUID-based models, generate IDs
        from advanced_alchemy.base import UUIDAuditBase

        if issubclass(Movie, UUIDAuditBase):
            import uuid

            for data in movie_data:
                data["id"] = str(uuid.uuid4())

    movies = [Movie(**data) for data in movie_data]
    session.add_all(movies)
    session.commit()


def test_before_after_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    before_after_filter = BeforeAfter(
        field_name="release_date", before=datetime(1999, 3, 31, tzinfo=timezone.utc), after=None
    )
    statement = before_after_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1


def test_on_before_after_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    on_before_after_filter = OnBeforeAfter(
        field_name="release_date", on_or_before=None, on_or_after=datetime(1999, 3, 31, tzinfo=timezone.utc)
    )
    statement = on_before_after_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2


def test_collection_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    collection_filter = CollectionFilter(field_name="title", values=["The Matrix", "Shawshank Redemption"])
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2


def test_not_in_collection_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    not_in_collection_filter = NotInCollectionFilter(field_name="title", values=["The Hangover"])
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2


def test_exists_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    # Test EXISTS with a condition that is true for at least one row
    # Should return all rows because the subquery finds a match
    exists_filter_1 = ExistsFilter(values=[Movie.genre == "Action"])
    # For correlated subquery: Should return only rows where the condition is true
    statement = exists_filter_1.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1

    # Test EXISTS with multiple conditions using AND (default) that are true for different rows
    # The combination (Action AND Drama) is never true for a single row, so subquery is empty
    exists_filter_2 = ExistsFilter(values=[Movie.genre == "Action", Movie.genre == "Drama"])
    # For correlated subquery: Should return only rows where BOTH conditions are true (none)
    statement = exists_filter_2.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 0

    # Test EXISTS with a condition that is never true
    # Should return no rows because the subquery is empty
    exists_filter_3 = ExistsFilter(values=[Movie.genre == "SciFi"])
    # For correlated subquery: Should return only rows where the condition is true (none)
    statement = exists_filter_3.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 0


def test_exists_filter_operators(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    # Test EXISTS with OR operator - condition is true
    exists_filter_or = ExistsFilter(values=[Movie.genre == "Action", Movie.genre == "SciFi"], operator="or")
    # For correlated subquery: Should return rows where EITHER condition is true (only Action movie)
    statement = exists_filter_or.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1

    exists_filter_or_2 = ExistsFilter(values=[Movie.genre == "Action", Movie.genre == "Drama"], operator="or")
    # For correlated subquery: Should return rows where EITHER condition is true (only Action movie)
    statement = exists_filter_or_2.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2

    # Test EXISTS with AND operator - conditions never true simultaneously
    exists_filter_and = ExistsFilter(
        values=[Movie.title.startswith("The Matrix"), Movie.title.startswith("Shawshank")], operator="and"
    )
    # For correlated subquery: Should return rows where BOTH conditions are true (none)
    statement = exists_filter_and.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 0


def test_not_exists_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    # Test NOT EXISTS with a condition that is true for at least one row
    # Should return no rows because the subquery finds a match
    not_exists_filter_true = NotExistsFilter(values=[Movie.title.like("%Hangover%")])
    # For correlated subquery: Should return rows where condition is FALSE (Matrix, Shawshank)
    statement = not_exists_filter_true.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2

    # Test NOT EXISTS with a condition that is never true
    # Should return all rows because the subquery is empty
    not_exists_filter_false = NotExistsFilter(values=[Movie.title == "NonExistentMovie"])
    # For correlated subquery: Should return rows where condition is FALSE (all movies)
    statement = not_exists_filter_false.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 3


def test_not_exists_filter_operators(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    # Test NOT EXISTS with OR operator - Should return rows where NEITHER condition is true
    not_exists_filter_or = NotExistsFilter(values=[Movie.genre == "Comedy", Movie.genre == "SciFi"], operator="or")
    # For correlated subquery: Should return rows where NEITHER condition is true (Action, Drama)
    statement = not_exists_filter_or.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2

    # Test NOT EXISTS with AND operator - Should return rows where NOT BOTH conditions are true
    not_exists_filter_and = NotExistsFilter(
        values=[Movie.title.startswith("The Matrix"), Movie.title.startswith("Shawshank")], operator="and"
    )
    # For correlated subquery: Should return rows where NOT BOTH conditions are true (all)
    statement = not_exists_filter_and.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 3


def test_limit_offset_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    limit_offset_filter = LimitOffset(limit=2, offset=1)
    statement = limit_offset_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2


def test_order_by_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    order_by_filter = OrderBy(field_name="release_date", sort_order="asc")
    statement = order_by_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert results[0].title == "Shawshank Redemption"
    order_by_filter = OrderBy(field_name="release_date", sort_order="desc")
    statement = order_by_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert results[0].title == "The Hangover"


def test_search_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    search_filter = SearchFilter(field_name="title", value="Hangover")
    statement = search_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1


def test_filter_group_logical_operators(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    # Test AND operator
    before_2000 = BeforeAfter(field_name="release_date", before=datetime(2000, 1, 1, tzinfo=timezone.utc), after=None)
    has_the_in_title = SearchFilter(field_name="title", value="The", ignore_case=True)

    # Should match only "The Matrix" (before 2000 AND has "The" in title)
    and_filter_group = FilterGroup(
        logical_operator=and_,
        filters=[before_2000, has_the_in_title],
    )

    statement = and_filter_group.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
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
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_multi_filter_basic(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
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
    results = session.execute(statement).scalars().all()
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
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_multi_filter_nested(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
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
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "The Hangover"}


def test_multi_filter_empty_filters(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    """Test MultiFilter with empty filter lists."""
    # Test with empty filter list
    multi_filter = MultiFilter(filters={"and_": []})
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    # Should return all movies since no filters are applied
    assert len(results) == 3

    # Test with empty filters dict
    multi_filter = MultiFilter(filters={})
    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    # Should return all movies since no filters are applied
    assert len(results) == 3


def test_multi_filter_invalid_filter_type(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
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
    results = session.execute(statement).scalars().all()
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
    results = session.execute(statement).scalars().all()
    # Should return all movies since invalid filter is ignored
    assert len(results) == 3


def test_multi_filter_invalid_filter_args(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
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
    results = session.execute(statement).scalars().all()
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
    results = session.execute(statement).scalars().all()
    # Should return all movies since invalid filter is ignored
    assert len(results) == 3


def test_multi_filter_invalid_logical_operator(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
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
    results = session.execute(statement).scalars().all()
    # Should return all movies since invalid operator is ignored
    assert len(results) == 3


def test_multi_filter_complex_nested(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
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
    results = session.execute(statement).scalars().all()
    # Should match "The Matrix" (before 2000 AND has "The" in title)
    # and "Shawshank Redemption" (before 2000 AND is a drama)
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_multi_filter_all_filter_types(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
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
    results = session.execute(statement).scalars().all()
    # Should match all movies since at least one condition is true for each
    assert len(results) == 3
    assert {r.title for r in results} == {"The Matrix", "The Hangover", "Shawshank Redemption"}


def test_comparison_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    """Test ComparisonFilter with various operators."""
    # Test equality operator
    eq_filter = ComparisonFilter(field_name="genre", operator="eq", value="Action")
    statement = eq_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1
    assert results[0].title == "The Matrix"

    # Test inequality operator
    ne_filter = ComparisonFilter(field_name="genre", operator="ne", value="Action")
    statement = ne_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Hangover", "Shawshank Redemption"}

    # Test greater than operator
    gt_filter = ComparisonFilter(
        field_name="release_date", operator="gt", value=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    statement = gt_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1
    assert results[0].title == "The Hangover"

    # Test less than operator
    lt_filter = ComparisonFilter(
        field_name="release_date", operator="lt", value=datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    statement = lt_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test greater than or equal operator
    ge_filter = ComparisonFilter(
        field_name="release_date", operator="ge", value=datetime(1999, 3, 31, tzinfo=timezone.utc)
    )
    statement = ge_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "The Hangover"}

    # Test less than or equal operator
    le_filter = ComparisonFilter(
        field_name="release_date", operator="le", value=datetime(1999, 3, 31, tzinfo=timezone.utc)
    )
    statement = le_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
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


def test_collection_filter_prefer_any(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    """Test CollectionFilter with prefer_any parameter."""
    # Test with prefer_any=False (default, using IN)
    collection_filter: CollectionFilter[str] = CollectionFilter(
        field_name="title", values=["The Matrix", "Shawshank Redemption"]
    )
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with prefer_any=True (using ANY)
    # Skip this test for SQLite since it doesn't support the ANY function
    from sqlalchemy.dialects import sqlite

    if not isinstance(session.get_bind().dialect, sqlite.dialect):
        collection_filter = CollectionFilter[str](field_name="title", values=["The Matrix", "Shawshank Redemption"])
        statement = collection_filter.append_to_statement(select(Movie), Movie, prefer_any=True)
        results = session.execute(statement).scalars().all()
        assert len(results) == 2
        assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with empty collection
    collection_filter = CollectionFilter[str](field_name="title", values=[])
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 0

    # Test with None values
    collection_filter = CollectionFilter[str](field_name="title", values=None)
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 3  # Should return all movies


def test_not_in_collection_filter_prefer_any(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Spanner Emulator - EXISTS filters have constraints in emulator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner Emulator has constraints with EXISTS filters")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    """Test NotInCollectionFilter with prefer_any parameter."""
    # Test with prefer_any=False (default, using NOT IN)
    not_in_collection_filter: NotInCollectionFilter[str] = NotInCollectionFilter(
        field_name="title", values=["The Hangover"]
    )
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with prefer_any=True (using != ANY)
    # Skip this test for SQLite since it doesn't support the ANY function
    from sqlalchemy.dialects import sqlite

    if not isinstance(session.get_bind().dialect, sqlite.dialect):
        not_in_collection_filter = NotInCollectionFilter[str](field_name="title", values=["The Hangover"])
        statement = not_in_collection_filter.append_to_statement(select(Movie), Movie, prefer_any=True)
        results = session.execute(statement).scalars().all()
        assert len(results) == 2
        assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}

    # Test with empty collection
    not_in_collection_filter = NotInCollectionFilter[str](field_name="title", values=[])
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 3  # Should return all movies

    # Test with None values
    not_in_collection_filter = NotInCollectionFilter[str](field_name="title", values=None)
    statement = not_in_collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 3  # Should return all movies


# Session-level teardown to ensure tables are dropped
@pytest.fixture(scope="session", autouse=True)
def cleanup_filter_tables(request: FixtureRequest) -> Generator[None, None, None]:
    """Ensure all filter test tables are dropped at session end."""
    yield

    # Clean up all cached tables at session end
    for cache_key, model in _movie_model_cache.items():
        # Tables are cleaned up by individual engine fixtures
        pass

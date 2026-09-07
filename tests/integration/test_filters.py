from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import pytest
from google.cloud.sqlalchemy_spanner.sqlalchemy_spanner import SpannerDialect
from pytest import FixtureRequest
from sqlalchemy import Boolean, Engine, ForeignKey, String, create_engine, func, select
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, joinedload, mapped_column, relationship

from advanced_alchemy.base import BigIntBase, UUIDAuditBase
from advanced_alchemy.filters import (
    BeforeAfter,
    BooleanFilter,
    ChoicesFilter,
    CollectionFilter,
    ComparisonFilter,
    ExistsFilter,
    FilterGroup,
    LimitOffset,
    MultiFilter,
    NotExistsFilter,
    NotInCollectionFilter,
    NotInSearchFilter,
    NotNullFilter,
    NullFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
    and_,
    or_,
)
from tests.integration.helpers import get_worker_id

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

        # Create the class with unique name from the start to avoid registry conflicts
        class_name = f"Movie_{unique_suffix}"

        Movie = type(
            class_name,
            (base_class, TestBase),
            {
                "__tablename__": f"test_movies_{worker_id}_{engine_dialect_name}",
                "__mapper_args__": {"concrete": True},
                "__module__": __name__,  # Set proper module
                "title": mapped_column(String(length=100)),
                "release_date": mapped_column(),
                "genre": mapped_column(String(length=50)),
                "director": mapped_column(String(length=100), nullable=True),
                "is_featured": mapped_column(Boolean(), default=False),
                "__annotations__": {
                    "title": Mapped[str],
                    "release_date": Mapped[datetime],
                    "genre": Mapped[str],
                    "director": Mapped[Optional[str]],
                    "is_featured": Mapped[bool],
                },
            },
        )  # type: ignore[valid-type,misc]

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
    """Setup movie table for sync engines."""
    worker_id = get_worker_id(request)
    engine_dialect_name = getattr(engine.dialect, "name", "mock")

    # Skip Spanner, CockroachDB, and MSSQL due to database-specific issues
    if engine_dialect_name.startswith(("spanner", "cockroach", "mssql")):
        pytest.skip(f"Filter tests are not supported on {engine_dialect_name}")

    # Get the appropriate model for this engine type
    movie_model = get_movie_model_for_engine(engine_dialect_name, worker_id)

    # Skip for mock engines
    if engine_dialect_name != "mock":
        # Create table once per engine type
        movie_model.metadata.create_all(engine)

    yield movie_model

    # Cleanup is handled by _auto_clean_sync_db fixture


@pytest.fixture
async def movie_model_async(
    cached_movie_model: type[DeclarativeBase],
    async_engine: AsyncEngine,
) -> AsyncGenerator[type[DeclarativeBase], None]:
    """Setup movie table for async engines."""
    engine_dialect_name = getattr(async_engine.dialect, "name", "mock")

    # Skip Spanner, CockroachDB, and MSSQL due to database-specific issues
    if engine_dialect_name.startswith(("spanner", "cockroach", "mssql")):
        pytest.skip(f"Filter tests are not supported on {engine_dialect_name}")

    # Skip for mock engines
    if engine_dialect_name != "mock":
        # Create table once per engine type
        async with async_engine.begin() as conn:
            await conn.run_sync(cached_movie_model.metadata.create_all)

    yield cached_movie_model

    # Cleanup is handled by _auto_clean_async_db fixture


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
        {
            "title": "The Matrix",
            "release_date": datetime(1999, 3, 31, tzinfo=timezone.utc),
            "genre": "Action",
            "director": "Wachowskis",
            "is_featured": True,
        },
        {
            "title": "The Hangover",
            "release_date": datetime(2009, 6, 1, tzinfo=timezone.utc),
            "genre": "Comedy",
            "director": None,  # NULL director for testing NullFilter
            "is_featured": False,
        },
        {
            "title": "Shawshank Redemption",
            "release_date": datetime(1994, 10, 14, tzinfo=timezone.utc),
            "genre": "Drama",
            "director": "Frank Darabont",
            "is_featured": True,
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

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    collection_filter = CollectionFilter(field_name="title", values=["The Matrix", "Shawshank Redemption"])
    statement = collection_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2


def test_choices_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    session.execute(Movie.__table__.delete())
    session.commit()
    setup_movie_data(session, Movie)
    choices_filter = ChoicesFilter(field_name="genre", values=["Action", "Drama"])
    statement = choices_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2


def test_boolean_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    session.execute(Movie.__table__.delete())
    session.commit()
    setup_movie_data(session, Movie)
    boolean_filter = BooleanFilter(field_name="is_featured", value=True)
    statement = boolean_filter.append_to_statement(select(Movie), Movie)
    oracle_sql = str(statement.compile(dialect=oracle.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
    assert " IS 1" not in oracle_sql
    assert " = 1" in oracle_sql
    results = session.execute(statement).scalars().all()
    assert len(results) == 2

    no_op_filter = BooleanFilter(field_name="is_featured", value=None)
    statement = no_op_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 3


def test_not_in_collection_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

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

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    limit_offset_filter = LimitOffset(limit=2, offset=1)
    # Add ORDER BY for MSSQL compatibility (required when using OFFSET)
    statement = select(Movie).order_by(Movie.id)
    statement = limit_offset_filter.append_to_statement(statement, Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 2


def test_order_by_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

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


def test_order_by_with_func_random(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test OrderBy filter with func.random() expression."""
    Movie = movie_model_sync

    # Skip mock engines
    dialect_name = getattr(session.bind.dialect, "name", "")
    if dialect_name == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Skip Oracle - uses dbms_random.value() instead of random()
    if dialect_name.startswith("oracle"):
        pytest.skip("Oracle uses dbms_random.value() instead of random()")

    # Clean any existing data first, then setup fresh data
    if dialect_name != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test func.random() - should not raise type error
    order_by_filter = OrderBy(field_name=func.random())
    statement = order_by_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    # Should return all movies, order is random
    assert len(results) == 3


def test_order_by_with_func_lower(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test OrderBy filter with func.lower() for case-insensitive sorting."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test func.lower() for case-insensitive alphabetical sorting
    order_by_filter = OrderBy(field_name=func.lower(Movie.title), sort_order="asc")
    statement = order_by_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    # Should be sorted alphabetically: Shawshank, The Hangover, The Matrix
    assert results[0].title == "Shawshank Redemption"
    assert results[1].title == "The Hangover"
    assert results[2].title == "The Matrix"


def test_order_by_with_instrumented_attribute(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test OrderBy filter with InstrumentedAttribute (Model.field)."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test with InstrumentedAttribute (backward compatibility)
    order_by_filter = OrderBy(field_name=Movie.release_date, sort_order="asc")
    statement = order_by_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert results[0].title == "Shawshank Redemption"


def test_order_by_nulls_placement(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """ "The Hangover" has a NULL director, and the databases disagree about where NULLs sort.

    `nulls` pins it: without it, a descending sort puts the NULL row first on PostgreSQL and last on
    SQLite, so the same query pages differently per backend.
    """
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    for sort_order in ("asc", "desc"):
        nulls_last_filter = OrderBy(field_name="director", sort_order=sort_order, nulls="last")
        results = session.execute(nulls_last_filter.append_to_statement(select(Movie), Movie)).scalars().all()
        assert results[-1].director is None, f"{sort_order} with nulls='last' must end with the NULL row"

        nulls_first_filter = OrderBy(field_name="director", sort_order=sort_order, nulls="first")
        results = session.execute(nulls_first_filter.append_to_statement(select(Movie), Movie)).scalars().all()
        assert results[0].director is None, f"{sort_order} with nulls='first' must start with the NULL row"


class OrderByBase(DeclarativeBase):
    pass


class OrderByMovie(OrderByBase):
    __tablename__ = "order_by_nulls_movie"

    id: Mapped[int] = mapped_column(primary_key=True)
    director: Mapped[str] = mapped_column(String(length=50), nullable=True)
    credits: Mapped[list["OrderByCredit"]] = relationship()


class OrderByCredit(OrderByBase):
    __tablename__ = "order_by_nulls_credit"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(ForeignKey(OrderByMovie.id))


@pytest.fixture
def order_by_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://")
    try:
        OrderByBase.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(
                OrderByMovie(id=index, director=director, credits=[OrderByCredit(), OrderByCredit()])
                for index, director in enumerate((None, "z", "a"), start=1)
            )
            session.commit()
            yield session
    finally:
        engine.dispose()


NULLS_NATIVE_DIALECTS = [
    postgresql.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
    sqlite.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
    oracle.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
]
NULLS_EMULATED_DIALECTS = [
    mysql.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
    mssql.dialect(),  # type: ignore[no-untyped-call,unused-ignore]
]

NULLS_NATIVE = pytest.mark.parametrize("dialect", NULLS_NATIVE_DIALECTS)
NULLS_EMULATED = pytest.mark.parametrize("dialect", NULLS_EMULATED_DIALECTS)


def _compile_order_by_nulls(dialect: Any, **kwargs: Any) -> str:
    statement = OrderBy(field_name="director", **kwargs).append_to_statement(select(OrderByMovie), OrderByMovie)
    return str(statement.compile(dialect=dialect))


@NULLS_NATIVE
@pytest.mark.parametrize(("nulls", "clause"), [("first", "NULLS FIRST"), ("last", "NULLS LAST")])
@pytest.mark.unit
def test_dialects_with_the_syntax_get_the_native_clause(dialect: Any, nulls: str, clause: str) -> None:
    """Keeping the native clause is what lets an index on the column still satisfy the ordering."""
    assert clause in _compile_order_by_nulls(dialect, sort_order="desc", nulls=nulls)


@NULLS_EMULATED
@pytest.mark.parametrize(("sort_order", "nulls"), [("asc", "last"), ("desc", "first")])
@pytest.mark.unit
def test_dialects_without_the_syntax_get_a_nullity_key(dialect: Any, sort_order: str, nulls: str) -> None:
    """MySQL and SQL Server reject `NULLS FIRST`/`NULLS LAST` outright, so it must not be emitted."""
    compiled = _compile_order_by_nulls(dialect, sort_order=sort_order, nulls=nulls)

    assert "NULLS" not in compiled
    assert "CASE WHEN" in compiled
    assert compiled.rstrip().endswith(sort_order.upper())


@NULLS_EMULATED
@pytest.mark.parametrize(("sort_order", "nulls"), [("asc", "first"), ("desc", "last")])
@pytest.mark.unit
def test_placements_native_to_null_lowest_backends_stay_plain(dialect: Any, sort_order: str, nulls: str) -> None:
    """These backends sort NULL lowest, so the plain term already places it and an index can satisfy the sort."""
    compiled = _compile_order_by_nulls(dialect, sort_order=sort_order, nulls=nulls)

    assert "NULLS" not in compiled
    assert "CASE" not in compiled
    assert compiled.rstrip().endswith(f"director {sort_order.upper()}")


@NULLS_EMULATED
@pytest.mark.parametrize(
    ("sort_order", "nulls", "when_null"), [("asc", "last", "THEN 1 ELSE 0"), ("desc", "first", "THEN 0 ELSE 1")]
)
@pytest.mark.unit
def test_the_nullity_key_sorts_the_right_way(dialect: Any, sort_order: str, nulls: str, when_null: str) -> None:
    """The key ascends, so NULLs need the higher value to land last and the lower one to land first."""
    assert when_null in _compile_order_by_nulls(dialect, sort_order=sort_order, nulls=nulls)


@pytest.mark.parametrize("dialect", NULLS_NATIVE_DIALECTS + NULLS_EMULATED_DIALECTS)
@pytest.mark.unit
def test_the_default_is_untouched(dialect: Any) -> None:
    """Without `nulls` no NULLS clause and no CASE key are emitted."""
    compiled = _compile_order_by_nulls(dialect, sort_order="desc")

    assert "NULLS" not in compiled
    assert "CASE" not in compiled


@pytest.mark.parametrize("sort_order", ["asc", "desc"])
@pytest.mark.parametrize("nulls", ["first", "last"])
@pytest.mark.unit
def test_nulls_placement_with_paginated_eager_loading(
    order_by_session: Session, sort_order: Literal["asc", "desc"], nulls: Literal["first", "last"]
) -> None:
    statement = OrderBy("director", sort_order, nulls).append_to_statement(
        select(OrderByMovie).options(joinedload(OrderByMovie.credits)).limit(2).offset(1), OrderByMovie
    )
    movies = order_by_session.scalars(statement).unique().all()

    expected = [3, 2] if sort_order == "asc" else [2, 3]
    expected = [1, *expected] if nulls == "first" else [*expected, 1]
    assert [movie.id for movie in movies] == expected[1:]
    assert all(len(movie.credits) == 2 for movie in movies)


@NULLS_EMULATED
@pytest.mark.unit
def test_emulated_null_ordering_expands_labels_inside_case(dialect: Any) -> None:
    director = func.lower(OrderByMovie.director).label("normalized_director")
    statement = OrderBy(director, nulls="last").append_to_statement(select(director), OrderByMovie)

    compiled = str(statement.compile(dialect=dialect))

    assert compiled.endswith(
        "ORDER BY CASE WHEN (lower(order_by_nulls_movie.director) IS NULL) THEN 1 ELSE 0 END, normalized_director ASC"
    )


@NULLS_EMULATED
@pytest.mark.unit
def test_emulated_eager_loading_adapts_the_ordering_column(dialect: Any) -> None:
    statement = OrderBy("director", nulls="last").append_to_statement(
        select(OrderByMovie).options(joinedload(OrderByMovie.credits)).limit(2), OrderByMovie
    )
    compiled = str(statement.compile(dialect=dialect))

    assert "ASC AS" not in compiled
    assert compiled.endswith("ORDER BY CASE WHEN (anon_1.director IS NULL) THEN 1 ELSE 0 END, anon_1.director ASC")


@pytest.mark.unit
def test_nulls_placement_reuses_distinct_compiled_statements(order_by_session: Session) -> None:
    cache: dict[Any, Any] = {}
    for _ in range(2):
        for field in ("director", "id"):
            for sort_order in ("asc", "desc"):
                for nulls in ("first", "last"):
                    statement = OrderBy(field, sort_order, nulls).append_to_statement(
                        select(OrderByMovie.id), OrderByMovie
                    )
                    result = order_by_session.scalars(statement, execution_options={"compiled_cache": cache}).all()
                    if field == "id":
                        expected = [1, 2, 3] if sort_order == "asc" else [3, 2, 1]
                    else:
                        expected = [3, 2] if sort_order == "asc" else [2, 3]
                        expected = [1, *expected] if nulls == "first" else [*expected, 1]
                    assert result == expected
        assert len(cache) == 8


def test_search_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)
    search_filter = SearchFilter(field_name="title", value="Hangover")
    statement = search_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1


@pytest.mark.unit
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
    Movie = get_movie_model_for_engine("sqlite", "search_compile")
    expected = select(Movie).where(getattr(Movie.title, operator)(f"%{value}%")).compile(dialect=dialect)
    for search_filter in (
        filter_type("title", value, ignore_case=ignore_case),
        filter_type("title", value, ignore_case=ignore_case, escape_wildcards=False),
    ):
        compiled = search_filter.append_to_statement(select(Movie), Movie).compile(dialect=dialect)
        assert str(compiled) == str(expected)
        assert compiled.params == expected.params


def test_search_filter_escapes_wildcards(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Wildcard escaping is opt-in; without it `%` and `_` in the value stay SQL wildcards.

    "The_" is not a substring of any title, but `_` is a single-character wildcard in LIKE, so
    without escaping it would match both "The Matrix" and "The Hangover".
    """
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    escaped = SearchFilter(field_name="title", value="The_", escape_wildcards=True)
    results = session.execute(escaped.append_to_statement(select(Movie), Movie)).scalars().all()
    assert len(results) == 0

    unescaped = SearchFilter(field_name="title", value="The_")
    results = session.execute(unescaped.append_to_statement(select(Movie), Movie)).scalars().all()
    assert {movie.title for movie in results} == {"The Matrix", "The Hangover"}


def test_not_in_search_filter_escapes_wildcards(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """`NotInSearchFilter` inherits the escaping, so a literal "The_" excludes nothing."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    escaped = NotInSearchFilter(field_name="title", value="The_", escape_wildcards=True)
    results = session.execute(escaped.append_to_statement(select(Movie), Movie)).scalars().all()
    assert len(results) == 3

    unescaped = NotInSearchFilter(field_name="title", value="The_")
    results = session.execute(unescaped.append_to_statement(select(Movie), Movie)).scalars().all()
    assert {movie.title for movie in results} == {"Shawshank Redemption"}


@pytest.mark.parametrize("value", ["The_", "50%", "path/", "path/%_"])
@pytest.mark.parametrize("ignore_case", [False, True])
@pytest.mark.parametrize("filter_type", [SearchFilter, NotInSearchFilter])
def test_search_filter_matches_literal_characters(
    session: Session,
    movie_model_sync: type[DeclarativeBase],
    value: str,
    ignore_case: bool,
    filter_type: type[SearchFilter],
) -> None:
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")
    Movie = movie_model_sync
    session.execute(Movie.__table__.delete())
    literal_title = f"prefix {value} suffix"
    other_title = "unrelated title"
    session.add_all(
        Movie(title=title, release_date=datetime(2020, 1, 1, tzinfo=timezone.utc), genre="Drama")
        for title in (literal_title, other_title)
    )
    session.flush()

    search_filter = filter_type(
        field_name="title",
        value=value.upper() if ignore_case else value,
        ignore_case=ignore_case,
        escape_wildcards=True,
    )
    results = session.execute(search_filter.append_to_statement(select(Movie), Movie)).scalars().all()
    expected = literal_title if filter_type is SearchFilter else other_title
    assert [movie.title for movie in results] == [expected]


def test_filter_group_logical_operators(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

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

    # Skip Spanner - has issues with complex multi-filter queries
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner has issues with complex multi-filter queries")

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

    multi_filter = MultiFilter(
        filters={
            "and_": [
                {"type": "boolean", "field_name": "is_featured", "value": True},
                {"type": "choices", "field_name": "genre", "values": ["Action"]},
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()
    assert len(results) == 1
    assert results[0].title == "The Matrix"


def test_comparison_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

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

    # Skip Spanner - has issues with ANY operator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner has issues with ANY operator")

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
    # Only PostgreSQL properly supports the ANY operator with array parameters
    dialect_name = getattr(session.bind.dialect, "name", "")
    if dialect_name in ("postgresql", "psycopg", "asyncpg", "cockroachdb"):
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

    # Skip Spanner - has issues with ANY operator
    if getattr(session.bind.dialect, "name", "") == "spanner+spanner":
        pytest.skip("Spanner has issues with ANY operator")

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
    # Only PostgreSQL properly supports the ANY operator with array parameters
    dialect_name = getattr(session.bind.dialect, "name", "")
    if dialect_name in ("postgresql", "psycopg", "asyncpg"):
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


def test_null_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test NullFilter matches NULL records."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test IS NULL filter on director field
    null_filter = NullFilter("director")
    statement = null_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()

    # Should return only "The Hangover" which has NULL director
    assert len(results) == 1
    assert results[0].title == "The Hangover"
    assert results[0].director is None


def test_not_null_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test NotNullFilter matches NOT NULL records."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test NotNullFilter on director field
    not_null_filter = NotNullFilter("director")
    statement = not_null_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()

    # Should return "The Matrix" and "Shawshank Redemption" which have directors
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_null_filter_combined_with_other_filters(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test NullFilter combined with other filters using AND logic."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test NullFilter combined with CollectionFilter
    # Find movies with a director AND genre is Action or Drama
    not_null_filter = NotNullFilter("director")
    collection_filter = CollectionFilter("genre", ["Action", "Drama"])

    statement = select(Movie)
    statement = not_null_filter.append_to_statement(statement, Movie)
    statement = collection_filter.append_to_statement(statement, Movie)
    results = session.execute(statement).scalars().all()

    # Should return "The Matrix" (Action) and "Shawshank Redemption" (Drama)
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_null_filter_with_multi_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test NullFilter with MultiFilter JSON/dict input."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test MultiFilter with null filter
    multi_filter = MultiFilter(
        filters={
            "and_": [
                {"type": "null", "field_name": "director"},
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()

    # Should return only "The Hangover" with NULL director
    assert len(results) == 1
    assert results[0].title == "The Hangover"


def test_not_null_filter_with_multi_filter(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test NotNullFilter with MultiFilter JSON/dict input."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test MultiFilter with not_null filter
    multi_filter = MultiFilter(
        filters={
            "and_": [
                {"type": "not_null", "field_name": "director"},
            ]
        }
    )

    statement = multi_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()

    # Should return "The Matrix" and "Shawshank Redemption" with directors
    assert len(results) == 2
    assert {r.title for r in results} == {"The Matrix", "Shawshank Redemption"}


def test_null_filter_empty_result(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test NullFilter returns empty list when no matches."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test NullFilter on title field (which is never NULL)
    null_filter = NullFilter("title")
    statement = null_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()

    # Should return empty list since no titles are NULL
    assert len(results) == 0


def test_null_filter_with_instrumented_attribute(session: Session, movie_model_sync: type[DeclarativeBase]) -> None:
    """Test NullFilter with InstrumentedAttribute (Model.field)."""
    Movie = movie_model_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    # Clean any existing data first, then setup fresh data
    if getattr(session.bind.dialect, "name", "") != "mock":
        session.execute(Movie.__table__.delete())
        session.commit()
    setup_movie_data(session, Movie)

    # Test with InstrumentedAttribute
    null_filter = NullFilter(Movie.director)
    statement = null_filter.append_to_statement(select(Movie), Movie)
    results = session.execute(statement).scalars().all()

    # Should return only "The Hangover" which has NULL director
    assert len(results) == 1
    assert results[0].title == "The Hangover"


# Session-level teardown to ensure tables are dropped
@pytest.fixture(scope="session", autouse=True)
def cleanup_filter_tables(request: FixtureRequest) -> Generator[None, None, None]:
    """Ensure all filter test tables are dropped at session end."""
    yield

    # Clean up all cached tables at session end
    for cache_key, model in _movie_model_cache.items():
        # Tables are cleaned up by individual engine fixtures
        pass

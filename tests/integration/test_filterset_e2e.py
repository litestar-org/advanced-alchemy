"""End-to-end integration tests for the Tier 2 :class:`FilterSet` facade.

Phase 5.3 of the FilterSet roadmap. Drives a declarative ``BookFilter``
through the full ``from_query_params → to_filters → MultiFilter`` chain
against the active engine matrix to confirm the Tier 2 declarative
surface and the Tier 1 statement filters integrate as advertised.
"""

from typing import Any, ClassVar

import pytest
import pytest_asyncio
from sqlalchemy import Engine, ForeignKey, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from advanced_alchemy.filters import (
    ComparisonFilter,
    FilterSet,
    NumberFilter,
    OrderingApply,
    OrderingFilter,
    RelationshipFilter,
    StringFilter,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("filterset-e2e"),
]


@pytest.fixture
def skip_unsupported_sync_engines(engine: Engine, uuid_models_dba: dict[str, type]) -> None:
    """Skip backends with known issues; ensure UUID schema exists.

    Mirrors the helper in ``test_relationship_filters`` — Spanner can't
    express the ``unique=True`` constraint on the ``Tag`` model, and the
    Oracle xdist isolation issue tracked in beads ``38c.9.6`` blocks
    these fixtures from running there cleanly.
    """
    dialect_name = getattr(engine.dialect, "name", "")
    if dialect_name == "spanner":
        pytest.skip("Spanner doesn't support direct UNIQUE constraints")
    if dialect_name.startswith("oracle"):
        pytest.skip("Oracle xdist isolation issue (38c.9.6)")
    if dialect_name != "mock":
        uuid_models_dba["base"].metadata.create_all(engine, checkfirst=True)


@pytest_asyncio.fixture(loop_scope="function")
async def skip_unsupported_async_engines(
    async_engine: AsyncEngine,
    uuid_models_dba: dict[str, type],
) -> None:
    dialect_name = getattr(async_engine.dialect, "name", "")
    if dialect_name == "spanner":
        pytest.skip("Spanner doesn't support direct UNIQUE constraints")
    if dialect_name.startswith("oracle"):
        pytest.skip("Oracle xdist isolation issue (38c.9.6)")
    if dialect_name != "mock":
        async with async_engine.begin() as conn:
            await conn.run_sync(uuid_models_dba["base"].metadata.create_all, checkfirst=True)


def _seed_book_data_sync(session: Session, author_model: Any, book_model: Any) -> None:
    christie = author_model(name="Agatha Christie")
    asimov = author_model(name="Isaac Asimov")
    book_a = book_model(title="The Mysterious Affair at Styles", author=christie)
    book_b = book_model(title="Murder on the Orient Express", author=christie)
    book_c = book_model(title="Foundation", author=asimov)
    session.add_all([christie, asimov, book_a, book_b, book_c])
    session.commit()


async def _seed_book_data_async(session: AsyncSession, author_model: Any, book_model: Any) -> None:
    christie = author_model(name="Agatha Christie")
    asimov = author_model(name="Isaac Asimov")
    book_a = book_model(title="The Mysterious Affair at Styles", author=christie)
    book_b = book_model(title="Murder on the Orient Express", author=christie)
    book_c = book_model(title="Foundation", author=asimov)
    session.add_all([christie, asimov, book_a, book_b, book_c])
    await session.commit()


def _build_book_filterset(book_model: type) -> type[FilterSet]:
    """Construct a ``BookFilter`` bound to the worker-specific Book model.

    The shared integration fixtures generate model classes per xdist
    worker, so the FilterSet declaration cannot live at module scope —
    it has to capture the ``book_model`` resolved at test time.
    """

    class BookFilter(FilterSet):
        title = StringFilter(lookups=["exact", "icontains"])
        author__name = StringFilter(lookups=["exact", "iexact"])
        order_by = OrderingFilter(allowed=["title"])

        class Meta:
            model = book_model
            allowed_relationships: ClassVar = ["author"]

    return BookFilter


def test_filterset_e2e_sync(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    author_model: Any = uuid_models["author"]
    book_model: Any = uuid_models["book"]
    _seed_book_data_sync(session, author_model, book_model)

    book_filter_cls = _build_book_filterset(book_model)
    instance = book_filter_cls.from_query_params(
        {"author__name__iexact": "Agatha Christie", "order_by": "title"},
    )
    statement_filters = instance.to_filters()
    assert len(statement_filters) == 2
    assert isinstance(statement_filters[0], RelationshipFilter)
    assert isinstance(statement_filters[-1], OrderingApply)

    stmt = select(book_model)
    for sf in statement_filters:
        stmt = sf.append_to_statement(stmt, book_model)

    titles = [b.title for b in session.execute(stmt).scalars().all()]
    assert titles == ["Murder on the Orient Express", "The Mysterious Affair at Styles"]


@pytest.mark.asyncio
async def test_filterset_e2e_async(
    skip_unsupported_async_engines: None,
    uuid_test_session_async: tuple[AsyncSession, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_async
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    author_model: Any = uuid_models["author"]
    book_model: Any = uuid_models["book"]
    await _seed_book_data_async(session, author_model, book_model)

    book_filter_cls = _build_book_filterset(book_model)
    instance = book_filter_cls.from_query_params(
        {"title__icontains": "founda"},
    )
    statement_filters = instance.to_filters()
    assert len(statement_filters) == 1

    stmt = select(book_model)
    for sf in statement_filters:
        stmt = sf.append_to_statement(stmt, book_model)

    rows = (await session.execute(stmt)).scalars().all()
    assert {b.title for b in rows} == {"Foundation"}


def test_filterset_emits_single_select_sync(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    """Confirm a relationship-traversing filter expands to one round trip.

    The PRD's headline performance claim is that a ``FilterSet`` always
    compiles to a single ``SELECT`` against the parent model — no joins
    pulled in by the filter, no extra round trips for relationship
    hops. Counts ``SELECT`` statements observed on the bind via SQLAlchemy
    event hooks for the duration of the query.
    """
    session, uuid_models = uuid_test_session_sync
    bind = session.bind
    if bind is None or getattr(bind.dialect, "name", "") == "mock":
        pytest.skip("Real engine required for query-count assertion")

    author_model: Any = uuid_models["author"]
    book_model: Any = uuid_models["book"]
    _seed_book_data_sync(session, author_model, book_model)

    book_filter_cls = _build_book_filterset(book_model)
    instance = book_filter_cls.from_query_params({"author__name__exact": "Isaac Asimov"})
    statement_filters = instance.to_filters()

    stmt = select(book_model)
    for sf in statement_filters:
        stmt = sf.append_to_statement(stmt, book_model)

    from sqlalchemy import event

    statements: list[str] = []

    def _record_select(_conn: Any, _cursor: Any, sql: str, *_args: Any, **_kwargs: Any) -> None:
        if sql.lstrip().upper().startswith("SELECT"):
            statements.append(sql)

    sync_engine = getattr(bind, "sync_engine", bind)
    event.listen(sync_engine, "before_cursor_execute", _record_select)
    try:
        rows = session.execute(stmt).scalars().all()
    finally:
        event.remove(sync_engine, "before_cursor_execute", _record_select)

    assert {b.title for b in rows} == {"Foundation"}
    assert len(statements) == 1, statements


class _FsBase(DeclarativeBase):
    pass


class _FsCountry(_FsBase):
    __tablename__ = "fs_e2e_country"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(2))


class _FsOrg(_FsBase):
    __tablename__ = "fs_e2e_org"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    country_id: Mapped[int] = mapped_column(ForeignKey("fs_e2e_country.id"))
    country: Mapped[_FsCountry] = relationship("_FsCountry")


class _FsAuthor(_FsBase):
    __tablename__ = "fs_e2e_author"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    org_id: Mapped[int] = mapped_column(ForeignKey("fs_e2e_org.id"))
    org: Mapped[_FsOrg] = relationship("_FsOrg")


class _FsPost(_FsBase):
    __tablename__ = "fs_e2e_post"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    views: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int] = mapped_column(ForeignKey("fs_e2e_author.id"))
    author: Mapped[_FsAuthor] = relationship("_FsAuthor")


class _PostFilter(FilterSet):
    title = StringFilter(lookups=["icontains"])
    views = NumberFilter(type_=int, lookups=["gt"])
    author__org__country__code = StringFilter(lookups=["in", "exact"])

    class Meta:
        model = _FsPost
        allowed_relationships: ClassVar = ["author", "org", "country"]
        max_relationship_depth: ClassVar = 3


def test_filterset_e2e_two_level_relationship_path_sqlite() -> None:
    """Verify depth-2 relationship traversal against an in-memory SQLite engine.

    Uses inline models so the test can express the full ``post →
    author → org → country`` chain without depending on the shared
    integration fixture topology, which only goes one hop deep.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as OrmSession

    engine = create_engine("sqlite:///:memory:")
    _FsBase.metadata.create_all(engine)

    with OrmSession(engine) as session:
        usa = _FsCountry(id=1, code="US")
        uk = _FsCountry(id=2, code="UK")
        de = _FsCountry(id=3, code="DE")
        org_a = _FsOrg(id=1, name="A", country=usa)
        org_b = _FsOrg(id=2, name="B", country=uk)
        org_c = _FsOrg(id=3, name="C", country=de)
        author_x = _FsAuthor(id=1, name="X", org=org_a)
        author_y = _FsAuthor(id=2, name="Y", org=org_b)
        author_z = _FsAuthor(id=3, name="Z", org=org_c)
        post_1 = _FsPost(id=1, title="hello", views=10, author=author_x)
        post_2 = _FsPost(id=2, title="world", views=20, author=author_y)
        post_3 = _FsPost(id=3, title="foo", views=30, author=author_z)
        session.add_all([usa, uk, de, org_a, org_b, org_c, author_x, author_y, author_z, post_1, post_2, post_3])
        session.commit()

        instance = _PostFilter.from_query_params(
            {"author__org__country__code__in": "US,UK", "views__gt": "0"},
        )
        statement_filters = instance.to_filters()
        assert len(statement_filters) == 2

        stmt = select(_FsPost)
        for sf in statement_filters:
            stmt = sf.append_to_statement(stmt, _FsPost)

        rows = session.execute(stmt).scalars().all()
        assert {p.title for p in rows} == {"hello", "world"}

        nested = next(sf for sf in statement_filters if isinstance(sf, RelationshipFilter))
        assert nested.relationship == "author"
        org_layer = nested.filters[0]
        assert isinstance(org_layer, RelationshipFilter)
        assert org_layer.relationship == "org"
        country_layer = org_layer.filters[0]
        assert isinstance(country_layer, RelationshipFilter)
        assert country_layer.relationship == "country"

    _FsBase.metadata.drop_all(engine)


def test_filterset_e2e_two_level_relationship_emits_single_select_sqlite() -> None:
    """A depth-2 traversal must still compile to one ``SELECT``.

    Companion to the depth-1 assertion in
    ``test_filterset_emits_single_select_sync``. Confirms nested
    ``RelationshipFilter`` wrapping does not introduce extra round trips.
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session as OrmSession

    engine = create_engine("sqlite:///:memory:")
    _FsBase.metadata.create_all(engine)

    try:
        with OrmSession(engine) as session:
            usa = _FsCountry(id=1, code="US")
            org = _FsOrg(id=1, name="A", country=usa)
            author = _FsAuthor(id=1, name="X", org=org)
            session.add_all(
                [usa, org, author, _FsPost(id=1, title="hello", views=10, author=author)],
            )
            session.commit()

            instance = _PostFilter.from_query_params(
                {"author__org__country__code__in": "US"},
            )
            statement_filters = instance.to_filters()

            stmt = select(_FsPost)
            for sf in statement_filters:
                stmt = sf.append_to_statement(stmt, _FsPost)

            statements: list[str] = []

            def _record_select(_conn: Any, _cursor: Any, sql: str, *_args: Any, **_kwargs: Any) -> None:
                if sql.lstrip().upper().startswith("SELECT"):
                    statements.append(sql)

            event.listen(engine, "before_cursor_execute", _record_select)
            try:
                rows = session.execute(stmt).scalars().all()
            finally:
                event.remove(engine, "before_cursor_execute", _record_select)

            assert {p.title for p in rows} == {"hello"}
            assert len(statements) == 1, statements
    finally:
        _FsBase.metadata.drop_all(engine)


def test_filterset_e2e_unfiltered_yields_full_table_sqlite() -> None:
    """Empty query params → no filters → unfiltered SELECT returns all rows."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as OrmSession

    engine = create_engine("sqlite:///:memory:")
    _FsBase.metadata.create_all(engine)

    with OrmSession(engine) as session:
        country = _FsCountry(id=10, code="US")
        org = _FsOrg(id=10, name="Acme", country=country)
        author = _FsAuthor(id=10, name="A", org=org)
        post = _FsPost(id=10, title="t", views=1, author=author)
        session.add_all([country, org, author, post])
        session.commit()

        instance = _PostFilter.from_query_params({})
        assert instance.to_filters() == []

        stmt = select(_FsPost)
        rows = session.execute(stmt).scalars().all()
        assert len(rows) == 1

    _FsBase.metadata.drop_all(engine)


def test_filterset_e2e_comparison_and_ordering_sqlite() -> None:
    """Verify comparison + ordering compile and execute on a hermetic engine."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as OrmSession

    class _LocalBase(DeclarativeBase):
        pass

    class _Item(_LocalBase):
        __tablename__ = "fs_e2e_item"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(50))
        score: Mapped[int] = mapped_column(Integer)

    class _ItemFilter(FilterSet):
        score = NumberFilter(type_=int, lookups=["gte", "exact"])
        order_by = OrderingFilter(allowed=["score", "name"])

        class Meta:
            model = _Item

    engine = create_engine("sqlite:///:memory:")
    _LocalBase.metadata.create_all(engine)

    with OrmSession(engine) as session:
        session.add_all(
            [
                _Item(id=1, name="alpha", score=5),
                _Item(id=2, name="bravo", score=15),
                _Item(id=3, name="charlie", score=10),
            ],
        )
        session.commit()

        instance = _ItemFilter.from_query_params({"score__gte": "10", "order_by": "-score,name"})
        statement_filters = instance.to_filters()
        assert len(statement_filters) == 2
        assert isinstance(statement_filters[0], ComparisonFilter)
        assert isinstance(statement_filters[-1], OrderingApply)

        stmt = select(_Item)
        for sf in statement_filters:
            stmt = sf.append_to_statement(stmt, _Item)

        rows = session.execute(stmt).scalars().all()
        assert [r.name for r in rows] == ["bravo", "charlie"]

    _LocalBase.metadata.drop_all(engine)

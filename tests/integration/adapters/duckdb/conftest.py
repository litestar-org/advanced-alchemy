from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generator, cast

import pytest
from sqlalchemy import Engine, NullPool, create_engine, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy import base
from tests.fixtures import types
from tests.helpers import RawRecordData

if TYPE_CHECKING:
    pass


@pytest.fixture(name="engine", scope="session")
def duckdb_engine(
    _patch_bases: Any,
    tmpdir_factory: pytest.TempdirFactory,
) -> Generator[Engine, None, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    tmp_path = tmpdir_factory.mktemp("data")  # pyright: ignore[reportAssignmentType]
    engine = create_engine(f"duckdb:///{tmp_path}/test.duck.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def seed_db(
    engine: Engine,
    raw_authors: RawRecordData,
    raw_slug_books: RawRecordData,
    raw_rules: RawRecordData,
    raw_secrets: RawRecordData,
    author_model: types.AuthorModel,
    rule_model: types.RuleModel,
    secret_model: types.SecretModel,
    slug_book_model: types.SlugBookModel,
) -> None:
    with engine.begin() as conn:
        base.orm_registry.metadata.drop_all(conn)
        base.orm_registry.metadata.create_all(conn)
    with engine.begin() as conn:
        for author in raw_authors:
            conn.execute(insert(author_model).values(author))
        for rule in raw_rules:
            conn.execute(insert(rule_model).values(rule))
        for secret in raw_secrets:
            conn.execute(insert(secret_model).values(secret))
        for book in raw_slug_books:
            conn.execute(insert(slug_book_model).values(book))


@pytest.fixture()
def session(engine: Engine, seed_db: None) -> Generator[Session, None, None]:
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def any_session(session: Session, request: pytest.FixtureRequest) -> Generator[Session, None, None]:
    yield session


@pytest.fixture()
def author_repo(
    request: pytest.FixtureRequest,
    any_session: AsyncSession | Session,
    repository_module: Any,
) -> types.AuthorRepository:
    """Return an AuthorAsyncRepository or AuthorSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.AuthorAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.AuthorSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.AuthorAsyncRepository(session=any_session)
    else:
        repo = repository_module.AuthorSyncRepository(session=any_session)
    return cast(types.AuthorRepository, repo)


@pytest.fixture()
def secret_repo(
    request: pytest.FixtureRequest,
    any_session: AsyncSession | Session,
    repository_module: Any,
) -> types.SecretRepository:
    """Return an SecretAsyncRepository or SecretSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.SecretAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.SecretSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.SecretAsyncRepository(session=any_session)
    else:
        repo = repository_module.SecretSyncRepository(session=any_session)
    return cast(types.SecretRepository, repo)


@pytest.fixture()
def author_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: pytest.FixtureRequest,
) -> types.AuthorService:
    """Return an AuthorAsyncService or AuthorSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.AuthorAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.AuthorSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.AuthorAsyncService(session=any_session)
    else:
        repo = service_module.AuthorSyncService(session=any_session)
    return cast(types.AuthorService, repo)


@pytest.fixture()
def rule_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
    request: pytest.FixtureRequest,
) -> types.RuleRepository:
    """Return an RuleAsyncRepository or RuleSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.RuleAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.RuleSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.RuleAsyncRepository(session=any_session)
    else:
        repo = repository_module.RuleSyncRepository(session=any_session)
    return cast(types.RuleRepository, repo)


@pytest.fixture()
def rule_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: pytest.FixtureRequest,
) -> types.RuleService:
    """Return an RuleAsyncService or RuleSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.RuleAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.RuleSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.RuleAsyncService(session=any_session)
    else:
        repo = service_module.RuleSyncService(session=any_session)
    return cast(types.RuleService, repo)


@pytest.fixture()
def book_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
    request: pytest.FixtureRequest,
) -> types.BookRepository:
    """Return an BookAsyncRepository or BookSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.BookAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.BookSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.BookAsyncRepository(session=any_session)
    else:
        repo = repository_module.BookSyncRepository(session=any_session)
    return cast(types.BookRepository, repo)


@pytest.fixture()
def book_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: pytest.FixtureRequest,
) -> types.BookService:
    """Return an BookAsyncService or BookSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.BookAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.BookSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.BookAsyncService(session=any_session)
    else:
        repo = service_module.BookSyncService(session=any_session)
    return cast(types.BookService, repo)


@pytest.fixture()
def slug_book_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
    request: pytest.FixtureRequest,
) -> types.SlugBookRepository:
    """Return an SlugBookAsyncRepository or SlugBookSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.SlugBookAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.SlugBookSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.SlugBookAsyncRepository(session=any_session)
    else:
        repo = repository_module.SlugBookSyncRepository(session=any_session)
    return cast("types.SlugBookRepository", repo)


@pytest.fixture()
def slug_book_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: pytest.FixtureRequest,
) -> types.SlugBookService:
    """Return an SlugBookAsyncService or SlugBookSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        svc = service_module.SlugBookAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        svc = service_module.SlugBookSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        svc = service_module.SlugBookAsyncService(session=any_session)
    else:
        svc = service_module.SlugBookSyncService(session=any_session)
    return cast("types.SlugBookService", svc)


@pytest.fixture()
def tag_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
    request: pytest.FixtureRequest,
) -> types.ItemRepository:
    """Return an TagAsyncRepository or TagSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.TagAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.TagSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.TagAsyncRepository(session=any_session)
    else:
        repo = repository_module.TagSyncRepository(session=any_session)

    return cast(types.ItemRepository, repo)


@pytest.fixture()
def tag_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: pytest.FixtureRequest,
) -> types.TagService:
    """Return an TagAsyncService or TagSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.TagAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.TagSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.TagAsyncService(session=any_session)
    else:
        repo = service_module.TagSyncService(session=any_session)
    return cast(types.TagService, repo)


@pytest.fixture()
def item_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
    request: pytest.FixtureRequest,
) -> types.ItemRepository:
    """Return an ItemAsyncRepository or ItemSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.ItemAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.ItemSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.ItemAsyncRepository(session=any_session)
    else:
        repo = repository_module.ItemSyncRepository(session=any_session)

    return cast(types.ItemRepository, repo)


@pytest.fixture()
def item_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: pytest.FixtureRequest,
) -> types.ItemService:
    """Return an ItemAsyncService or ItemSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.ItemAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.ItemSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.ItemAsyncService(session=any_session)
    else:
        repo = service_module.ItemSyncService(session=any_session)
    return cast(types.ItemService, repo)


@pytest.fixture()
def model_with_fetched_value_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
) -> types.ModelWithFetchedValueRepository:
    """Return an ModelWithFetchedValueAsyncRepository or ModelWithFetchedValueSyncRepository
    based on the current PK and session type
    """
    if isinstance(any_session, AsyncSession):
        repo = repository_module.ModelWithFetchedValueAsyncRepository(session=any_session)
    else:
        repo = repository_module.ModelWithFetchedValueSyncRepository(session=any_session)
    return cast(types.ModelWithFetchedValueRepository, repo)

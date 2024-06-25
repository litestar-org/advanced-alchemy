"""Unit tests for the SQLAlchemy Repository implementation."""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Generator, Iterator, List, Literal, Type, Union, cast
from unittest.mock import NonCallableMagicMock
from uuid import UUID, uuid4

import pytest
from msgspec import Struct
from pydantic import BaseModel
from pytest_lazyfixture import lazy_fixture
from sqlalchemy import Engine, Table, and_, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session, sessionmaker
from time_machine import travel

from advanced_alchemy import base
from advanced_alchemy.exceptions import NotFoundError, RepositoryError
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    NotInCollectionFilter,
    NotInSearchFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemyAsyncSlugRepository
from advanced_alchemy.repository._util import get_instrumented_attr, model_from_dict
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemyAsyncMockSlugRepository,
    SQLAlchemySyncMockRepository,
    SQLAlchemySyncMockSlugRepository,
)
from advanced_alchemy.service import (
    SQLAlchemyAsyncRepositoryService,
)
from advanced_alchemy.service.pagination import OffsetPagination
from advanced_alchemy.utils.text import slugify
from tests.fixtures.bigint import models as models_bigint
from tests.fixtures.bigint import repositories as repositories_bigint
from tests.fixtures.bigint import services as services_bigint
from tests.fixtures.uuid import models as models_uuid
from tests.fixtures.uuid import repositories as repositories_uuid
from tests.fixtures.uuid import services as services_uuid
from tests.helpers import maybe_async
from tests.integration.helpers import update_raw_records

if TYPE_CHECKING:
    from pytest import FixtureRequest
    from time_machine import Coordinates

pytestmark = [
    pytest.mark.integration,
]
xfail = pytest.mark.xfail


RepositoryPKType = Literal["uuid", "bigint"]
SecretModel = Type[Union[models_uuid.UUIDSecret, models_bigint.BigIntSecret]]
AuthorModel = Type[Union[models_uuid.UUIDAuthor, models_bigint.BigIntAuthor]]
RuleModel = Type[Union[models_uuid.UUIDRule, models_bigint.BigIntRule]]
ModelWithFetchedValue = Type[Union[models_uuid.UUIDModelWithFetchedValue, models_bigint.BigIntModelWithFetchedValue]]
ItemModel = Type[Union[models_uuid.UUIDItem, models_bigint.BigIntItem]]
TagModel = Type[Union[models_uuid.UUIDTag, models_bigint.BigIntTag]]
SlugBookModel = Type[Union[models_uuid.UUIDSlugBook, models_bigint.BigIntSlugBook]]


AnySecret = Union[models_uuid.UUIDSecret, models_bigint.BigIntSecret]
SecretRepository = SQLAlchemyAsyncRepository[AnySecret]
SecretService = SQLAlchemyAsyncRepositoryService[AnySecret]
SecretMockRepository = SQLAlchemyAsyncMockRepository[AnySecret]
AnySecretRepository = Union[SecretRepository, SecretMockRepository]

AnyAuthor = Union[models_uuid.UUIDAuthor, models_bigint.BigIntAuthor]
AuthorRepository = SQLAlchemyAsyncRepository[AnyAuthor]
AuthorMockRepository = SQLAlchemyAsyncMockRepository[AnyAuthor]
AnyAuthorRepository = Union[AuthorRepository, AuthorMockRepository]
AuthorService = SQLAlchemyAsyncRepositoryService[AnyAuthor]

AnyRule = Union[models_uuid.UUIDRule, models_bigint.BigIntRule]
RuleRepository = SQLAlchemyAsyncRepository[AnyRule]
RuleService = SQLAlchemyAsyncRepositoryService[AnyRule]

AnySlugBook = Union[models_uuid.UUIDSlugBook, models_bigint.BigIntSlugBook]
SlugBookRepository = SQLAlchemyAsyncSlugRepository[AnySlugBook]
SlugBookService = SQLAlchemyAsyncRepositoryService[AnySlugBook]


AnyBook = Union[models_uuid.UUIDBook, models_bigint.BigIntBook]
BookRepository = SQLAlchemyAsyncRepository[AnyBook]
BookService = SQLAlchemyAsyncRepositoryService[AnyBook]

AnyTag = Union[models_uuid.UUIDTag, models_bigint.BigIntTag]
TagRepository = SQLAlchemyAsyncRepository[AnyTag]
TagService = SQLAlchemyAsyncRepositoryService[AnyTag]

AnyItem = Union[models_uuid.UUIDItem, models_bigint.BigIntItem]
ItemRepository = SQLAlchemyAsyncRepository[AnyItem]
ItemService = SQLAlchemyAsyncRepositoryService[AnyItem]

AnyModelWithFetchedValue = Union[models_uuid.UUIDModelWithFetchedValue, models_bigint.BigIntModelWithFetchedValue]
ModelWithFetchedValueRepository = SQLAlchemyAsyncRepository[AnyModelWithFetchedValue]
ModelWithFetchedValueService = SQLAlchemyAsyncRepositoryService[AnyModelWithFetchedValue]

RawRecordData = List[Dict[str, Any]]

mock_engines = {"mock_async_engine", "mock_sync_engine"}


@pytest.fixture(autouse=True)
def _clear_in_memory_db() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    try:
        yield
    finally:
        SQLAlchemyAsyncMockRepository.__database_clear__()
        SQLAlchemySyncMockRepository.__database_clear__()


@pytest.fixture(name="raw_authors_uuid")
def fx_raw_authors_uuid() -> RawRecordData:
    """Unstructured author representations."""
    return [
        {
            "id": UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
            "name": "Agatha Christie",
            "dob": "1890-09-15",
            "created_at": "2023-05-01T00:00:00",
            "updated_at": "2023-05-11T00:00:00",
        },
        {
            "id": UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"),
            "name": "Leo Tolstoy",
            "dob": "1828-09-09",
            "created_at": "2023-03-01T00:00:00",
            "updated_at": "2023-05-15T00:00:00",
        },
    ]


@pytest.fixture(name="raw_books_uuid")
def fx_raw_books_uuid(raw_authors_uuid: RawRecordData) -> RawRecordData:
    """Unstructured book representations."""
    return [
        {
            "id": UUID("f34545b9-663c-4fce-915d-dd1ae9cea42a"),
            "title": "Murder on the Orient Express",
            "author_id": raw_authors_uuid[0]["id"],
            "author": raw_authors_uuid[0],
        },
    ]


@pytest.fixture(name="raw_slug_books_uuid")
def fx_raw_slug_books_uuid(raw_authors_uuid: RawRecordData) -> RawRecordData:
    """Unstructured slug book representations."""
    return [
        {
            "id": UUID("f34545b9-663c-4fce-915d-dd1ae9cea42a"),
            "title": "Murder on the Orient Express",
            "slug": slugify("Murder on the Orient Express"),
            "author_id": str(raw_authors_uuid[0]["id"]),
        },
    ]


@pytest.fixture(name="raw_log_events_uuid")
def fx_raw_log_events_uuid() -> RawRecordData:
    """Unstructured log events representations."""
    return [
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "logged_at": "0001-01-01T00:00:00",
            "payload": {"foo": "bar", "baz": datetime.now()},
            "created_at": "0001-01-01T00:00:00",
            "updated_at": "0001-01-01T00:00:00",
        },
    ]


@pytest.fixture(name="raw_rules_uuid")
def fx_raw_rules_uuid() -> RawRecordData:
    """Unstructured rules representations."""
    return [
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "name": "Initial loading rule.",
            "config": {"url": "https://example.org", "setting_123": 1},
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-02-01T00:00:00",
        },
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea34b",
            "name": "Secondary loading rule.",
            "config": {"url": "https://example.org", "bar": "foo", "setting_123": 4},
            "created_at": "2023-02-01T00:00:00",
            "updated_at": "2023-02-01T00:00:00",
        },
    ]


@pytest.fixture(name="raw_secrets_uuid")
def fx_raw_secrets_uuid() -> RawRecordData:
    """secret representations."""
    return [
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "secret": "I'm a secret!",
            "long_secret": "It's clobbering time.",
        },
    ]


@pytest.fixture(name="raw_authors_bigint")
def fx_raw_authors_bigint() -> RawRecordData:
    """Unstructured author representations."""
    return [
        {
            "id": 2023,
            "name": "Agatha Christie",
            "dob": "1890-09-15",
            "created_at": "2023-05-01T00:00:00",
            "updated_at": "2023-05-11T00:00:00",
        },
        {
            "id": 2024,
            "name": "Leo Tolstoy",
            "dob": "1828-09-09",
            "created_at": "2023-03-01T00:00:00",
            "updated_at": "2023-05-15T00:00:00",
        },
    ]


@pytest.fixture(name="raw_books_bigint")
def fx_raw_books_bigint(raw_authors_bigint: RawRecordData) -> RawRecordData:
    """Unstructured book representations."""
    return [
        {
            "title": "Murder on the Orient Express",
            "author_id": raw_authors_bigint[0]["id"],
            "author": raw_authors_bigint[0],
        },
    ]


@pytest.fixture(name="raw_slug_books_bigint")
def fx_raw_slug_books_bigint(raw_authors_bigint: RawRecordData) -> RawRecordData:
    """Unstructured slug book representations."""
    return [
        {
            "title": "Murder on the Orient Express",
            "slug": slugify("Murder on the Orient Express"),
            "author_id": str(raw_authors_bigint[0]["id"]),
        },
    ]


@pytest.fixture(name="raw_log_events_bigint")
def fx_raw_log_events_bigint() -> RawRecordData:
    """Unstructured log events representations."""
    return [
        {
            "id": 2025,
            "logged_at": "0001-01-01T00:00:00",
            "payload": {"foo": "bar", "baz": datetime.now()},
            "created_at": "0001-01-01T00:00:00",
            "updated_at": "0001-01-01T00:00:00",
        },
    ]


@pytest.fixture(name="raw_rules_bigint")
def fx_raw_rules_bigint() -> RawRecordData:
    """Unstructured rules representations."""
    return [
        {
            "id": 2025,
            "name": "Initial loading rule.",
            "config": {"url": "https://example.org", "setting_123": 1},
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-02-01T00:00:00",
        },
        {
            "id": 2024,
            "name": "Secondary loading rule.",
            "config": {"url": "https://example.org", "bar": "foo", "setting_123": 4},
            "created_at": "2023-02-01T00:00:00",
            "updated_at": "2023-02-01T00:00:00",
        },
    ]


@pytest.fixture(name="raw_secrets_bigint")
def fx_raw_secrets_bigint() -> RawRecordData:
    """secret representations."""
    return [
        {
            "id": 2025,
            "secret": "I'm a secret!",
            "long_secret": "It's clobbering time.",
        },
    ]


@pytest.fixture(params=["uuid", "bigint"])
def repository_pk_type(request: FixtureRequest) -> RepositoryPKType:
    """Return the primary key type of the repository"""
    return cast(RepositoryPKType, request.param)


@pytest.fixture()
def author_model(repository_pk_type: RepositoryPKType) -> AuthorModel:
    """Return the ``Author`` model matching the current repository PK type"""
    if repository_pk_type == "uuid":
        return models_uuid.UUIDAuthor
    return models_bigint.BigIntAuthor


@pytest.fixture()
def rule_model(repository_pk_type: RepositoryPKType) -> RuleModel:
    """Return the ``Rule`` model matching the current repository PK type"""
    if repository_pk_type == "bigint":
        return models_bigint.BigIntRule
    return models_uuid.UUIDRule


@pytest.fixture()
def model_with_fetched_value(repository_pk_type: RepositoryPKType) -> ModelWithFetchedValue:
    """Return the ``ModelWithFetchedValue`` model matching the current repository PK type"""
    if repository_pk_type == "bigint":
        return models_bigint.BigIntModelWithFetchedValue
    return models_uuid.UUIDModelWithFetchedValue


@pytest.fixture()
def item_model(repository_pk_type: RepositoryPKType) -> ItemModel:
    """Return the ``Item`` model matching the current repository PK type"""
    if repository_pk_type == "bigint":
        return models_bigint.BigIntItem
    return models_uuid.UUIDItem


@pytest.fixture()
def tag_model(repository_pk_type: RepositoryPKType) -> TagModel:
    """Return the ``Tag`` model matching the current repository PK type"""
    if repository_pk_type == "uuid":
        return models_uuid.UUIDTag
    return models_bigint.BigIntTag


@pytest.fixture()
def book_model(repository_pk_type: RepositoryPKType) -> type[models_uuid.UUIDBook | models_bigint.BigIntBook]:
    """Return the ``Book`` model matching the current repository PK type"""
    if repository_pk_type == "uuid":
        return models_uuid.UUIDBook
    return models_bigint.BigIntBook


@pytest.fixture()
def slug_book_model(
    repository_pk_type: RepositoryPKType,
) -> SlugBookModel:
    """Return the ``SlugBook`` model matching the current repository PK type"""
    if repository_pk_type == "uuid":
        return models_uuid.UUIDSlugBook
    return models_bigint.BigIntSlugBook


@pytest.fixture()
def secret_model(repository_pk_type: RepositoryPKType) -> SecretModel:
    """Return the ``Secret`` model matching the current repository PK type"""
    return models_uuid.UUIDSecret if repository_pk_type == "uuid" else models_bigint.BigIntSecret


@pytest.fixture()
def new_pk_id(repository_pk_type: RepositoryPKType) -> Any:
    """Return an unused primary key, matching the current repository PK type"""
    if repository_pk_type == "uuid":
        return UUID("baa0a5c7-5404-4821-bc76-6cf5e73c8219")
    return 10


@pytest.fixture()
def existing_slug_book_ids(raw_slug_books: RawRecordData) -> Iterator[Any]:
    """Return the existing primary keys based on the raw data provided"""
    return (book["id"] for book in raw_slug_books)


@pytest.fixture()
def first_slug_book_id(raw_slug_books: RawRecordData) -> Any:
    """Return the primary key of the first ``Book`` record of the current repository PK type"""
    return raw_slug_books[0]["id"]


@pytest.fixture()
def existing_author_ids(raw_authors: RawRecordData) -> Iterator[Any]:
    """Return the existing primary keys based on the raw data provided"""
    return (author["id"] for author in raw_authors)


@pytest.fixture()
def first_author_id(raw_authors: RawRecordData) -> Any:
    """Return the primary key of the first ``Author`` record of the current repository PK type"""
    return raw_authors[0]["id"]


@pytest.fixture()
def existing_secret_ids(raw_secrets: RawRecordData) -> Iterator[Any]:
    """Return the existing primary keys based on the raw data provided"""
    return (secret["id"] for secret in raw_secrets)


@pytest.fixture()
def first_secret_id(raw_secrets: RawRecordData) -> Any:
    """Return the primary key of the first ``Secret`` record of the current repository PK type"""
    return raw_secrets[0]["id"]


@pytest.fixture(
    params=[
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
            ],
        ),
        pytest.param(
            "duckdb_engine",
            marks=[
                pytest.mark.duckdb,
                pytest.mark.integration,
                pytest.mark.xdist_group("duckdb"),
            ],
        ),
        pytest.param(
            "oracle18c_engine",
            marks=[
                pytest.mark.oracledb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23c_engine",
            marks=[
                pytest.mark.oracledb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle23"),
            ],
        ),
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "spanner_engine",
            marks=[
                pytest.mark.spanner,
                pytest.mark.integration,
                pytest.mark.xdist_group("spanner"),
            ],
        ),
        pytest.param(
            "mssql_engine",
            marks=[
                pytest.mark.mssql_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("mssql"),
            ],
        ),
        pytest.param(
            "cockroachdb_engine",
            marks=[
                pytest.mark.cockroachdb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
        pytest.param(
            "mock_sync_engine",
            marks=[
                pytest.mark.mock_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("mock"),
            ],
        ),
    ],
)
def engine(request: FixtureRequest, repository_pk_type: RepositoryPKType) -> Engine:
    """Return a synchronous engine. Parametrized to return all engines supported by
    the repository PK type
    """
    engine = cast(Engine, request.getfixturevalue(request.param))
    if engine.dialect.name.startswith("spanner") and repository_pk_type == "bigint":
        pytest.skip(reason="Spanner does not support monotonically increasing primary keys")
    elif engine.dialect.name.startswith("cockroach") and repository_pk_type == "bigint":
        pytest.skip(reason="Cockroachdb has special considerations for monotonically increasing primary keys.")
    return engine


@pytest.fixture()
def raw_authors(request: FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Author`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        authors = request.getfixturevalue("raw_authors_bigint")
    else:
        authors = request.getfixturevalue("raw_authors_uuid")
    return cast("RawRecordData", authors)


@pytest.fixture()
def raw_slug_books(request: FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Author`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        books = request.getfixturevalue("raw_slug_books_bigint")
    else:
        books = request.getfixturevalue("raw_slug_books_uuid")
    return cast("RawRecordData", books)


@pytest.fixture()
def raw_rules(request: FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Rule`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        rules = request.getfixturevalue("raw_rules_bigint")
    else:
        rules = request.getfixturevalue("raw_rules_uuid")
    return cast("RawRecordData", rules)


@pytest.fixture()
def raw_secrets(request: FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Secret`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        secrets = request.getfixturevalue("raw_secrets_bigint")
    else:
        secrets = request.getfixturevalue("raw_secrets_uuid")
    return cast("RawRecordData", secrets)


def _seed_db_sync(
    *,
    engine: Engine,
    raw_authors: RawRecordData,
    raw_slug_books: RawRecordData,
    raw_rules: RawRecordData,
    raw_secrets: RawRecordData,
    author_model: AuthorModel,
    secret_model: SecretModel,
    rule_model: RuleModel,
    slug_book_model: SlugBookModel,
) -> None:
    update_raw_records(raw_authors=raw_authors, raw_rules=raw_rules)

    if isinstance(engine, NonCallableMagicMock):
        for raw_author in raw_authors:
            SQLAlchemySyncMockRepository.__database_add__(  # pyright: ignore[reportUnknownMemberType]
                author_model,
                model_from_dict(author_model, **raw_author),  # type: ignore[type-var]
            )
        for raw_rule in raw_rules:
            SQLAlchemySyncMockRepository.__database_add__(  # pyright: ignore[reportUnknownMemberType]
                author_model,
                model_from_dict(rule_model, **raw_rule),  # type: ignore[type-var]
            )
        for raw_secret in raw_secrets:
            SQLAlchemySyncMockRepository.__database_add__(  # pyright: ignore[reportUnknownMemberType]
                secret_model,
                model_from_dict(secret_model, **raw_secret),  # type: ignore[type-var]
            )
        for raw_book in raw_slug_books:
            SQLAlchemySyncMockSlugRepository.__database_add__(  # pyright: ignore[reportUnknownMemberType]
                slug_book_model,
                model_from_dict(slug_book_model, **raw_book),  # type: ignore[type-var]
            )
    else:
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


def _seed_spanner(
    *,
    engine: Engine,
    raw_authors_uuid: RawRecordData,
    raw_rules_uuid: RawRecordData,
    raw_slug_books_uuid: RawRecordData,
) -> list[Table]:
    update_raw_records(raw_authors=raw_authors_uuid, raw_rules=raw_rules_uuid)

    with engine.begin() as txn:
        objs = [
            tbl for tbl in models_uuid.UUIDAuthor.registry.metadata.sorted_tables if tbl.description.startswith("uuid")
        ]
        models_uuid.UUIDAuthor.registry.metadata.create_all(txn, tables=objs)
    return objs


@pytest.fixture()
def seed_db_sync(
    engine: Engine,
    raw_authors: RawRecordData,
    raw_slug_books: RawRecordData,
    raw_rules: RawRecordData,
    raw_secrets: RawRecordData,
    author_model: AuthorModel,
    rule_model: RuleModel,
    secret_model: SecretModel,
    slug_book_model: SlugBookModel,
) -> None:
    if engine.dialect.name.startswith("spanner"):
        _seed_spanner(
            engine=engine,
            raw_authors_uuid=raw_authors,
            raw_rules_uuid=raw_rules,
            raw_slug_books_uuid=raw_slug_books,
        )
    else:
        _seed_db_sync(
            engine=engine,
            raw_authors=raw_authors,
            raw_rules=raw_rules,
            raw_secrets=raw_secrets,
            raw_slug_books=raw_slug_books,
            author_model=author_model,
            rule_model=rule_model,
            secret_model=secret_model,
            slug_book_model=slug_book_model,
        )


@pytest.fixture()
def session(
    engine: Engine,
    raw_authors: RawRecordData,
    raw_rules: RawRecordData,
    raw_secrets: RawRecordData,
    seed_db_sync: None,
) -> Generator[Session, None, None]:
    """Return a synchronous session for the current engine"""
    session = sessionmaker(bind=engine)()

    if engine.dialect.name.startswith("spanner"):
        try:
            author_repo = repositories_uuid.AuthorSyncRepository(session=session)
            for author in raw_authors:
                _ = author_repo.get_or_upsert(match_fields="name", **author)
            secret_repo = repositories_uuid.SecretSyncRepository(session=session)
            for secret in raw_secrets:
                _ = secret_repo.get_or_upsert(match_fields="id", **secret)
            if not bool(os.environ.get("SPANNER_EMULATOR_HOST")):
                rule_repo = repositories_uuid.RuleSyncRepository(session=session)
                for rule in raw_rules:
                    _ = rule_repo.add(models_uuid.UUIDRule(**rule))
            yield session
        finally:
            session.rollback()
            session.close()
        with engine.begin() as txn:
            models_uuid.UUIDAuthor.registry.metadata.drop_all(txn, tables=seed_db_sync)
    else:
        try:
            yield session
        finally:
            session.rollback()
            session.close()


@pytest.fixture(
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
            ],
        ),
        pytest.param(
            "asyncmy_engine",
            marks=[
                pytest.mark.asyncmy,
                pytest.mark.integration,
                pytest.mark.xdist_group("mysql"),
            ],
        ),
        pytest.param(
            "asyncpg_engine",
            marks=[
                pytest.mark.asyncpg,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "psycopg_async_engine",
            marks=[
                pytest.mark.psycopg_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "cockroachdb_async_engine",
            marks=[
                pytest.mark.cockroachdb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
        pytest.param(
            "mssql_async_engine",
            marks=[
                pytest.mark.mssql_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("mssql"),
            ],
        ),
        pytest.param(
            "oracle18c_async_engine",
            marks=[
                pytest.mark.oracledb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23c_async_engine",
            marks=[
                pytest.mark.oracledb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle23"),
            ],
        ),
        pytest.param(
            "mock_async_engine",
            marks=[
                pytest.mark.mock_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("mock"),
            ],
        ),
    ],
)
def async_engine(request: FixtureRequest, repository_pk_type: RepositoryPKType) -> AsyncEngine:
    async_engine = cast(AsyncEngine, request.getfixturevalue(request.param))
    if async_engine.dialect.name.startswith("cockroach") and repository_pk_type == "bigint":
        pytest.skip(reason="Cockroachdb has special considerations for monotonically increasing primary keys.")
    return async_engine


@pytest.fixture()
async def seed_db_async(
    async_engine: AsyncEngine | NonCallableMagicMock,
    raw_authors: RawRecordData,
    raw_rules: RawRecordData,
    raw_secrets: RawRecordData,
    author_model: AuthorModel,
    rule_model: RuleModel,
    secret_model: SecretModel,
) -> None:
    """Return an asynchronous session for the current engine"""
    # convert date/time strings to dt objects.
    for raw_author in raw_authors:
        raw_author["dob"] = datetime.strptime(raw_author["dob"], "%Y-%m-%d").date()
        raw_author["created_at"] = datetime.strptime(raw_author["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            timezone.utc,
        )
        raw_author["updated_at"] = datetime.strptime(raw_author["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            timezone.utc,
        )
    for raw_author in raw_rules:
        raw_author["created_at"] = datetime.strptime(raw_author["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            timezone.utc,
        )
        raw_author["updated_at"] = datetime.strptime(raw_author["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            timezone.utc,
        )

    if isinstance(async_engine, NonCallableMagicMock):
        for raw_author in raw_authors:
            SQLAlchemyAsyncMockRepository.__database_add__(  # pyright: ignore[reportUnknownMemberType]
                author_model,
                model_from_dict(author_model, **raw_author),  # type: ignore[type-var]
            )
        for raw_rule in raw_rules:
            SQLAlchemyAsyncMockRepository.__database_add__(  # pyright: ignore[reportUnknownMemberType]
                author_model,
                model_from_dict(rule_model, **raw_rule),  # type: ignore[type-var]
            )
        for raw_secret in raw_secrets:
            SQLAlchemyAsyncMockRepository.__database_add__(  # pyright: ignore[reportUnknownMemberType]
                secret_model,
                model_from_dict(secret_model, **raw_secret),  # type: ignore[type-var]
            )
    else:
        async with async_engine.begin() as conn:
            await conn.run_sync(base.orm_registry.metadata.drop_all)
            await conn.run_sync(base.orm_registry.metadata.create_all)
            await conn.execute(insert(author_model), raw_authors)
            await conn.execute(insert(rule_model), raw_rules)
            await conn.execute(insert(secret_model), raw_secrets)


@pytest.fixture(params=[lazy_fixture("session"), lazy_fixture("async_session")], ids=["sync", "async"])
def any_session(request: FixtureRequest) -> AsyncSession | Session:
    """Return a session for the current session"""
    if isinstance(request.param, AsyncSession):
        request.getfixturevalue("seed_db_async")
    else:
        request.getfixturevalue("seed_db_sync")
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(params=[lazy_fixture("engine"), lazy_fixture("async_engine")], ids=["sync", "async"])
async def any_engine(
    request: FixtureRequest,
) -> Engine | AsyncEngine:
    """Return a session for the current session"""
    return cast("Engine | AsyncEngine", request.getfixturevalue(request.param))


@pytest.fixture()
def repository_module(repository_pk_type: RepositoryPKType, request: FixtureRequest) -> Any:
    if repository_pk_type == "bigint" and mock_engines.intersection(set(request.fixturenames)):
        pytest.skip("Skipping additional bigint mock repository tests")
    return repositories_uuid if repository_pk_type == "uuid" else repositories_bigint


@pytest.fixture()
def service_module(repository_pk_type: RepositoryPKType, request: FixtureRequest) -> Any:
    if repository_pk_type == "bigint" and mock_engines.intersection(set(request.fixturenames)):
        pytest.skip("Skipping additional bigint mock repository tests")
    return services_uuid if repository_pk_type == "uuid" else services_bigint


@pytest.fixture()
def author_repo(
    request: FixtureRequest,
    any_session: AsyncSession | Session,
    repository_module: Any,
) -> AuthorRepository:
    """Return an AuthorAsyncRepository or AuthorSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.AuthorAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.AuthorSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.AuthorAsyncRepository(session=any_session)
    else:
        repo = repository_module.AuthorSyncRepository(session=any_session)
    return cast(AuthorRepository, repo)


@pytest.fixture()
def secret_repo(
    request: FixtureRequest,
    any_session: AsyncSession | Session,
    repository_module: Any,
) -> SecretRepository:
    """Return an SecretAsyncRepository or SecretSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.SecretAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.SecretSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.SecretAsyncRepository(session=any_session)
    else:
        repo = repository_module.SecretSyncRepository(session=any_session)
    return cast(SecretRepository, repo)


@pytest.fixture()
def author_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: FixtureRequest,
) -> AuthorService:
    """Return an AuthorAsyncService or AuthorSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.AuthorAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.AuthorSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.AuthorAsyncService(session=any_session)
    else:
        repo = service_module.AuthorSyncService(session=any_session)
    return cast(AuthorService, repo)


@pytest.fixture()
def rule_repo(any_session: AsyncSession | Session, repository_module: Any, request: FixtureRequest) -> RuleRepository:
    """Return an RuleAsyncRepository or RuleSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.RuleAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.RuleSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.RuleAsyncRepository(session=any_session)
    else:
        repo = repository_module.RuleSyncRepository(session=any_session)
    return cast(RuleRepository, repo)


@pytest.fixture()
def rule_service(any_session: AsyncSession | Session, service_module: Any, request: FixtureRequest) -> RuleService:
    """Return an RuleAsyncService or RuleSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.RuleAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.RuleSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.RuleAsyncService(session=any_session)
    else:
        repo = service_module.RuleSyncService(session=any_session)
    return cast(RuleService, repo)


@pytest.fixture()
def book_repo(any_session: AsyncSession | Session, repository_module: Any, request: FixtureRequest) -> BookRepository:
    """Return an BookAsyncRepository or BookSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.BookAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.BookSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.BookAsyncRepository(session=any_session)
    else:
        repo = repository_module.BookSyncRepository(session=any_session)
    return cast(BookRepository, repo)


@pytest.fixture()
def book_service(any_session: AsyncSession | Session, service_module: Any, request: FixtureRequest) -> BookService:
    """Return an BookAsyncService or BookSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.BookAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.BookSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.BookAsyncService(session=any_session)
    else:
        repo = service_module.BookSyncService(session=any_session)
    return cast(BookService, repo)


@pytest.fixture()
def slug_book_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
    request: FixtureRequest,
) -> SlugBookRepository:
    """Return an SlugBookAsyncRepository or SlugBookSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.SlugBookAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.SlugBookSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.SlugBookAsyncRepository(session=any_session)
    else:
        repo = repository_module.SlugBookSyncRepository(session=any_session)
    return cast("SlugBookRepository", repo)


@pytest.fixture()
def slug_book_service(
    any_session: AsyncSession | Session,
    service_module: Any,
    request: FixtureRequest,
) -> SlugBookService:
    """Return an SlugBookAsyncService or SlugBookSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        svc = service_module.SlugBookAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        svc = service_module.SlugBookSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        svc = service_module.SlugBookAsyncService(session=any_session)
    else:
        svc = service_module.SlugBookSyncService(session=any_session)
    return cast("SlugBookService", svc)


@pytest.fixture()
def tag_repo(any_session: AsyncSession | Session, repository_module: Any, request: FixtureRequest) -> ItemRepository:
    """Return an TagAsyncRepository or TagSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.TagAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.TagSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.TagAsyncRepository(session=any_session)
    else:
        repo = repository_module.TagSyncRepository(session=any_session)

    return cast(ItemRepository, repo)


@pytest.fixture()
def tag_service(any_session: AsyncSession | Session, service_module: Any, request: FixtureRequest) -> TagService:
    """Return an TagAsyncService or TagSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.TagAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.TagSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.TagAsyncService(session=any_session)
    else:
        repo = service_module.TagSyncService(session=any_session)
    return cast(TagService, repo)


@pytest.fixture()
def item_repo(any_session: AsyncSession | Session, repository_module: Any, request: FixtureRequest) -> ItemRepository:
    """Return an ItemAsyncRepository or ItemSyncRepository based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = repository_module.ItemAsyncMockRepository(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = repository_module.ItemSyncMockRepository(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = repository_module.ItemAsyncRepository(session=any_session)
    else:
        repo = repository_module.ItemSyncRepository(session=any_session)

    return cast(ItemRepository, repo)


@pytest.fixture()
def item_service(any_session: AsyncSession | Session, service_module: Any, request: FixtureRequest) -> ItemService:
    """Return an ItemAsyncService or ItemSyncService based on the current PK and session type"""
    if "mock_async_engine" in request.fixturenames:
        repo = service_module.ItemAsyncMockService(session=any_session)
    elif "mock_sync_engine" in request.fixturenames:
        repo = service_module.ItemSyncMockService(session=any_session)
    elif isinstance(any_session, AsyncSession):
        repo = service_module.ItemAsyncService(session=any_session)
    else:
        repo = service_module.ItemSyncService(session=any_session)
    return cast(ItemService, repo)


@pytest.fixture()
def model_with_fetched_value_repo(
    any_session: AsyncSession | Session,
    repository_module: Any,
) -> ModelWithFetchedValueRepository:
    """Return an ModelWithFetchedValueAsyncRepository or ModelWithFetchedValueSyncRepository
    based on the current PK and session type
    """
    if isinstance(any_session, AsyncSession):
        repo = repository_module.ModelWithFetchedValueAsyncRepository(session=any_session)
    else:
        repo = repository_module.ModelWithFetchedValueSyncRepository(session=any_session)
    return cast(ModelWithFetchedValueRepository, repo)


def test_filter_by_kwargs_with_incorrect_attribute_name(author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy filter by kwargs with invalid column name.

    Args:
        author_repo: The author mock repository
    """
    with pytest.raises(RepositoryError):
        if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
            author_repo.filter_collection_by_kwargs(author_repo.__collection__().list(), whoops="silly me")
        else:
            author_repo.filter_collection_by_kwargs(author_repo.statement, whoops="silly me")


async def test_repo_count_method(author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy count.

    Args:
        author_repo: The author mock repository
    """
    assert await maybe_async(author_repo.count()) == 2


async def test_repo_count_method_with_filters(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy count with filters.

    Args:
        author_repo: The author mock repository
    """
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert (
            await maybe_async(
                author_repo.count(
                    **{author_repo.model_type.name.key: raw_authors[0]["name"]},
                ),
            )
            == 1
        )
    else:
        assert (
            await maybe_async(
                author_repo.count(
                    author_repo.model_type.name == raw_authors[0]["name"],
                ),
            )
            == 1
        )


async def test_repo_list_and_count_method(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_repo: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_repo.list_and_count())
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_repo_list_and_count_method_with_filters(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
) -> None:
    """Test SQLAlchemy list with count and filters in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_repo: The author mock repository
    """
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection, count = await maybe_async(
            author_repo.list_and_count(**{author_repo.model_type.name.key: exp_name}),
        )
    else:
        collection, count = await maybe_async(
            author_repo.list_and_count(author_repo.model_type.name == exp_name),
        )
    assert count == 1
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_repo_list_and_count_basic_method(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy basic list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_repo: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_repo.list_and_count(force_basic_query_mode=True))
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_repo_list_and_count_method_empty(book_repo: BookRepository) -> None:
    collection, count = await maybe_async(book_repo.list_and_count())
    assert count == 0
    assert isinstance(collection, list)
    assert len(collection) == 0


@pytest.fixture()
def frozen_datetime() -> Generator[Coordinates, None, None]:
    with travel(datetime.utcnow, tick=False) as frozen:  # pyright: ignore[reportDeprecated,reportCallIssue]
        yield frozen


async def test_repo_created_updated(
    frozen_datetime: Coordinates,
    author_repo: AnyAuthorRepository,
    book_model: type[AnyBook],
    repository_pk_type: RepositoryPKType,
) -> None:
    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig

    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        pytest.skip(f"{SQLAlchemyAsyncMockRepository.__name__} does not update created/updated columns")
    if isinstance(author_repo, SQLAlchemyAsyncRepository):  # pyright: ignore[reportUnnecessaryIsInstance]
        config = SQLAlchemyAsyncConfig(
            engine_instance=author_repo.session.get_bind(),  # type: ignore[arg-type]
        )
    else:
        config = SQLAlchemySyncConfig(  # type: ignore[unreachable]
            engine_instance=author_repo.session.get_bind(),
        )
    config.__post_init__()
    author = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    original_update_dt = author.updated_at
    assert author.created_at is not None
    assert author.updated_at is not None
    frozen_datetime.shift(delta=timedelta(seconds=5))
    # looks odd, but we want to get correct type checking here
    if repository_pk_type == "uuid":
        author = cast(models_uuid.UUIDAuthor, author)
        book_model = cast("type[models_uuid.UUIDBook]", book_model)
    else:
        author = cast(models_bigint.BigIntAuthor, author)
        book_model = cast("type[models_bigint.BigIntBook]", book_model)
    author.name = "Altered"
    author = await maybe_async(author_repo.update(author))
    assert author.updated_at > original_update_dt
    # test nested
    author.books.append(book_model(title="Testing"))  # type: ignore[arg-type]
    author = await maybe_async(author_repo.update(author))
    assert author.updated_at > original_update_dt


# This test does not work when run in group for some reason.
# If you run individually, it'll pass.
@xfail
async def test_repo_created_updated_no_listener(
    frozen_datetime: Coordinates,
    author_repo: AuthorRepository,
    book_model: type[AnyBook],
    repository_pk_type: RepositoryPKType,
) -> None:
    from sqlalchemy import event
    from sqlalchemy.exc import InvalidRequestError

    from advanced_alchemy._listeners import touch_updated_timestamp
    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig

    with contextlib.suppress(InvalidRequestError):
        event.remove(Session, "before_flush", touch_updated_timestamp)

    if isinstance(author_repo, SQLAlchemyAsyncRepository):  # pyright: ignore[reportUnnecessaryIsInstance]
        config = SQLAlchemyAsyncConfig(
            enable_touch_updated_timestamp_listener=False,
            engine_instance=author_repo.session.get_bind(),  # type: ignore[arg-type]
        )
    else:
        config = SQLAlchemySyncConfig(  # type: ignore[unreachable]
            enable_touch_updated_timestamp_listener=False,
            engine_instance=author_repo.session.get_bind(),
        )
    config.__post_init__()
    author = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    original_update_dt = author.updated_at
    assert author.created_at is not None
    assert author.updated_at is not None
    frozen_datetime.shift(delta=timedelta(seconds=5))
    # looks odd, but we want to get correct type checking here
    if repository_pk_type == "uuid":
        author = cast(models_uuid.UUIDAuthor, author)
        book_model = cast("type[models_uuid.UUIDBook]", book_model)
    else:
        author = cast(models_bigint.BigIntAuthor, author)
        book_model = cast("type[models_bigint.BigIntBook]", book_model)
    author.books.append(book_model(title="Testing"))  # type: ignore[arg-type]
    author = await maybe_async(author_repo.update(author))
    assert author.updated_at == original_update_dt


async def test_repo_list_method(
    raw_authors_uuid: RawRecordData,
    author_repo: AnyAuthorRepository,
) -> None:
    exp_count = len(raw_authors_uuid)
    collection = await maybe_async(author_repo.list())
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_repo_list_method_with_filters(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection = await maybe_async(
            author_repo.list(**{author_repo.model_type.id.key: exp_id, author_repo.model_type.name.key: exp_name}),  # type: ignore[union-attr]
        )
    else:
        collection = await maybe_async(
            author_repo.list(
                and_(author_repo.model_type.id == exp_id, author_repo.model_type.name == exp_name),
            ),
        )
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_repo_add_method(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 1
    new_author = author_model(name="Testing", dob=datetime.now().date())
    obj = await maybe_async(author_repo.add(new_author))
    count = await maybe_async(author_repo.count())
    assert exp_count == count
    assert isinstance(obj, author_model)
    assert new_author.name == obj.name
    assert obj.id is not None


async def test_repo_add_many_method(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 2
    objs = await maybe_async(
        author_repo.add_many(
            [
                author_model(name="Testing 2", dob=datetime.now().date()),
                author_model(name="Cody", dob=datetime.now().date()),
            ],
        ),
    )
    count = await maybe_async(author_repo.count())
    assert exp_count == count
    assert isinstance(objs, list)
    assert len(objs) == 2
    for obj in objs:
        assert obj.id is not None
        assert obj.name in {"Testing 2", "Cody"}


async def test_repo_update_many_method(author_repo: AnyAuthorRepository) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip("Skipped on emulator")

    objs = await maybe_async(author_repo.list())
    for idx, obj in enumerate(objs):
        obj.name = f"Update {idx}"
    objs = await maybe_async(author_repo.update_many(objs))
    for obj in objs:
        assert obj.name.startswith("Update")


async def test_repo_exists_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    exists = await maybe_async(author_repo.exists(id=first_author_id))
    assert exists


async def test_repo_exists_method_with_filters(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
    first_author_id: Any,
) -> None:
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        exists = await maybe_async(
            author_repo.exists(
                **{author_repo.model_type.name.key: raw_authors[0]["name"]},
                id=first_author_id,
            ),
        )
    else:
        exists = await maybe_async(
            author_repo.exists(
                author_repo.model_type.name == raw_authors[0]["name"],
                id=first_author_id,
            ),
        )
    assert exists


async def test_repo_update_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get(first_author_id))
    obj.name = "Updated Name"
    updated_obj = await maybe_async(author_repo.update(obj))
    assert updated_obj.name == obj.name


async def test_repo_delete_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.delete(first_author_id))
    assert str(obj.id) == str(first_author_id)


async def test_repo_delete_many_method(author_repo: AnyAuthorRepository, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="author name %d" % chunk) for chunk in range(2000)]
    _ = await maybe_async(author_repo.add_many(data_to_insert))
    all_objs = await maybe_async(author_repo.list())
    ids_to_delete = [existing_obj.id for existing_obj in all_objs]
    objs = await maybe_async(author_repo.delete_many(ids_to_delete))
    await maybe_async(author_repo.session.commit())
    assert len(objs) > 0
    data, count = await maybe_async(author_repo.list_and_count())
    assert data == []
    assert count == 0


async def test_repo_get_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get(first_author_id))
    assert obj.name == "Agatha Christie"


async def test_repo_get_one_or_none_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get_one_or_none(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    none_obj = await maybe_async(author_repo.get_one_or_none(name="I don't exist"))
    assert none_obj is None


async def test_repo_get_one_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get_one(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    with pytest.raises(RepositoryError):
        _ = await author_repo.get_one(name="I don't exist")


async def test_repo_get_or_upsert_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    existing_obj, existing_created = await maybe_async(author_repo.get_or_upsert(name="Agatha Christie"))
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_created is False
    new_obj, new_created = await maybe_async(author_repo.get_or_upsert(name="New Author"))
    assert new_obj.id is not None
    assert new_obj.name == "New Author"
    assert new_created


async def test_repo_get_or_upsert_match_filter(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    now = datetime.now()
    existing_obj, existing_created = await maybe_async(
        author_repo.get_or_upsert(match_fields="name", name="Agatha Christie", dob=now.date()),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_obj.dob == now.date()
    assert existing_created is False


async def test_repo_get_or_upsert_match_filter_no_upsert(
    author_repo: AnyAuthorRepository,
    first_author_id: Any,
) -> None:
    now = datetime.now()
    existing_obj, existing_created = await maybe_async(
        author_repo.get_or_upsert(match_fields="name", upsert=False, name="Agatha Christie", dob=now.date()),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_obj.dob != now.date()
    assert existing_created is False


async def test_repo_get_and_update(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    existing_obj, existing_updated = await maybe_async(
        author_repo.get_and_update(name="Agatha Christie"),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_updated is False


async def test_repo_get_and_upsert_match_filter(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    now = datetime.now()
    with pytest.raises(NotFoundError):
        _ = await maybe_async(
            author_repo.get_and_update(match_fields="name", name="Agatha Christie123", dob=now.date()),
        )
    with pytest.raises(NotFoundError):
        _ = await maybe_async(
            author_repo.get_and_update(name="Agatha Christie123"),
        )


async def test_repo_upsert_method(
    author_repo: AnyAuthorRepository,
    first_author_id: Any,
    author_model: AuthorModel,
    new_pk_id: Any,
) -> None:
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_obj = await maybe_async(author_repo.upsert(existing_obj))
    assert str(upsert_update_obj.id) == str(first_author_id)
    assert upsert_update_obj.name == "Agatha C."

    upsert_insert_obj = await maybe_async(author_repo.upsert(author_model(name="An Author")))
    assert upsert_insert_obj.id is not None
    assert upsert_insert_obj.name == "An Author"

    # ensures that it still works even if the ID is added before insert
    upsert2_insert_obj = await maybe_async(author_repo.upsert(author_model(id=new_pk_id, name="Another Author")))
    assert upsert2_insert_obj.id is not None
    assert upsert2_insert_obj.name == "Another Author"
    _ = await maybe_async(author_repo.get_one(name="Leo Tolstoy"))
    # ensures that it still works even if the ID isn't set on an existing key
    new_dob = datetime.strptime("2028-09-09", "%Y-%m-%d").date()
    upsert3_update_obj = await maybe_async(
        author_repo.upsert(
            author_model(name="Leo Tolstoy", dob=new_dob),
            match_fields=["name"],
        ),
    )
    if not isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert upsert3_update_obj.id in {UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"), 2024}
    assert upsert3_update_obj.name == "Leo Tolstoy"
    assert upsert3_update_obj.dob == new_dob


async def test_repo_upsert_many_method(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_repo.upsert_many(
            [
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
        ),
    )
    assert len(upsert_update_objs) == 3
    assert upsert_update_objs[0].id is not None
    assert upsert_update_objs[0].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[1].id is not None
    assert upsert_update_objs[1].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[2].id is not None
    assert upsert_update_objs[2].name in ("Agatha C.", "Inserted Author", "Custom Author")


async def test_repo_upsert_many_method_match(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_repo.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["id"],
        ),
    )
    assert len(upsert_update_objs) == 3


async def test_repo_upsert_many_method_match_non_id(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_count = await maybe_async(author_repo.count())
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    _ = await maybe_async(
        author_repo.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["name"],
        ),
    )
    existing_count_now = await maybe_async(author_repo.count())

    assert existing_count_now > existing_count


async def test_repo_upsert_many_method_match_not_on_input(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_count = await maybe_async(author_repo.count())
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    _ = await maybe_async(
        author_repo.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["id"],
        ),
    )
    existing_count_now = await maybe_async(author_repo.count())

    assert existing_count_now > existing_count


async def test_repo_filter_before_after(author_repo: AnyAuthorRepository) -> None:
    before_filter = BeforeAfter(
        field_name="created_at",
        before=datetime.strptime("2023-05-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        after=None,
    )
    existing_obj = await maybe_async(author_repo.list(before_filter))
    assert existing_obj[0].name == "Leo Tolstoy"

    after_filter = BeforeAfter(
        field_name="created_at",
        after=datetime.strptime("2023-03-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        before=None,
    )
    existing_obj = await maybe_async(author_repo.list(after_filter))
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_on_before_after(author_repo: AnyAuthorRepository) -> None:
    before_filter = OnBeforeAfter(
        field_name="created_at",
        on_or_before=datetime.strptime("2023-05-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        on_or_after=None,
    )
    existing_obj = await maybe_async(
        author_repo.list(*[before_filter, OrderBy(field_name="created_at", sort_order="desc")]),  # type: ignore
    )
    assert existing_obj[0].name == "Agatha Christie"

    after_filter = OnBeforeAfter(
        field_name="created_at",
        on_or_after=datetime.strptime("2023-03-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        on_or_before=None,
    )
    existing_obj = await maybe_async(
        author_repo.list(*[after_filter, OrderBy(field_name="created_at", sort_order="desc")]),  # type: ignore
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_search(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(author_repo.list(SearchFilter(field_name="name", value="gath", ignore_case=False)))
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(author_repo.list(SearchFilter(field_name="name", value="GATH", ignore_case=False)))
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 0
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(author_repo.list(SearchFilter(field_name="name", value="GATH", ignore_case=True)))
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_search_multi_field(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(
        author_repo.list(SearchFilter(field_name={"name", "string_field"}, value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(
        author_repo.list(SearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 0
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_repo.list(SearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_not_in_search(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name="name", value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name="name", value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 2
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_not_in_search_multi_field(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 2
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_order_by(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(author_repo.list(OrderBy(field_name="created_at", sort_order="desc")))
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(author_repo.list(OrderBy(field_name="created_at", sort_order="asc")))
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_collection(
    author_repo: AnyAuthorRepository,
    existing_author_ids: Generator[Any, None, None],
) -> None:
    first_author_id = next(existing_author_ids)
    second_author_id = next(existing_author_ids)
    existing_obj = await maybe_async(author_repo.list(CollectionFilter(field_name="id", values=[first_author_id])))
    assert existing_obj[0].name == "Agatha Christie"

    existing_obj = await maybe_async(author_repo.list(CollectionFilter(field_name="id", values=[second_author_id])))
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_no_obj_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    no_obj = await maybe_async(author_repo.list(CollectionFilter[str](field_name="id", values=[])))
    assert no_obj == []


async def test_repo_filter_null_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    no_obj = await maybe_async(author_repo.list(CollectionFilter[str](field_name="id", values=None)))
    assert len(no_obj) > 0


async def test_repo_filter_not_in_collection(
    author_repo: AnyAuthorRepository,
    existing_author_ids: Generator[Any, None, None],
) -> None:
    first_author_id = next(existing_author_ids)
    second_author_id = next(existing_author_ids)
    existing_obj = await maybe_async(author_repo.list(NotInCollectionFilter(field_name="id", values=[first_author_id])))
    assert existing_obj[0].name == "Leo Tolstoy"

    existing_obj = await maybe_async(
        author_repo.list(NotInCollectionFilter(field_name="id", values=[second_author_id])),
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_not_in_no_obj_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    existing_obj = await maybe_async(author_repo.list(NotInCollectionFilter[str](field_name="id", values=[])))
    assert len(existing_obj) > 0


async def test_repo_filter_not_in_null_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    existing_obj = await maybe_async(author_repo.list(NotInCollectionFilter[str](field_name="id", values=None)))
    assert len(existing_obj) > 0


async def test_repo_json_methods(
    raw_rules_uuid: RawRecordData,
    rule_repo: RuleRepository,
    rule_service: RuleService,
    rule_model: RuleModel,
) -> None:
    if rule_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip("Skipped on emulator")

    exp_count = len(raw_rules_uuid) + 1
    new_rule = rule_model(name="Testing", config={"an": "object"})
    obj = await maybe_async(rule_repo.add(new_rule))
    count = await maybe_async(rule_repo.count())
    assert exp_count == count
    assert isinstance(obj, rule_model)
    assert new_rule.name == obj.name
    assert new_rule.config == obj.config  # pyright: ignore
    assert obj.id is not None
    obj.config = {"the": "update"}
    updated = await maybe_async(rule_repo.update(obj))
    assert obj.config == updated.config  # pyright: ignore

    get_obj, get_created = await maybe_async(
        rule_repo.get_or_upsert(match_fields=["name"], name="Secondary loading rule.", config={"another": "object"}),
    )
    assert get_created is False
    assert get_obj.id is not None
    assert get_obj.config == {"another": "object"}  # pyright: ignore

    new_obj, new_created = await maybe_async(
        rule_repo.get_or_upsert(match_fields=["name"], name="New rule.", config={"new": "object"}),
    )
    assert new_created is True
    assert new_obj.id is not None
    assert new_obj.config == {"new": "object"}  # pyright: ignore


async def test_repo_fetched_value(
    model_with_fetched_value_repo: ModelWithFetchedValueRepository,
    model_with_fetched_value: ModelWithFetchedValue,
    request: FixtureRequest,
) -> None:
    if any(fixture in request.fixturenames for fixture in ["mock_async_engine", "mock_sync_engine"]):
        pytest.skip(f"{SQLAlchemyAsyncMockRepository.__name__} does not works with fetched values")
    obj = await maybe_async(model_with_fetched_value_repo.add(model_with_fetched_value(val=1)))
    first_time = obj.updated
    assert first_time is not None
    assert obj.val == 1
    await maybe_async(model_with_fetched_value_repo.session.commit())
    await maybe_async(asyncio.sleep(2))
    obj.val = 2
    obj = await maybe_async(model_with_fetched_value_repo.update(obj))
    assert obj.updated is not None
    assert obj.val == 2
    assert obj.updated != first_time


async def test_lazy_load(
    item_repo: ItemRepository,
    tag_repo: TagRepository,
    item_model: ItemModel,
    tag_model: TagModel,
) -> None:
    if getattr(tag_repo, "__collection__", None) is not None:
        pytest.skip("Skipping lazy load testing on Mock repositories.")
    tag_obj = await maybe_async(tag_repo.add(tag_model(name="A new tag")))
    assert tag_obj
    new_items = await maybe_async(
        item_repo.add_many([item_model(name="The first item"), item_model(name="The second item")]),
    )
    await maybe_async(item_repo.session.commit())
    await maybe_async(tag_repo.session.commit())
    assert len(new_items) > 0
    first_item_id = new_items[0].id
    new_items[1].id
    update_data = {
        "name": "A modified Name",
        "tag_names": ["A new tag"],
        "id": first_item_id,
    }
    tags_to_add = await maybe_async(tag_repo.list(CollectionFilter("name", update_data.pop("tag_names", []))))  # type: ignore
    assert len(tags_to_add) > 0  # pyright: ignore
    assert tags_to_add[0].id is not None  # pyright: ignore
    update_data["tags"] = tags_to_add  # type: ignore[assignment]
    updated_obj = await maybe_async(item_repo.update(item_model(**update_data), auto_refresh=False))
    await maybe_async(item_repo.session.commit())
    assert len(updated_obj.tags) > 0
    assert updated_obj.tags[0].name == "A new tag"


async def test_repo_health_check(author_repo: AnyAuthorRepository) -> None:
    healthy = await maybe_async(author_repo.check_health(author_repo.session))
    assert healthy


async def test_repo_custom_statement(author_repo: AnyAuthorRepository, author_service: AuthorService) -> None:
    """Test Repo with custom statement

    Args:
        author_repo: The author mock repository
    """
    service_type = type(author_service)
    new_service = service_type(session=author_repo.session, statement=select(author_repo.model_type))
    assert await maybe_async(new_service.count()) == 2


async def test_repo_encrypted_methods(
    raw_secrets_uuid: RawRecordData,
    secret_repo: SecretRepository,
    raw_secrets: RawRecordData,
    first_secret_id: Any,
    secret_model: SecretModel,
) -> None:
    existing_obj = await maybe_async(secret_repo.get(first_secret_id))
    assert existing_obj.secret == raw_secrets[0]["secret"]
    assert existing_obj.long_secret == raw_secrets[0]["long_secret"]

    exp_count = len(raw_secrets_uuid) + 1
    new_secret = secret_model(secret="hidden data", long_secret="another longer secret")
    obj = await maybe_async(secret_repo.add(new_secret))
    count = await maybe_async(secret_repo.count())
    assert exp_count == count
    assert isinstance(obj, secret_model)
    assert new_secret.secret == obj.secret
    assert new_secret.long_secret == obj.long_secret
    assert obj.id is not None
    obj.secret = "new secret value"
    obj.long_secret = "new long secret value"
    updated = await maybe_async(secret_repo.update(obj))
    assert obj.secret == updated.secret
    assert obj.long_secret == updated.long_secret


# service tests
async def test_service_filter_search(author_service: AuthorService) -> None:
    existing_obj = await maybe_async(
        author_service.list(SearchFilter(field_name="name", value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(
        author_service.list(SearchFilter(field_name="name", value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = (
        author_service.repository.session.bind.dialect.name if author_service.repository.session.bind else "default"
    )
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 0
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_service.list(SearchFilter(field_name="name", value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_service_count_method(author_service: AuthorService) -> None:
    """Test SQLAlchemy count.

    Args:
        author_service: The author mock repository
    """
    assert await maybe_async(author_service.count()) == 2


async def test_service_count_method_with_filters(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy count with filters.

    Args:
        author_service: The author mock repository
    """
    if issubclass(author_service.repository_type, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert (
            await maybe_async(
                author_service.count(
                    **{author_service.repository.model_type.name.key: raw_authors[0]["name"]},
                ),
            )
            == 1
        )
    else:
        assert (
            await maybe_async(
                author_service.count(
                    author_service.repository.model_type.name == raw_authors[0]["name"],
                ),
            )
            == 1
        )


async def test_service_list_and_count_method(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_service.list_and_count())
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_service_list_and_count_method_with_filters(
    raw_authors: RawRecordData,
    author_service: AuthorService,
) -> None:
    """Test SQLAlchemy list with count and filters in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if issubclass(author_service.repository_type, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection, count = await maybe_async(  # pyright: ignore
            author_service.list_and_count(**{author_service.repository.model_type.name.key: exp_name}),  # pyright: ignore
        )
    else:
        collection, count = await maybe_async(
            author_service.list_and_count(author_service.repository.model_type.name == exp_name),
        )
    assert count == 1
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_service_list_and_count_basic_method(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy basic list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_service.list_and_count(force_basic_query_mode=True))
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_service_list_and_count_method_empty(book_service: BookService) -> None:
    collection, count = await maybe_async(book_service.list_and_count())
    assert count == 0
    assert isinstance(collection, list)
    assert len(collection) == 0


async def test_service_list_method(
    raw_authors_uuid: RawRecordData,
    author_service: AuthorService,
) -> None:
    exp_count = len(raw_authors_uuid)
    collection = await maybe_async(author_service.list())
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_service_list_method_with_filters(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if issubclass(author_service.repository_type, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection = await maybe_async(  # pyright: ignore
            author_service.list(
                **{
                    author_service.repository.model_type.id.key: exp_id,  # type: ignore[union-attr]
                    author_service.repository.model_type.name.key: exp_name,
                },
            ),
        )
    else:
        collection = await maybe_async(
            author_service.list(
                and_(
                    author_service.repository.model_type.id == exp_id,
                    author_service.repository.model_type.name == exp_name,
                ),
            ),
        )
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_service_create_method(
    raw_authors: RawRecordData,
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 1
    new_author = author_model(name="Testing", dob=datetime.now().date())
    obj = await maybe_async(author_service.create(new_author))
    count = await maybe_async(author_service.count())
    assert exp_count == count
    assert isinstance(obj, author_model)
    assert new_author.name == obj.name
    assert obj.id is not None


async def test_service_create_many_method(
    raw_authors: RawRecordData,
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 2
    objs = await maybe_async(
        author_service.create_many(
            [
                author_model(name="Testing 2", dob=datetime.now().date()),
                author_model(name="Cody", dob=datetime.now().date()),
            ],
        ),
    )
    count = await maybe_async(author_service.count())
    assert exp_count == count
    assert isinstance(objs, list)
    assert len(objs) == 2
    for obj in objs:
        assert obj.id is not None
        assert obj.name in {"Testing 2", "Cody"}


async def test_service_update_many_method(author_service: AuthorService) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip("Skipped on emulator")

    objs = await maybe_async(author_service.list())
    for idx, obj in enumerate(objs):
        obj.name = f"Update {idx}"
    objs = await maybe_async(author_service.update_many(list(objs)))
    for obj in objs:
        assert obj.name.startswith("Update")


async def test_service_exists_method(author_service: AuthorService, first_author_id: Any) -> None:
    exists = await maybe_async(author_service.exists(id=first_author_id))
    assert exists


async def test_service_update_method_item_id(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    obj.name = "Updated Name2"
    updated_obj = await maybe_async(author_service.update(item_id=first_author_id, data=obj))
    assert updated_obj.name == obj.name


async def test_service_update_method_no_item_id(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    obj.name = "Updated Name2"
    updated_obj = await maybe_async(author_service.update(data=obj))
    assert str(updated_obj.id) == str(first_author_id)
    assert updated_obj.name == obj.name


async def test_service_update_method_data_is_dict(author_service: AuthorService, first_author_id: Any) -> None:
    new_date = datetime.date(datetime.now())
    updated_obj = await maybe_async(
        author_service.update(item_id=first_author_id, data={"dob": new_date}),
    )
    assert updated_obj.dob == new_date
    # ensure the other fields are not affected
    assert updated_obj.name == "Agatha Christie"


async def test_service_update_method_data_is_dict_with_none_value(
    author_service: AuthorService,
    first_author_id: Any,
) -> None:
    updated_obj = await maybe_async(author_service.update(item_id=first_author_id, data={"dob": None}))
    assert cast(Union[date, None], updated_obj.dob) is None
    # ensure the other fields are not affected
    assert updated_obj.name == "Agatha Christie"


async def test_service_update_method_instrumented_attribute(
    author_service: AuthorService,
    first_author_id: Any,
) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    id_attribute = get_instrumented_attr(author_service.repository.model_type, "id")
    obj.name = "Updated Name2"
    updated_obj = await maybe_async(author_service.update(data=obj, id_attribute=id_attribute))
    assert str(updated_obj.id) == str(first_author_id)
    assert updated_obj.name == obj.name


async def test_service_delete_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.delete(first_author_id))
    assert str(obj.id) == str(first_author_id)


async def test_service_delete_many_method(author_service: AuthorService, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="author name %d" % chunk) for chunk in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    all_objs = await maybe_async(author_service.list())
    ids_to_delete = [existing_obj.id for existing_obj in all_objs]
    objs = await maybe_async(author_service.delete_many(ids_to_delete))
    await maybe_async(author_service.repository.session.commit())  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType,reportAttributeAccessIssue]
    assert len(objs) > 0
    data, count = await maybe_async(author_service.list_and_count())
    assert data == []
    assert count == 0


async def test_service_delete_where_method_empty(author_service: AuthorService, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="author name %d" % chunk) for chunk in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    total_count = await maybe_async(author_service.count())
    all_objs = await maybe_async(author_service.delete_where())
    assert len(all_objs) == total_count
    data, count = await maybe_async(author_service.list_and_count())
    assert data == []
    assert count == 0


async def test_service_delete_where_method_filter(author_service: AuthorService, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="delete me") for _ in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    all_objs = await maybe_async(author_service.delete_where(name="delete me"))
    assert len(all_objs) == len(data_to_insert)
    count = await maybe_async(author_service.count())
    assert count == 2


async def test_service_delete_where_method_search_filter(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    data_to_insert = [author_model(name="delete me") for _ in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    all_objs = await maybe_async(author_service.delete_where(NotInSearchFilter(field_name="name", value="delete me")))
    assert len(all_objs) == 2
    count = await maybe_async(author_service.count())
    assert count == len(data_to_insert)


async def test_service_get_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    assert obj.name == "Agatha Christie"


async def test_service_get_one_or_none_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get_one_or_none(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    none_obj = await maybe_async(author_service.get_one_or_none(name="I don't exist"))
    assert none_obj is None


async def test_service_get_one_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get_one(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    with pytest.raises(RepositoryError):
        _ = await author_service.get_one(name="I don't exist")


async def test_service_get_or_upsert_method(author_service: AuthorService, first_author_id: Any) -> None:
    existing_obj, existing_created = await maybe_async(author_service.get_or_upsert(name="Agatha Christie"))
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_created is False
    new_obj, new_created = await maybe_async(author_service.get_or_upsert(name="New Author"))
    assert new_obj.id is not None
    assert new_obj.name == "New Author"
    assert new_created


async def test_service_get_and_update_method(author_service: AuthorService, first_author_id: Any) -> None:
    existing_obj, existing_created = await maybe_async(
        author_service.get_and_update(name="Agatha Christie", match_fields="name"),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_created is False
    with pytest.raises(NotFoundError):
        _ = await maybe_async(author_service.get_and_update(name="New Author"))


async def test_service_upsert_method(
    author_service: AuthorService,
    first_author_id: Any,
    author_model: AuthorModel,
    new_pk_id: Any,
) -> None:
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_obj = await maybe_async(author_service.upsert(item_id=first_author_id, data=existing_obj))
    assert str(upsert_update_obj.id) == str(first_author_id)
    assert upsert_update_obj.name == "Agatha C."

    upsert_insert_obj = await maybe_async(author_service.upsert(data=author_model(name="An Author")))
    assert upsert_insert_obj.id is not None
    assert upsert_insert_obj.name == "An Author"

    # ensures that it still works even if the ID is added before insert
    upsert2_insert_obj = await maybe_async(
        author_service.upsert(author_model(id=new_pk_id, name="Another Author")),
    )
    assert upsert2_insert_obj.id is not None
    assert upsert2_insert_obj.name == "Another Author"


async def test_service_upsert_method_match(
    author_service: AuthorService,
    first_author_id: Any,
    author_model: AuthorModel,
    new_pk_id: Any,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_obj = await maybe_async(
        author_service.upsert(data=existing_obj.to_dict(exclude={"id"}), match_fields=["name"]),
    )
    if not isinstance(author_service.repository, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert str(upsert_update_obj.id) == str(first_author_id)
    assert upsert_update_obj.name == "Agatha C."

    upsert_insert_obj = await maybe_async(
        author_service.upsert(data=author_model(name="An Author"), match_fields=["name"]),
    )
    assert upsert_insert_obj.id is not None
    assert upsert_insert_obj.name == "An Author"

    # ensures that it still works even if the ID is added before insert
    upsert2_insert_obj = await maybe_async(
        author_service.upsert(author_model(id=new_pk_id, name="Another Author"), match_fields=["name"]),
    )
    assert upsert2_insert_obj.id is not None
    assert upsert2_insert_obj.name == "Another Author"


async def test_service_upsert_many_method(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_service.upsert_many(
            [
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
        ),
    )
    assert len(upsert_update_objs) == 3
    assert upsert_update_objs[0].id is not None
    assert upsert_update_objs[0].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[1].id is not None
    assert upsert_update_objs[1].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[2].id is not None
    assert upsert_update_objs[2].name in ("Agatha C.", "Inserted Author", "Custom Author")


async def test_service_upsert_many_method_match_fields_id(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_service.upsert_many(
            [
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["id"],
        ),
    )
    assert len(upsert_update_objs) == 3
    assert upsert_update_objs[0].id is not None
    assert upsert_update_objs[0].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[1].id is not None
    assert upsert_update_objs[1].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[2].id is not None
    assert upsert_update_objs[2].name in ("Agatha C.", "Inserted Author", "Custom Author")


async def test_service_upsert_many_method_match_fields_non_id(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_count = await maybe_async(author_service.count())
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    _ = await maybe_async(
        author_service.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["name"],
        ),
    )
    existing_count_now = await maybe_async(author_service.count())

    assert existing_count_now > existing_count


async def test_service_update_no_pk(author_service: AuthorService) -> None:
    with pytest.raises(RepositoryError):
        _existing_obj = await maybe_async(author_service.update(data={"name": "Agatha Christie"}))


async def test_service_create_method_slug(
    raw_slug_books: RawRecordData,
    slug_book_service: SlugBookService,
    slug_book_model: SlugBookModel,
) -> None:
    new_book = {"title": "a new book!!", "author_id": uuid4().hex}
    obj = await maybe_async(slug_book_service.create(new_book))
    assert isinstance(obj, slug_book_model)
    assert new_book["title"] == obj.title
    assert obj.slug == "a-new-book"
    assert obj.id is not None


async def test_service_create_method_slug_existing(
    raw_slug_books: RawRecordData,
    slug_book_service: SlugBookService,
    slug_book_model: SlugBookModel,
) -> None:
    if isinstance(
        slug_book_service.repository_type,
        (
            SQLAlchemySyncMockSlugRepository,
            SQLAlchemyAsyncMockSlugRepository,
            SQLAlchemyAsyncMockRepository,
            SQLAlchemySyncMockRepository,
        ),
    ):
        pytest.skip("Skipping additional bigint mock repository tests")
    current_count = await maybe_async(slug_book_service.count())
    if current_count == 0:
        _ = await maybe_async(slug_book_service.create_many(raw_slug_books))

    new_book = {"title": "Murder on the Orient Express", "author_id": uuid4().hex}
    obj = await maybe_async(slug_book_service.create(new_book))
    assert isinstance(obj, slug_book_model)
    assert new_book["title"] == obj.title
    assert obj.slug != "murder-on-the-orient-express"
    assert obj.id is not None


async def test_service_create_many_method_slug(
    raw_slug_books: RawRecordData,
    slug_book_service: SlugBookService,
    slug_book_model: SlugBookModel,
) -> None:
    objs = await maybe_async(
        slug_book_service.create_many(
            [
                {"title": " extra!! ", "author_id": uuid4().hex},
                {"title": "punctuated Book!!", "author_id": uuid4().hex},
            ],
        ),
    )
    assert isinstance(objs, list)
    for obj in objs:
        assert obj.id is not None
        assert obj.slug in {"extra", "punctuated-book"}
        assert obj.title in {" extra!! ", "punctuated Book!!"}


class AuthorStruct(Struct):
    name: str


class AuthorBaseModel(BaseModel):
    model_config = {"from_attributes": True}
    name: str


async def test_service_paginated_to_schema(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_service.list_and_count())
    model_dto = author_service.to_schema(data=collection, total=count)
    pydantic_dto = author_service.to_schema(data=collection, total=count, schema_type=AuthorBaseModel)
    msgspec_dto = author_service.to_schema(data=collection, total=count, schema_type=AuthorStruct)
    assert exp_count == count
    assert isinstance(model_dto, OffsetPagination)
    assert isinstance(model_dto.items[0].name, str)
    assert model_dto.total == exp_count
    assert isinstance(pydantic_dto, OffsetPagination)
    assert isinstance(pydantic_dto.items[0].name, str)  # pyright: ignore
    assert pydantic_dto.total == exp_count
    assert isinstance(msgspec_dto, OffsetPagination)
    assert isinstance(msgspec_dto.items[0].name, str)  # pyright: ignore
    assert msgspec_dto.total == exp_count


async def test_service_to_schema(
    author_service: AuthorService,
    first_author_id: Any,
) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    obj = await maybe_async(author_service.get(first_author_id))
    model_dto = author_service.to_schema(data=obj)
    pydantic_dto = author_service.to_schema(data=obj, schema_type=AuthorBaseModel)
    msgspec_dto = author_service.to_schema(data=obj, schema_type=AuthorStruct)
    assert issubclass(AuthorStruct, Struct)
    assert issubclass(AuthorBaseModel, BaseModel)
    assert isinstance(model_dto.name, str)
    assert isinstance(pydantic_dto, BaseModel)
    assert isinstance(msgspec_dto, Struct)
    assert isinstance(pydantic_dto.name, str)  # pyright: ignore
    assert isinstance(msgspec_dto.name, str)  # pyright: ignore

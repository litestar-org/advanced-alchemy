from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator, cast
from uuid import UUID

import pytest

from tests.fixtures.bigint import models as models_bigint
from tests.fixtures.bigint import repositories as repositories_bigint
from tests.fixtures.bigint import services as services_bigint
from tests.fixtures.types import (
    AuthorModel,
    ItemModel,
    ModelWithFetchedValue,
    RawRecordData,
    RepositoryPKType,
    RuleModel,
    SecretModel,
    SlugBookModel,
    TagModel,
)
from tests.fixtures.uuid import models as models_uuid
from tests.fixtures.uuid import repositories as repositories_uuid
from tests.fixtures.uuid import services as services_uuid

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture(scope="session")
def _patch_bases(monkeysession: MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Ensure new registry state for every test.

    This prevents errors such as "Table '...' is already defined for
    this MetaData instance...
    """
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base

    class NewUUIDBase(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDAuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv6Base(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv6AuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv7Base(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv7AuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewBigIntBase(base.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewBigIntAuditBase(base.BigIntPrimaryKey, base.CommonTableAttributes, base.AuditColumns, DeclarativeBase): ...

    monkeysession.setattr(base, "UUIDBase", NewUUIDBase)
    monkeysession.setattr(base, "UUIDAuditBase", NewUUIDAuditBase)
    monkeysession.setattr(base, "UUIDv6Base", NewUUIDv6Base)
    monkeysession.setattr(base, "UUIDv6AuditBase", NewUUIDv6AuditBase)
    monkeysession.setattr(base, "UUIDv7Base", NewUUIDv7Base)
    monkeysession.setattr(base, "UUIDv7AuditBase", NewUUIDv7AuditBase)
    monkeysession.setattr(base, "BigIntBase", NewBigIntBase)
    monkeysession.setattr(base, "BigIntAuditBase", NewBigIntAuditBase)


@pytest.fixture(params=["uuid", "bigint"], scope="session")
def repository_pk_type(request: pytest.FixtureRequest) -> RepositoryPKType:
    """Return the primary key type of the repository"""
    return cast(RepositoryPKType, request.param)


@pytest.fixture()
def repository_module(repository_pk_type: RepositoryPKType, request: pytest.FixtureRequest) -> Any:
    return repositories_uuid if repository_pk_type == "uuid" else repositories_bigint


@pytest.fixture()
def service_module(repository_pk_type: RepositoryPKType, request: pytest.FixtureRequest) -> Any:
    return services_uuid if repository_pk_type == "uuid" else services_bigint


@pytest.fixture(scope="session")
def raw_authors(request: pytest.FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Author`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        authors = request.getfixturevalue("raw_authors_bigint")
    else:
        authors = request.getfixturevalue("raw_authors_uuid")
    return cast("RawRecordData", authors)


@pytest.fixture(scope="session")
def raw_slug_books(request: pytest.FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Author`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        books = request.getfixturevalue("raw_slug_books_bigint")
    else:
        books = request.getfixturevalue("raw_slug_books_uuid")
    return cast("RawRecordData", books)


@pytest.fixture(scope="session")
def raw_rules(request: pytest.FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Rule`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        rules = request.getfixturevalue("raw_rules_bigint")
    else:
        rules = request.getfixturevalue("raw_rules_uuid")
    return cast("RawRecordData", rules)


@pytest.fixture(scope="session")
def raw_secrets(request: pytest.FixtureRequest, repository_pk_type: RepositoryPKType) -> RawRecordData:
    """Return raw ``Secret`` data matching the current PK type"""
    if repository_pk_type == "bigint":
        secrets = request.getfixturevalue("raw_secrets_bigint")
    else:
        secrets = request.getfixturevalue("raw_secrets_uuid")
    return cast("RawRecordData", secrets)


@pytest.fixture(scope="session")
def author_model(repository_pk_type: RepositoryPKType) -> AuthorModel:
    """Return the ``Author`` model matching the current repository PK type"""
    if repository_pk_type == "uuid":
        return models_uuid.UUIDAuthor
    return models_bigint.BigIntAuthor


@pytest.fixture(scope="session")
def rule_model(repository_pk_type: RepositoryPKType) -> RuleModel:
    """Return the ``Rule`` model matching the current repository PK type"""
    if repository_pk_type == "bigint":
        return models_bigint.BigIntRule
    return models_uuid.UUIDRule


@pytest.fixture(scope="session")
def model_with_fetched_value(repository_pk_type: RepositoryPKType) -> ModelWithFetchedValue:
    """Return the ``ModelWithFetchedValue`` model matching the current repository PK type"""
    if repository_pk_type == "bigint":
        return models_bigint.BigIntModelWithFetchedValue
    return models_uuid.UUIDModelWithFetchedValue


@pytest.fixture(scope="session")
def item_model(repository_pk_type: RepositoryPKType) -> ItemModel:
    """Return the ``Item`` model matching the current repository PK type"""
    if repository_pk_type == "bigint":
        return models_bigint.BigIntItem
    return models_uuid.UUIDItem


@pytest.fixture(scope="session")
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

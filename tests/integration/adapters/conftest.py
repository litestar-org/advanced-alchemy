from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterator, cast
from uuid import UUID

import pytest

from advanced_alchemy.utils.text import slugify
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
    pass


@pytest.fixture(params=["uuid", "bigint"], ids=["UUID", "BigInt"])
def repository_pk_type(request: pytest.FixtureRequest) -> RepositoryPKType:
    """Return the primary key type of the repository"""
    return cast(RepositoryPKType, request.param)


@pytest.fixture()
def repository_module(repository_pk_type: RepositoryPKType, request: pytest.FixtureRequest) -> Any:
    return repositories_uuid if repository_pk_type == "uuid" else repositories_bigint


@pytest.fixture()
def service_module(repository_pk_type: RepositoryPKType, request: pytest.FixtureRequest) -> Any:
    return services_uuid if repository_pk_type == "uuid" else services_bigint


# raw data


@pytest.fixture
def raw_authors(repository_pk_type: RepositoryPKType) -> Iterator[RawRecordData]:
    """Unstructured author representations."""
    yield [
        {
            "id": 2023 if repository_pk_type == "bigint" else UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
            "name": "Agatha Christie",
            "dob": datetime.strptime("1890-09-15", "%Y-%m-%d").date(),
            "created_at": datetime.strptime("2023-05-02T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
            "updated_at": datetime.strptime("2023-05-12T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
        },
        {
            "id": 2024 if repository_pk_type == "bigint" else UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"),
            "name": "Leo Tolstoy",
            "dob": datetime.strptime("1828-09-09", "%Y-%m-%d").date(),
            "created_at": datetime.strptime("2023-05-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
            "updated_at": datetime.strptime("2023-05-11T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
        },
    ]


@pytest.fixture
def raw_books(raw_authors: RawRecordData) -> Iterator[RawRecordData]:
    """Unstructured book representations."""
    yield [
        {
            "title": "Murder on the Orient Express",
            "author_id": raw_authors[0]["id"],
            "author": raw_authors[0],
        },
    ]


@pytest.fixture
def raw_slug_books(raw_authors: RawRecordData) -> Iterator[RawRecordData]:
    """Unstructured slug book representations."""
    yield [
        {
            "title": "Murder on the Orient Express",
            "slug": slugify("Murder on the Orient Express"),
            "author_id": str(raw_authors[0]["id"]),
        },
    ]


@pytest.fixture
def raw_log_events(repository_pk_type: RepositoryPKType) -> Iterator[RawRecordData]:
    """Unstructured log events representations."""
    yield [
        {
            "id": 2025 if repository_pk_type == "bigint" else "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "logged_at": "0001-01-01T00:00:00",
            "payload": {"foo": "bar", "baz": datetime.now()},
            "created_at": datetime.strptime("2023-05-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
            "updated_at": datetime.strptime("2023-05-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
        },
    ]


@pytest.fixture
def raw_rules(repository_pk_type: RepositoryPKType) -> Iterator[RawRecordData]:
    """Unstructured rules representations."""
    yield [
        {
            "id": 2025 if repository_pk_type == "bigint" else "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "name": "Initial loading rule.",
            "config": {"url": "https://example.org", "setting_123": 1},
            "created_at": datetime.strptime("2023-02-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
            "updated_at": datetime.strptime("2023-03-11T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
        },
        {
            "id": 2024 if repository_pk_type == "bigint" else "f34545b9-663c-4fce-915d-dd1ae9cea34b",
            "name": "Secondary loading rule.",
            "config": {"url": "https://example.org", "bar": "foo", "setting_123": 4},
            "created_at": datetime.strptime("2023-02-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
            "updated_at": datetime.strptime("2023-02-11T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(
                timezone.utc,
            ),
        },
    ]


@pytest.fixture
def raw_secrets(repository_pk_type: RepositoryPKType) -> Iterator[RawRecordData]:
    """secret representations."""
    yield [
        {
            "id": 2025 if repository_pk_type == "bigint" else "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "secret": "I'm a secret!",
            "long_secret": "It's clobbering time.",
        },
    ]


@pytest.fixture()
def new_pk_id(repository_pk_type: RepositoryPKType) -> Any:
    """Return an unused primary key, matching the current repository PK type"""
    if repository_pk_type == "uuid":
        return UUID("baa0a5c7-5404-4821-bc76-6cf5e73c8219")
    return 10


@pytest.fixture()
def existing_slug_book_ids(raw_slug_books: RawRecordData) -> Iterator[Any]:
    """Return the existing primary keys based on the raw data provided"""
    yield (book["id"] for book in raw_slug_books)


@pytest.fixture()
def first_slug_book_id(raw_slug_books: RawRecordData) -> Any:
    """Return the primary key of the first ``Book`` record of the current repository PK type"""
    return raw_slug_books[0]["id"]


@pytest.fixture()
def existing_author_ids(raw_authors: RawRecordData) -> Iterator[Any]:
    """Return the existing primary keys based on the raw data provided"""
    yield (author["id"] for author in raw_authors)


@pytest.fixture()
def first_author_id(raw_authors: RawRecordData) -> Any:
    """Return the primary key of the first ``Author`` record of the current repository PK type"""
    return raw_authors[0]["id"]


@pytest.fixture()
def existing_secret_ids(raw_secrets: RawRecordData) -> Iterator[Any]:
    """Return the existing primary keys based on the raw data provided"""
    yield (secret["id"] for secret in raw_secrets)


@pytest.fixture()
def first_secret_id(raw_secrets: RawRecordData) -> Any:
    """Return the primary key of the first ``Secret`` record of the current repository PK type"""
    return raw_secrets[0]["id"]


# models


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

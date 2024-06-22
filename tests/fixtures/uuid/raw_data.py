from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from advanced_alchemy.utils.text import slugify
from tests.fixtures.types import RawRecordData


@pytest.fixture(scope="session", name="raw_authors_uuid")
def fx_raw_authors_uuid() -> RawRecordData:
    """Unstructured author representations."""
    return [
        {
            "id": UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
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
            "id": UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"),
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


@pytest.fixture(scope="session", name="raw_books_uuid")
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


@pytest.fixture(scope="session", name="raw_slug_books_uuid")
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


@pytest.fixture(scope="session", name="raw_log_events_uuid")
def fx_raw_log_events_uuid() -> RawRecordData:
    """Unstructured log events representations."""
    return [
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea42a",
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


@pytest.fixture(scope="session", name="raw_rules_uuid")
def fx_raw_rules_uuid() -> RawRecordData:
    """Unstructured rules representations."""
    return [
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea42a",
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
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea34b",
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


@pytest.fixture(scope="session", name="raw_secrets_uuid")
def fx_raw_secrets_uuid() -> RawRecordData:
    """secret representations."""
    return [
        {
            "id": "f34545b9-663c-4fce-915d-dd1ae9cea42a",
            "secret": "I'm a secret!",
            "long_secret": "It's clobbering time.",
        },
    ]

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from advanced_alchemy.utils.text import slugify
from tests.fixtures.types import RawRecordData


@pytest.fixture(scope="session", name="raw_authors_bigint")
def fx_raw_authors_bigint() -> RawRecordData:
    """Unstructured author representations."""
    return [
        {
            "id": 2023,
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
            "id": 2024,
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


@pytest.fixture(scope="session", name="raw_books_bigint")
def fx_raw_books_bigint(raw_authors_bigint: RawRecordData) -> RawRecordData:
    """Unstructured book representations."""
    return [
        {
            "title": "Murder on the Orient Express",
            "author_id": raw_authors_bigint[0]["id"],
            "author": raw_authors_bigint[0],
        },
    ]


@pytest.fixture(scope="session", name="raw_slug_books_bigint")
def fx_raw_slug_books_bigint(raw_authors_bigint: RawRecordData) -> RawRecordData:
    """Unstructured slug book representations."""
    return [
        {
            "title": "Murder on the Orient Express",
            "slug": slugify("Murder on the Orient Express"),
            "author_id": str(raw_authors_bigint[0]["id"]),
        },
    ]


@pytest.fixture(scope="session", name="raw_log_events_bigint")
def fx_raw_log_events_bigint() -> RawRecordData:
    """Unstructured log events representations."""
    return [
        {
            "id": 2025,
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


@pytest.fixture(scope="session", name="raw_rules_bigint")
def fx_raw_rules_bigint() -> RawRecordData:
    """Unstructured rules representations."""
    return [
        {
            "id": 2025,
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
            "id": 2024,
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


@pytest.fixture(scope="session", name="raw_secrets_bigint")
def fx_raw_secrets_bigint() -> RawRecordData:
    """secret representations."""
    return [
        {
            "id": 2025,
            "secret": "I'm a secret!",
            "long_secret": "It's clobbering time.",
        },
    ]

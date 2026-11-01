"""Root pytest configuration and global session fixtures.

Disables Google Cloud Spanner built-in Cloud Monitoring metrics export before
any Spanner client is created. Without GCP credentials its background exporter
thread fails to authenticate and logs errors during interpreter teardown, which
surfaces as 'Failed to export metrics to Cloud Monitoring' / 'I/O operation on
closed file'. The emulator used in integration tests does not need these metrics.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator

import pytest
from pytest import MonkeyPatch

os.environ.setdefault("SPANNER_DISABLE_BUILTIN_METRICS", "true")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options for the test suite."""
    parser.addoption(
        "--use-embedded-postgres",
        action="store_true",
        default=False,
        help="Run PostgreSQL integration tests against embedded PostgreSQL instead of Docker.",
    )


@pytest.fixture(autouse=True, scope="session")
def configure_logging() -> None:
    """Configure logging levels to suppress verbose database output."""
    logging.getLogger().setLevel(logging.WARNING)

    spanner_loggers = (
        "projects.emulator-test-project.instances.emulator-test-instance.databases.emulator-test-database",
        "google.cloud.spanner_v1.session",
        "google.cloud.spanner_v1",
        "google.cloud.spanner",
        "google.cloud.spanner_dbapi",
        "google.cloud.spanner_dbapi.connection",
        "google.cloud.spanner_dbapi.cursor",
        "database_sessions_manager",
    )
    for logger_name in spanner_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def monkeypatch_session() -> Generator[MonkeyPatch, None, None]:
    """Provide a session-scoped monkeypatch instance."""
    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()

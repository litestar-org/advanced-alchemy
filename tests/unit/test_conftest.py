"""Tests for root and integration test harness isolation and fixture generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import cast
from unittest.mock import MagicMock

FORBIDDEN_UNIT_MODULE_PREFIXES: tuple[str, ...] = (
    "pytest_databases.docker",
    "google.cloud.spanner",
    "tests.integration",
)


def run_unit_suite_isolated() -> list[str]:
    """Execute unit tests in a separate process and inspect loaded modules.

    Returns:
        List of loaded module names matching forbidden prefixes.
    """
    python_code = (
        "import json, sys, pytest\n"
        "pytest.main(['tests/unit/test_docs.py', '-q'])\n"
        "loaded = [\n"
        "    name for name in sys.modules\n"
        "    if name.startswith(('pytest_databases.docker', 'google.cloud.spanner', 'tests.integration'))\n"
        "]\n"
        "sys.stdout.write('__MODULES_START__' + json.dumps(loaded) + '__MODULES_END__')\n"
    )
    env = os.environ.copy()
    env["UV_NO_BUILD_ISOLATION"] = "1"
    env["UV_NO_SYNC"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", python_code],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if "__MODULES_START__" not in result.stdout:
        raise RuntimeError(f"Subprocess failed to output module list: {result.stdout}\n{result.stderr}")
    raw_json = result.stdout.split("__MODULES_START__")[1].split("__MODULES_END__")[0]
    return cast("list[str]", json.loads(raw_json))


def test_unit_suite_does_not_import_container_or_spanner_modules() -> None:
    """Ensure running unit tests does not import Docker, Spanner, or integration test modules."""
    loaded_forbidden = run_unit_suite_isolated()
    assert not loaded_forbidden, f"Unit test suite loaded forbidden modules: {loaded_forbidden}"


def test_full_collection_registers_integration_plugins_cleanly() -> None:
    """Ensure test collection across all directories succeeds without plugin registration conflicts."""
    env = os.environ.copy()
    env["UV_NO_BUILD_ISOLATION"] = "1"
    env["UV_NO_SYNC"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--strict-markers", "--collect-only", "-q", "tests", "docs"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, f"Pytest collection failed:\n{result.stdout}\n{result.stderr}"
    assert "Plugin already registered" not in result.stderr
    assert "Plugin already registered" not in result.stdout
    assert "spanner_connection" not in result.stderr


def test_cockroachdb_urls_use_worker_database_and_driver_opts() -> None:
    """Ensure CockroachDB URLs use the service database and format driver options cleanly."""
    from tests.integration.conftest import _build_cockroachdb_url, cockroachdb_asyncpg_url, cockroachdb_psycopg_url

    mock_service = MagicMock()
    mock_service.host = "127.0.0.1"
    mock_service.port = 26257
    mock_service.database = "pytest_databases_1"
    mock_service.driver_opts = {"sslmode": "disable"}

    assert (
        _build_cockroachdb_url("psycopg", mock_service)
        == "cockroachdb+psycopg://root@127.0.0.1:26257/pytest_databases_1?sslmode=disable"
    )
    assert (
        _build_cockroachdb_url("asyncpg", mock_service)
        == "cockroachdb+asyncpg://root@127.0.0.1:26257/pytest_databases_1"
    )
    assert (
        cockroachdb_psycopg_url.__wrapped__(mock_service)
        == "cockroachdb+psycopg://root@127.0.0.1:26257/pytest_databases_1?sslmode=disable"
    )
    assert (
        cockroachdb_asyncpg_url.__wrapped__(mock_service)
        == "cockroachdb+asyncpg://root@127.0.0.1:26257/pytest_databases_1"
    )

    mock_service.driver_opts = {}
    assert (
        _build_cockroachdb_url("psycopg", mock_service)
        == "cockroachdb+psycopg://root@127.0.0.1:26257/pytest_databases_1"
    )
    assert (
        _build_cockroachdb_url("asyncpg", mock_service)
        == "cockroachdb+asyncpg://root@127.0.0.1:26257/pytest_databases_1"
    )


def test_spanner_url_formats_service_identifiers_without_sdk_import() -> None:
    """Ensure spanner_url formats connection string without importing or calling Spanner SDK."""
    from tests.integration.conftest import _build_spanner_url, spanner_url

    mock_service = MagicMock()
    mock_service.project = "test-project"
    mock_service.instance_name = "test-instance"
    mock_service.database_name = "test-db"

    expected_url = "spanner+spanner:///projects/test-project/instances/test-instance/databases/test-db"
    assert _build_spanner_url(mock_service) == expected_url
    assert spanner_url.__wrapped__(mock_service) == expected_url

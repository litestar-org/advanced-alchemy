"""Tests for root and integration test harness isolation and fixture generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

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


def test_use_embedded_postgres_option_and_env_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure _use_embedded_postgres resolves CLI option and environment variables correctly."""
    from tests.integration.conftest import _use_embedded_postgres

    mock_config = MagicMock()
    mock_config.getoption.return_value = False

    monkeypatch.delenv("PYTEST_EMBEDDED_POSTGRES", raising=False)
    assert not _use_embedded_postgres(mock_config)

    mock_config.getoption.return_value = True
    assert _use_embedded_postgres(mock_config)

    mock_config.getoption.return_value = False
    for truthy_val in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv("PYTEST_EMBEDDED_POSTGRES", truthy_val)
        assert _use_embedded_postgres(mock_config)

    for falsy_val in ("0", "false", "no", ""):
        monkeypatch.setenv("PYTEST_EMBEDDED_POSTGRES", falsy_val)
        assert not _use_embedded_postgres(mock_config)


def test_render_postgres_url_handles_empty_and_populated_passwords() -> None:
    """Ensure _render_postgres_url omits password when empty and includes it when set."""
    from tests.integration.conftest import _render_postgres_url

    mock_service = MagicMock()
    mock_service.user = "postgres"
    mock_service.password = ""
    mock_service.host = "127.0.0.1"
    mock_service.port = 5432
    mock_service.database = "test_db"

    assert (
        _render_postgres_url("postgresql+asyncpg", mock_service)
        == "postgresql+asyncpg://postgres@127.0.0.1:5432/test_db"
    )
    assert (
        _render_postgres_url("postgresql+psycopg", mock_service)
        == "postgresql+psycopg://postgres@127.0.0.1:5432/test_db"
    )

    mock_service.password = "super-secret"
    assert (
        _render_postgres_url("postgresql+asyncpg", mock_service)
        == "postgresql+asyncpg://postgres:super-secret@127.0.0.1:5432/test_db"
    )
    assert (
        _render_postgres_url("postgresql+psycopg", mock_service)
        == "postgresql+psycopg://postgres:super-secret@127.0.0.1:5432/test_db"
    )


def test_fast_suite_deselects_all_container_service_fixtures() -> None:
    """Ensure fast suite collection deselects all Docker container service fixtures."""
    fast_exclude_markers = (
        "asyncmy or oracledb_sync or oracledb_async or cockroachdb_sync or "
        "cockroachdb_async or mssql_sync or mssql_async or spanner or rustfs"
    )
    python_code = (
        "import json, sys, pytest\n"
        "from _pytest.config import Config\n"
        "class CollectorPlugin:\n"
        "    def __init__(self):\n"
        "        self.collected = []\n"
        "    def pytest_collection_finish(self, session):\n"
        "        forbidden_fixtures = {\n"
        "            'postgres_service', 'mysql_service', 'oracle_18c_service',\n"
        "            'oracle_23ai_service', 'cockroachdb_service', 'mssql_service',\n"
        "            'spanner_service', 'rustfs_service',\n"
        "        }\n"
        "        leaked = []\n"
        "        for item in session.items:\n"
        "            fixturenames = set(getattr(item, 'fixturenames', []))\n"
        "            found = fixturenames.intersection(forbidden_fixtures)\n"
        "            if found:\n"
        "                leaked.append((item.nodeid, list(found)))\n"
        "        self.collected = leaked\n"
        "plugin = CollectorPlugin()\n"
        f"pytest.main(['--collect-only', '-q', '--use-embedded-postgres', '-m', 'not ({fast_exclude_markers})', 'tests', 'docs'], plugins=[plugin])\n"
        "sys.stdout.write('__FAST_LEAKED_START__' + json.dumps(plugin.collected) + '__FAST_LEAKED_END__')\n"
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
    if "__FAST_LEAKED_START__" not in result.stdout:
        raise RuntimeError(f"Subprocess failed to output fast leaked fixture list: {result.stdout}\n{result.stderr}")
    raw_json = result.stdout.split("__FAST_LEAKED_START__")[1].split("__FAST_LEAKED_END__")[0]
    leaked = cast("list[list[Any]]", json.loads(raw_json))
    assert not leaked, f"Fast suite collection leaked container service fixtures: {leaked}"

"""Tests for root and integration test harness isolation and fixture generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

FORBIDDEN_UNIT_MODULE_PREFIXES: tuple[str, ...] = (
    "pytest_databases.docker.",
    "google.cloud.spanner",
    "tests.integration",
)


def isolated_pytest_env() -> dict[str, str]:
    """Return the environment for a standalone nested pytest process."""
    env = os.environ.copy()
    for name in ("PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID"):
        env.pop(name, None)
    env["PYTEST_DATABASES_NAMESPACE"] = f"harness_{uuid4().hex[:8]}"
    env["UV_NO_BUILD_ISOLATION"] = "1"
    env["UV_NO_SYNC"] = "1"
    return env


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
        "    if name.startswith(('pytest_databases.docker.', 'google.cloud.spanner', 'tests.integration'))\n"
        "]\n"
        "sys.stdout.write('__MODULES_START__' + json.dumps(loaded) + '__MODULES_END__')\n"
    )
    env = isolated_pytest_env()
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
    env = isolated_pytest_env()
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
    env = isolated_pytest_env()
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


def test_integration_items_do_not_combine_multiple_xdist_groups() -> None:
    """Ensure no test under tests/integration carries multiple distinct xdist_group marks."""
    python_code = (
        "import json, sys, pytest\n"
        "class GroupCollectorPlugin:\n"
        "    def __init__(self):\n"
        "        self.multi_groups = []\n"
        "        self.missing_groups = []\n"
        "    def pytest_collection_finish(self, session):\n"
        "        for item in session.items:\n"
        "            if item.get_closest_marker('unit') is not None:\n"
        "                continue\n"
        "            groups = set()\n"
        "            for mark in item.iter_markers('xdist_group'):\n"
        "                val = mark.args[0] if mark.args else mark.kwargs.get('name')\n"
        "                if val:\n"
        "                    groups.add(val)\n"
        "            if len(groups) > 1:\n"
        "                self.multi_groups.append((item.nodeid, sorted(groups)))\n"
        "            elif len(groups) == 0:\n"
        "                self.missing_groups.append(item.nodeid)\n"
        "plugin = GroupCollectorPlugin()\n"
        "pytest.main(['--collect-only', '-q', 'tests/integration'], plugins=[plugin])\n"
        "sys.stdout.write('__GROUPS_START__' + json.dumps({'multi': plugin.multi_groups, 'missing': plugin.missing_groups}) + '__GROUPS_END__')\n"
    )
    env = isolated_pytest_env()
    result = subprocess.run(
        [sys.executable, "-c", python_code],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if "__GROUPS_START__" not in result.stdout:
        raise RuntimeError(f"Subprocess failed to output xdist_group audit: {result.stdout}\n{result.stderr}")
    raw_json = result.stdout.split("__GROUPS_START__")[1].split("__GROUPS_END__")[0]
    data = cast("dict[str, list[Any]]", json.loads(raw_json))
    assert not data["multi"], f"Integration items combined multiple xdist_groups: {data['multi']}"
    assert not data["missing"], f"Integration items missing xdist_group: {data['missing']}"


def test_file_object_rustfs_helpers_use_upstream_service_contract() -> None:
    """Ensure deprecated RustFS bucket and endpoint helpers are removed from test_file_object."""
    import tests.integration.test_file_object as test_file_object

    assert not hasattr(test_file_object, "ensure_rustfs_bucket"), (
        "ensure_rustfs_bucket should be removed in favor of upstream RustfsService contract"
    )
    assert not hasattr(test_file_object, "rustfs_endpoint_url"), (
        "rustfs_endpoint_url should be removed in favor of rustfs_service.endpoint_url"
    )


def test_nested_collection_preserves_parent_container_ownership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A collect-only child cannot act as controller for inherited worker services."""
    service_module = pytest.importorskip(
        "pytest_databases._service", reason="Container ownership requires pytest-databases 0.20"
    )
    if not hasattr(service_module, "derive_session_owner_id"):
        pytest.skip("Container ownership requires pytest-databases 0.20")
    derive_session_owner_id = getattr(service_module, "derive_session_owner_id")

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", "2")
    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", "parent-run")
    monkeypatch.setenv("PYTEST_DATABASES_NAMESPACE", "parent-run")
    parent_owner = derive_session_owner_id(Path.cwd())
    control_file = tmp_path / "ctrl"
    control_file.write_text(parent_owner, encoding="utf-8")
    python_code = (
        "import json, pathlib, sys, pytest\n"
        "from pytest_databases import _service\n"
        "cleaned = []\n"
        "class CleanupProbe:\n"
        "    def pytest_configure(self, config):\n"
        "        _service._cleanup_session_containers = lambda session, ctrl: cleaned.append(ctrl.read_text())\n"
        "code = pytest.main(['--collect-only', '-q', '--basetemp', sys.argv[1], 'tests/unit/test_docs.py'], plugins=[CleanupProbe()])\n"
        "result = {'cleaned': cleaned, 'owner': _service.derive_session_owner_id(pathlib.Path.cwd())}\n"
        "sys.stdout.write('__CLEANUP_START__' + json.dumps(result) + '__CLEANUP_END__')\n"
        "sys.exit(code)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", python_code, str(tmp_path / "child")],
        capture_output=True,
        text=True,
        check=False,
        env=isolated_pytest_env(),
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    data = json.loads(result.stdout.split("__CLEANUP_START__")[1].split("__CLEANUP_END__")[0])
    assert data["cleaned"] == [], f"Child attempted to stop parent-owned services: {data['cleaned']}"
    assert data["owner"] != parent_owner
    assert control_file.read_text(encoding="utf-8") == parent_owner


def test_schema_manager_build_schema_key_isolates_shared_dialect_urls() -> None:
    """Schema cache keys must separate distinct containers sharing a dialect name."""
    from sqlalchemy import create_engine

    from tests.integration.repository_fixtures import SchemaManager

    engine_18c = create_engine("oracle+oracledb://user:secret@127.0.0.1:1521/?service_name=XEPDB1")
    engine_23ai = create_engine("oracle+oracledb://user:secret@127.0.0.1:1522/?service_name=FREEPDB1")
    try:
        key_18c = SchemaManager.build_schema_key("uuid_sync", engine_18c, "gw0")
        key_23ai = SchemaManager.build_schema_key("uuid_sync", engine_23ai, "gw0")
    finally:
        engine_18c.dispose()
        engine_23ai.dispose()

    assert key_18c != key_23ai
    assert "secret" not in key_18c
    assert "secret" not in key_23ai


def test_integration_pytest_configure_ignores_missing_optional_plugins() -> None:
    """Integration plugin loading tolerates UsageError raised by newer pytest on missing optional plugins."""
    from tests.integration.conftest import pytest_configure as integration_pytest_configure

    class FakePluginManager:
        def has_plugin(self, name: str) -> bool:
            return False

        def import_plugin(self, name: str) -> None:
            raise pytest.UsageError(f'Error importing plugin "{name}"')

    config = MagicMock()
    config.pluginmanager = FakePluginManager()

    integration_pytest_configure(config)


def test_root_pytest_collection_modifyitems_syncs_node_id() -> None:
    """Root collection hook synchronizes pytest 9.2 NodeId storage with loadgroup _nodeid suffixes."""
    from _pytest import nodes

    from tests.conftest import pytest_collection_modifyitems

    coerce_node_id: Any = getattr(nodes, "coerce_node_id", None)
    if coerce_node_id is None:
        pytest.skip("Requires pytest 9.2 NodeId")

    class FakeItem:
        def __init__(self, initial: str, raw: str) -> None:
            self._id = coerce_node_id(initial)
            self._nodeid = raw

        @property
        def nodeid(self) -> str:
            return str(self._id)

    item: Any = FakeItem("tests/integration/test_a.py::test_x[pg]", "tests/integration/test_a.py::test_x[pg]@pg_1")
    pytest_collection_modifyitems([item])
    assert item.nodeid == "tests/integration/test_a.py::test_x[pg]@pg_1"

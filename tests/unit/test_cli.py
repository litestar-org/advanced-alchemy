from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from sqlalchemy.ext.asyncio import AsyncEngine

from advanced_alchemy.cli import (
    add_migration_commands,
    discover_config_from_pyproject,
    find_pyproject_toml,
    get_alchemy_group,
    parse_pyproject_config,
    resolve_config_async,
    resolve_config_sync,
)
from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from click import Group

MODULE_PREFIX = "cli_test_config_"


@pytest.fixture
def cli_runner() -> Generator[CliRunner, None, None]:
    """Create a Click CLI test runner."""
    yield CliRunner()


@pytest.fixture
def mock_config() -> Generator[MagicMock, None, None]:
    """Create a mock SQLAlchemy config."""
    config = MagicMock()
    config.bind_key = "default"
    config.alembic_config.script_location = "migrations"
    config.get_engine.return_value = MagicMock(spec=AsyncEngine)
    yield config


@pytest.fixture
def mock_context(mock_config: MagicMock) -> Generator[MagicMock, None, None]:
    """Create a mock Click context."""
    ctx = MagicMock()
    ctx.obj = {"configs": [mock_config]}
    yield ctx


@pytest.fixture
def database_cli(mock_context: MagicMock) -> Generator[Group, None, None]:
    """Create the database CLI group."""
    cli_group = get_alchemy_group()
    cli_group = add_migration_commands()
    cli_group.ctx = mock_context  # pyright: ignore[reportAttributeAccessIssue]
    yield cli_group


@pytest.fixture
def cleanup_test_modules() -> Iterator[None]:
    """Clean up dynamically imported test modules from sys.modules after each test."""
    modules_before = set(sys.modules.keys())
    yield
    modules_after = set(sys.modules.keys())
    test_modules = {m for m in modules_after - modules_before if m.startswith(MODULE_PREFIX)}
    for module in test_modules:
        sys.modules.pop(module, None)


def _create_module(path: Path, content: str) -> str:
    """Write a temporary Python module file and return its importable stem name."""
    module_name = f"{MODULE_PREFIX}{uuid.uuid4().hex}"
    (path / f"{module_name}.py").write_text(content)
    return module_name


def test_show_current_revision(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the show-current-revision command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "show-current-revision"],
        )
        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.current.assert_called_once_with(verbose=False)


@pytest.mark.parametrize(
    "args",
    [
        ["show-current-revision", "--config", "tests.unit.fixtures.configs"],
        ["show-current-revision", "-c", "tests.unit.fixtures.configs"],
        ["-c", "tests.unit.fixtures.configs", "show-current-revision"],
        ["--config", "tests.unit.fixtures:configs", "show-current-revision"],
        ["show-current-revision", "--config", "tests.unit.fixtures:configs"],
        ["upgrade", "--config", "tests.unit.fixtures.configs", "--no-prompt", "head"],
        ["downgrade", "-c", "tests.unit.fixtures.configs", "--no-prompt"],
    ],
)
def test_config_option_before_and_after_subcommand(
    cli_runner: CliRunner,
    database_cli: Group,
    args: list[str],
) -> None:
    """Test that --config / -c works both before and after the subcommand name with dot or colon syntax."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(database_cli, args)
        assert result.exit_code == 0, result.output
        mock_alembic.assert_called_once()


def test_missing_config_option_fails(cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invoking a subcommand without any config source fails with a helpful message."""
    monkeypatch.chdir(tmp_path)
    cli_group = add_migration_commands()
    result = cli_runner.invoke(cli_group, ["show-current-revision"], env={"ALCHEMY_CONFIG": ""})
    assert result.exit_code == 1
    assert "Error: No Advanced Alchemy config found." in result.output
    assert "--config" in result.output
    assert "ALCHEMY_CONFIG" in result.output
    assert "[tool.advanced-alchemy]" in result.output


@pytest.mark.parametrize("no_prompt", [True, False])
def test_downgrade_database(
    cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock, no_prompt: bool
) -> None:
    """Test the downgrade command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        args = ["--config", "tests.unit.fixtures.configs", "downgrade"]
        if no_prompt:
            args.append("--no-prompt")

        result = cli_runner.invoke(database_cli, args)

        if no_prompt:
            assert result.exit_code == 0
            mock_alembic.assert_called_once()
            mock_alembic.return_value.downgrade.assert_called_once_with(revision="-1", sql=False, tag=None)
        else:
            assert result.exit_code == 1
            assert "Are you sure you want to downgrade" in result.output


@pytest.mark.parametrize("no_prompt", [True, False])
def test_upgrade_database(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock, no_prompt: bool) -> None:
    """Test the upgrade command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        args = ["--config", "tests.unit.fixtures.configs", "upgrade", "head"]
        if no_prompt:
            args.append("--no-prompt")

        result = cli_runner.invoke(database_cli, args)

        if no_prompt:
            assert result.exit_code == 0
            mock_alembic.assert_called_once()
            mock_alembic.return_value.upgrade.assert_called_once_with(revision="head", sql=False, tag=None)
        else:
            assert result.exit_code == 1
            assert "Are you sure you want migrate the database" in result.output


def test_init_alembic(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the init command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "init", "--no-prompt", "migrations"],
        )
        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.init.assert_called_once_with(directory="migrations", multidb=False, package=True)


def test_make_migrations(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the make-migrations command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "make-migrations", "--no-prompt", "-m", "test migration"],
        )
        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.revision.assert_called_once()


def test_drop_all(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the drop-all command."""
    result = cli_runner.invoke(database_cli, ["--config", "tests.unit.fixtures.configs", "drop-all", "--no-prompt"])
    assert result.exit_code == 0


def test_dump_data(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock, tmp_path: Path) -> None:
    """Test the dump-data command."""
    result = cli_runner.invoke(
        database_cli,
        ["--config", "tests.unit.fixtures.configs", "dump-data", "--table", "test_table", "--dir", str(tmp_path)],
    )
    assert result.exit_code == 0


def test_stamp(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the stamp command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "stamp", "head"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.stamp.assert_called_once_with(revision="head", sql=False, tag=None, purge=False)


def test_stamp_with_options(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the stamp command with all options."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "stamp", "--sql", "--tag", "v1.0", "--purge", "head"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.stamp.assert_called_once_with(revision="head", sql=True, tag="v1.0", purge=True)


def test_check(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the check command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "check"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.check.assert_called_once()


def test_edit(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the edit command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "edit", "abc123"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.edit.assert_called_once_with(revision="abc123")


def test_ensure_version(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the ensure-version command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "ensure-version"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.ensure_version.assert_called_once_with(sql=False)


def test_heads(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the heads command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "heads", "--verbose", "--resolve-dependencies"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.heads.assert_called_once_with(verbose=True, resolve_dependencies=True)


def test_history(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the history command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            [
                "--config",
                "tests.unit.fixtures.configs",
                "history",
                "--verbose",
                "--rev-range",
                "base:head",
                "--indicate-current",
            ],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.history.assert_called_once_with(
            rev_range="base:head",
            verbose=True,
            indicate_current=True,
        )


def test_merge(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the merge command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "merge", "--no-prompt", "-m", "test merge", "heads"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.merge.assert_called_once_with(
            revisions="heads",
            message="test merge",
            branch_label=None,
            rev_id=None,
        )


def test_show(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the show command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "show", "head"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.show.assert_called_once_with(rev="head")


def test_branches(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the branches command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "branches", "--verbose"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.branches.assert_called_once_with(verbose=True)


def test_list_templates(cli_runner: CliRunner, database_cli: Group, mock_context: MagicMock) -> None:
    """Test the list-templates command."""
    with patch("advanced_alchemy.alembic.commands.AlembicCommands") as mock_alembic:
        result = cli_runner.invoke(
            database_cli,
            ["--config", "tests.unit.fixtures.configs", "list-templates"],
        )

        assert result.exit_code == 0
        mock_alembic.assert_called_once()
        mock_alembic.return_value.list_templates.assert_called_once()


def test_cli_group_creation() -> None:
    """Test that the CLI group is created correctly."""
    cli_group = add_migration_commands()
    assert cli_group.name == "alchemy"
    assert "show-config" in cli_group.commands
    assert "show-current-revision" in cli_group.commands
    assert "upgrade" in cli_group.commands
    assert "downgrade" in cli_group.commands
    assert "init" in cli_group.commands
    assert "make-migrations" in cli_group.commands
    assert "drop-all" in cli_group.commands
    assert "dump-data" in cli_group.commands
    assert "stamp" in cli_group.commands
    assert "check" in cli_group.commands
    assert "edit" in cli_group.commands
    assert "ensure-version" in cli_group.commands
    assert "heads" in cli_group.commands
    assert "history" in cli_group.commands
    assert "merge" in cli_group.commands
    assert "show" in cli_group.commands
    assert "branches" in cli_group.commands
    assert "list-templates" in cli_group.commands


def test_external_config_loading(cli_runner: CliRunner) -> None:
    """Test loading config from external module in current working directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        config_file = temp_path / "external_config.py"
        config_file.write_text("""
from advanced_alchemy.config import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///:memory:",
    bind_key="external",
)
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            cli_group = add_migration_commands()

            result = cli_runner.invoke(cli_group, ["--config", "external_config.config", "show-config"])

            assert result.exit_code == 0
            assert "external" in result.output
            assert "Error loading config" not in result.output

        finally:
            os.chdir(original_cwd)


def test_external_config_loading_multiple_configs(cli_runner: CliRunner) -> None:
    """Test loading multiple configs from external module."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        config_file = temp_path / "multi_config.py"
        config_file.write_text("""
from advanced_alchemy.config import SQLAlchemyAsyncConfig

configs = [
    SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        bind_key="primary",
    ),
    SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        bind_key="secondary",
    ),
]
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            cli_group = add_migration_commands()
            result = cli_runner.invoke(cli_group, ["--config", "multi_config.configs", "show-config"])

            assert result.exit_code == 0
            assert "primary" in result.output
            assert "secondary" in result.output

        finally:
            os.chdir(original_cwd)


def test_external_config_loading_nonexistent_module(cli_runner: CliRunner) -> None:
    """Test appropriate error when external module doesn't exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            cli_group = add_migration_commands()
            result = cli_runner.invoke(cli_group, ["--config", "nonexistent_module.config", "show-current-revision"])

            assert result.exit_code == 1
            assert "Error loading config" in result.output
            assert "No module named 'nonexistent_module'" in result.output

        finally:
            os.chdir(original_cwd)


def test_external_config_loading_nonexistent_attribute(cli_runner: CliRunner) -> None:
    """Test appropriate error when module exists but attribute doesn't."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        config_file = temp_path / "bad_config.py"
        config_file.write_text("""
from advanced_alchemy.config import SQLAlchemyAsyncConfig

some_other_var = "not a config"
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            cli_group = add_migration_commands()
            result = cli_runner.invoke(cli_group, ["--config", "bad_config.missing_attr", "show-current-revision"])

            assert result.exit_code == 1
            assert "Error loading config" in result.output

        finally:
            os.chdir(original_cwd)


def test_sync_callable_config_loading(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Test loading config from a synchronous factory callable via the CLI."""
    module_name = _create_module(
        tmp_path,
        """
from advanced_alchemy.config import SQLAlchemySyncConfig

def get_database_config():
    return SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
        bind_key="sync_callable",
    )
""",
    )
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(
        add_migration_commands(),
        ["--config", f"{module_name}:get_database_config", "--validate-config", "show-config"],
    )
    assert result.exit_code == 0, result.output
    assert "Successfully loaded 1 config(s)" in result.output
    assert "sync_callable" in result.output
    assert "(sync)" in result.output


def test_async_callable_config_loading(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Test loading config from an asynchronous coroutine factory via the CLI."""
    module_name = _create_module(
        tmp_path,
        """
import asyncio
from advanced_alchemy.config import SQLAlchemyAsyncConfig

async def get_database_config():
    await asyncio.sleep(0.001)
    return SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        bind_key="async_callable",
    )
""",
    )
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(
        add_migration_commands(),
        ["show-config", "--config", f"{module_name}:get_database_config", "--validate-config"],
    )
    assert result.exit_code == 0, result.output
    assert "Successfully loaded 1 config(s)" in result.output
    assert "async_callable" in result.output
    assert "(async-capable)" in result.output


async def test_resolve_config_async_function(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test resolve_config_async with both sync and async callables."""
    module_name = _create_module(
        tmp_path,
        """
from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

def get_sync():
    return SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="sync_bind")

async def get_async():
    return [
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", bind_key="async_bind"),
    ]
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sync_cfg = await resolve_config_async(f"{module_name}:get_sync")
    async_cfgs = await resolve_config_async(f"{module_name}.get_async")
    assert not isinstance(sync_cfg, list)
    assert sync_cfg.bind_key == "sync_bind"
    assert isinstance(async_cfgs, list)
    assert len(async_cfgs) == 1
    assert async_cfgs[0].bind_key == "async_bind"


def test_wrapper_object_config_unwrapping(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Test that wrapper objects exposing .config (such as plugins/extensions) unwrap cleanly."""
    module_name = _create_module(
        tmp_path,
        """
from advanced_alchemy.config import SQLAlchemySyncConfig

class PluginWrapper:
    def __init__(self) -> None:
        self.config = [
            SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="wrapped_primary"),
            SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="wrapped_secondary"),
        ]

plugin = PluginWrapper()
""",
    )
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(
        add_migration_commands(),
        ["--config", f"{module_name}:plugin", "--validate-config", "show-config"],
    )
    assert result.exit_code == 0, result.output
    assert "Successfully loaded 2 config(s)" in result.output
    assert "wrapped_primary" in result.output
    assert "wrapped_secondary" in result.output


def test_module_reference_reports_its_config_attributes(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Pointing --config at a module names the module:attribute reference to use."""
    module_name = _create_module(
        tmp_path,
        """
from advanced_alchemy.config import SQLAlchemySyncConfig

database_config = SQLAlchemySyncConfig(
    connection_string="sqlite:///:memory:",
    bind_key="app",
)
""",
    )
    monkeypatch.chdir(tmp_path)
    result = cli_runner.invoke(add_migration_commands(), ["--config", module_name, "show-config"])
    assert result.exit_code == 1
    normalized = " ".join(result.output.split())
    assert "names a module, not a database configuration" in normalized
    assert f"{module_name}:database_config" in normalized


@pytest.mark.parametrize("section_header", ["[tool.advanced-alchemy]", "[tool.advanced_alchemy]", "[tool.alchemy]"])
def test_cli_with_pyproject_sections(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    section_header: str,
) -> None:
    """Test CLI execution with pyproject.toml config across supported tool section names."""
    module_name = _create_module(
        tmp_path,
        """
from advanced_alchemy.config import SQLAlchemySyncConfig

config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="pyproject_db")
""",
    )
    (tmp_path / "pyproject.toml").write_text(f'{section_header}\nconfig = "{module_name}:config"\n')
    monkeypatch.chdir(tmp_path)

    result = cli_runner.invoke(add_migration_commands(), ["--validate-config", "show-config"])
    assert result.exit_code == 0, result.output
    assert "Using config from pyproject.toml" in result.output
    assert "Successfully loaded 1 config(s)" in result.output
    assert "pyproject_db" in result.output


def test_cli_with_env_var_and_precedence(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Test config precedence: CLI --config (root or subcommand) > ALCHEMY_CONFIG > pyproject.toml."""
    module_name = _create_module(
        tmp_path,
        """
from advanced_alchemy.config import SQLAlchemySyncConfig

cli_cfg = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="from_cli")
env_cfg = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="from_env")
toml_cfg = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="from_toml")
""",
    )
    (tmp_path / "pyproject.toml").write_text(f'[tool.advanced-alchemy]\nconfig = "{module_name}:toml_cfg"\n')
    monkeypatch.chdir(tmp_path)
    cli = add_migration_commands()

    env_result = cli_runner.invoke(
        cli,
        ["--validate-config", "show-config"],
        env={"ALCHEMY_CONFIG": f"{module_name}:env_cfg"},
    )
    assert env_result.exit_code == 0, env_result.output
    assert "from_env" in env_result.output
    assert "Using config from pyproject.toml" not in env_result.output

    root_cli_result = cli_runner.invoke(
        cli,
        ["--config", f"{module_name}:cli_cfg", "show-config"],
        env={"ALCHEMY_CONFIG": "nonexistent.module:bad"},
    )
    assert root_cli_result.exit_code == 0, root_cli_result.output
    assert "from_cli" in root_cli_result.output

    sub_cli_result = cli_runner.invoke(
        cli,
        ["show-config", "--config", f"{module_name}:cli_cfg"],
        env={"ALCHEMY_CONFIG": "nonexistent.module:bad"},
    )
    assert sub_cli_result.exit_code == 0, sub_cli_result.output
    assert "from_cli" in sub_cli_result.output


def test_cli_multiple_configs_list_and_bind_key_deduplication(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    """Test pyproject.toml list config paths, comma-separated env var paths, and bind_key deduplication."""
    module_name = _create_module(
        tmp_path,
        """
from pathlib import Path
from advanced_alchemy.config import AlembicSyncConfig, SQLAlchemySyncConfig

cfg_v1 = SQLAlchemySyncConfig(
    connection_string="sqlite:///:memory:",
    bind_key="main",
    alembic_config=AlembicSyncConfig(script_location=Path("migrations_v1")),
)
cfg_v2 = SQLAlchemySyncConfig(
    connection_string="sqlite:///:memory:",
    bind_key="main",
    alembic_config=AlembicSyncConfig(script_location=Path("migrations_v2")),
)
cfg_secondary = SQLAlchemySyncConfig(
    connection_string="sqlite:///:memory:",
    bind_key="analytics",
    alembic_config=AlembicSyncConfig(script_location="migrations_analytics"),
)
""",
    )
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.advanced-alchemy]\nconfig = ["{module_name}:cfg_v1", "{module_name}:cfg_v2", "{module_name}:cfg_secondary"]\n'
    )
    monkeypatch.chdir(tmp_path)

    result = cli_runner.invoke(add_migration_commands(), ["--validate-config", "show-config"])
    assert result.exit_code == 0, result.output
    assert "Successfully loaded 2 config(s)" in result.output
    assert "migrations_v2" in result.output
    assert "migrations_v1" not in result.output
    assert "analytics" in result.output


def test_pyproject_discovery_parent_and_git_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pyproject.toml upward discovery and .git boundary stopping behavior."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    nested = repo_root / "src" / "pkg"
    nested.mkdir(parents=True)

    (tmp_path / "pyproject.toml").write_text('[tool.advanced-alchemy]\nconfig = "outer:config"\n')
    monkeypatch.chdir(nested)
    assert find_pyproject_toml() is None
    assert discover_config_from_pyproject() is None

    (repo_root / "pyproject.toml").write_text('[tool.advanced-alchemy]\nconfig = "inner:config"\n')
    assert find_pyproject_toml() == repo_root / "pyproject.toml"
    assert discover_config_from_pyproject() == "inner:config"


def test_parse_pyproject_config_validation_errors(tmp_path: Path) -> None:
    """Test ValueError on malformed TOML or non-string config entries."""
    bad_toml = tmp_path / "pyproject.toml"
    bad_toml.write_text("invalid toml {{")
    with pytest.raises(ValueError, match="Failed to parse"):
        parse_pyproject_config(bad_toml)

    bad_type = tmp_path / "pyproject.toml"
    bad_type.write_text("[tool.advanced-alchemy]\nconfig = 123\n")
    with pytest.raises(ValueError, match="must be string or list of strings"):
        parse_pyproject_config(bad_type)

    bad_list = tmp_path / "pyproject.toml"
    bad_list.write_text('[tool.advanced-alchemy]\nconfig = ["valid", 42]\n')
    with pytest.raises(ValueError, match="list items must be strings"):
        parse_pyproject_config(bad_list)


def test_resolve_config_sync_validation_errors(
    tmp_path: Path,
    cleanup_test_modules: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ImproperConfigurationError for invalid paths, None, empty lists, and non-config values."""
    module_name = _create_module(
        tmp_path,
        """
none_val = None
empty_list = []
invalid_val = "not_a_config"
invalid_list = ["not_a_config"]
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(ImproperConfigurationError, match="not a valid reference"):
        resolve_config_sync(f"{module_name}:a:b")

    with pytest.raises(ImproperConfigurationError, match="resolved to None"):
        resolve_config_sync(f"{module_name}:none_val")

    with pytest.raises(ImproperConfigurationError, match="resolved to empty list"):
        resolve_config_sync(f"{module_name}:empty_list")

    with pytest.raises(ImproperConfigurationError, match="returned invalid type"):
        resolve_config_sync(f"{module_name}:invalid_val")

    with pytest.raises(ImproperConfigurationError, match="returned invalid config at index 0"):
        resolve_config_sync(f"{module_name}:invalid_list")


@pytest.mark.parametrize(
    ("extension_module", "blocked_top_level"),
    [
        ("advanced_alchemy.extensions.fastapi", ("click", "rich_click", "rich")),
        ("advanced_alchemy.extensions.sanic", ("click", "rich_click", "rich")),
        ("advanced_alchemy.extensions.starlette", ("click", "rich_click", "rich")),
        ("advanced_alchemy.extensions.flask", ("rich_click", "rich")),
    ],
)
def test_framework_extensions_do_not_require_optional_cli_packages_on_import(
    extension_module: str,
    blocked_top_level: tuple[str, ...],
) -> None:
    """Framework extensions must import cleanly when optional CLI packages are absent."""
    pytest.importorskip(extension_module.rsplit(".", 1)[-1])
    script = (
        "import builtins, importlib\n"
        f"blocked = {set(blocked_top_level)!r}\n"
        "real_import = builtins.__import__\n"
        "def guarded_import(name, *args, **kwargs):\n"
        "    if name.split('.', 1)[0] in blocked:\n"
        "        raise ModuleNotFoundError(f'No module named {name!r}')\n"
        "    return real_import(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded_import\n"
        f"importlib.import_module({extension_module!r})\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

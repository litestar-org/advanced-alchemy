from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from sqlalchemy.ext.asyncio import AsyncEngine

from advanced_alchemy.cli import add_migration_commands, get_alchemy_group

if TYPE_CHECKING:
    from click import Group


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
            # it's going to be -1 because we abort the task since we don't fill in the prompt
            assert result.exit_code == 1
            # When prompting is enabled, we need to check if the confirmation was shown
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
            # it's going to be -1 because we abort the task since we don't fill in the prompt
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
    # Original commands
    assert "show-current-revision" in cli_group.commands
    assert "upgrade" in cli_group.commands
    assert "downgrade" in cli_group.commands
    assert "init" in cli_group.commands
    assert "make-migrations" in cli_group.commands
    assert "drop-all" in cli_group.commands
    assert "dump-data" in cli_group.commands
    assert "stamp" in cli_group.commands
    # New commands added for Alembic CLI alignment
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

        # Create an external config file in the temp directory
        config_file = temp_path / "external_config.py"
        config_file.write_text("""
from advanced_alchemy.config import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///:memory:",
    bind_key="external",
)
""")

        # Change to the temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            # Test that the external config can be loaded
            cli_group = add_migration_commands()

            # Use a minimal command that doesn't require database setup
            # but still needs the config to be loaded successfully
            result = cli_runner.invoke(cli_group, ["--config", "external_config.config", "--help"])

            # Should succeed without import errors
            assert result.exit_code == 0
            assert "Error loading config" not in result.output
            assert "No module named" not in result.output

        finally:
            os.chdir(original_cwd)


def test_external_config_loading_multiple_configs(cli_runner: CliRunner) -> None:
    """Test loading multiple configs from external module."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create an external config file with multiple configs
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

        # Change to the temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            cli_group = add_migration_commands()
            result = cli_runner.invoke(cli_group, ["--config", "multi_config.configs", "--help"])

            # Should succeed without import errors
            assert result.exit_code == 0
            assert "Error loading config" not in result.output
            assert "No module named" not in result.output

        finally:
            os.chdir(original_cwd)


def test_external_config_loading_nonexistent_module(cli_runner: CliRunner) -> None:
    """Test appropriate error when external module doesn't exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Change to empty temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            cli_group = add_migration_commands()
            # Use actual command to trigger config loading, not --help
            result = cli_runner.invoke(cli_group, ["--config", "nonexistent_module.config", "show-current-revision"])

            # Should fail with appropriate error
            assert result.exit_code == 1
            assert "Error loading config" in result.output
            assert "No module named 'nonexistent_module'" in result.output

        finally:
            os.chdir(original_cwd)


def test_external_config_loading_nonexistent_attribute(cli_runner: CliRunner) -> None:
    """Test appropriate error when module exists but attribute doesn't."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create an external config file without the expected attribute
        config_file = temp_path / "bad_config.py"
        config_file.write_text("""
# This module exists but doesn't have a 'missing_attr' attribute
from advanced_alchemy.config import SQLAlchemyAsyncConfig

some_other_var = "not a config"
""")

        # Change to the temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)

            cli_group = add_migration_commands()
            # Use actual command to trigger config loading, not --help
            result = cli_runner.invoke(cli_group, ["--config", "bad_config.missing_attr", "show-current-revision"])

            # Should fail with appropriate error
            assert result.exit_code == 1
            assert "Error loading config" in result.output
            # The actual error message may vary, but it should indicate the attribute issue

        finally:
            os.chdir(original_cwd)

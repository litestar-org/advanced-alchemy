from __future__ import annotations

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


def test_cli_group_creation() -> None:
    """Test that the CLI group is created correctly."""
    cli_group = add_migration_commands()
    assert cli_group.name == "alchemy"
    assert "show-current-revision" in cli_group.commands
    assert "upgrade" in cli_group.commands
    assert "downgrade" in cli_group.commands
    assert "init" in cli_group.commands
    assert "make-migrations" in cli_group.commands
    assert "drop-all" in cli_group.commands
    assert "dump-data" in cli_group.commands

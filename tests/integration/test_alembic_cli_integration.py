"""Integration tests for Alembic CLI commands.

Tests the CLI commands against real databases to verify they interact
correctly with Alembic migration operations. These tests focus on verifying
commands execute without errors and perform their intended operations.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest
from alembic.util.exc import CommandError
from pytest import FixtureRequest
from pytest_lazy_fixtures import lf
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from advanced_alchemy import base
from advanced_alchemy.alembic import commands
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("alembic_cli_integration"),
]


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
            ],
        ),
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
    ],
)
def sync_test_config(request: FixtureRequest) -> Generator[SQLAlchemySyncConfig, None, None]:
    """Create sync SQLAlchemy config for testing."""
    engine = cast(Engine, request.getfixturevalue(request.param))
    orm_registry = base.create_registry()
    yield SQLAlchemySyncConfig(
        engine_instance=engine,
        session_maker=sessionmaker(bind=engine, expire_on_commit=False),
        metadata=orm_registry.metadata,
    )


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
            ],
        ),
        pytest.param(
            "asyncpg_engine",
            marks=[
                pytest.mark.asyncpg,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
    ],
)
def async_test_config(request: FixtureRequest) -> Generator[SQLAlchemyAsyncConfig, None, None]:
    """Create async SQLAlchemy config for testing."""
    async_engine = cast(AsyncEngine, request.getfixturevalue(request.param))
    orm_registry = base.create_registry()
    yield SQLAlchemyAsyncConfig(
        engine_instance=async_engine,
        session_maker=async_sessionmaker(bind=async_engine, expire_on_commit=False),
        metadata=orm_registry.metadata,
    )


@pytest.fixture(
    scope="session",
    params=[lf("sync_test_config"), lf("async_test_config")],
    ids=["sync", "async"],
)
def test_config(request: FixtureRequest) -> Generator[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig, None, None]:
    """Return config for current session."""
    if isinstance(request.param, SQLAlchemyAsyncConfig):
        request.getfixturevalue("async_test_config")
    else:
        request.getfixturevalue("sync_test_config")
    yield request.param  # type: ignore[no-any-return]


@pytest.fixture()
def alembic_cmds(
    test_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
) -> Generator[commands.AlembicCommands, None, None]:
    """Create AlembicCommands instance."""
    yield commands.AlembicCommands(
        sqlalchemy_config=test_config,
    )


@pytest.fixture()
def migration_dir(monkeypatch: MonkeyPatch, tmp_path: Path) -> Generator[Path, None, None]:
    """Create temporary migration directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(project_dir)
    yield project_dir


@pytest.fixture()
def initialized_migrations(alembic_cmds: commands.AlembicCommands, migration_dir: Path) -> Generator[Path, None, None]:
    """Initialize Alembic migrations directory."""
    migrations_path = migration_dir / "migrations"
    alembic_cmds.init(directory=str(migrations_path))
    yield migrations_path


@pytest.fixture()
def sample_migration(
    alembic_cmds: commands.AlembicCommands, initialized_migrations: Path
) -> Generator[str, None, None]:
    """Create a sample migration revision."""
    # Generate empty migration (no autogenerate to avoid model dependencies)
    alembic_cmds.revision(message="test migration", autogenerate=False)

    # Find the created revision file
    versions_dir = initialized_migrations / "versions"
    revision_files = list(versions_dir.glob("*.py"))
    assert len(revision_files) > 0, "migration revision should be created"

    # Extract revision ID from filename (format: {rev}_{message}.py)
    revision_id = revision_files[0].stem.split("_")[0]
    yield revision_id


def test_check_with_pending_migrations(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test check command with pending migrations."""
    # Check should run without crashing
    # It may or may not raise CommandError depending on database state
    try:
        alembic_cmds.check()
    except CommandError:
        # Expected - pending migrations detected
        pass


def test_check_with_no_migrations(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test check command with no migrations present."""
    # With no migrations, check may succeed or raise error
    try:
        alembic_cmds.check()
    except CommandError:
        # Expected - no migrations to check
        pass


def test_ensure_version_executes(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test ensure-version command executes without error."""
    # Command should execute without raising exception
    alembic_cmds.ensure_version(sql=False)


def test_ensure_version_sql_output(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test ensure-version with --sql flag generates SQL."""
    # Calling with sql=True should not raise error
    alembic_cmds.ensure_version(sql=True)


def test_stamp_executes(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test stamp command executes."""
    # Ensure version table first
    alembic_cmds.ensure_version(sql=False)
    # Stamp should execute without error
    alembic_cmds.stamp(revision=sample_migration, sql=False, tag=None, purge=False)


def test_stamp_with_sql_flag(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test stamp --sql generates SQL output."""
    # Stamp with sql flag should generate SQL without applying
    alembic_cmds.stamp(revision="head", sql=True, tag=None, purge=False)


def test_stamp_with_tag(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test stamp with custom tag."""
    # Ensure version table
    alembic_cmds.ensure_version(sql=False)
    # Stamp with tag should execute
    alembic_cmds.stamp(revision="head", sql=False, tag="release-1.0", purge=False)


def test_stamp_with_purge(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test stamp --purge option."""
    # Ensure version table
    alembic_cmds.ensure_version(sql=False)
    # Stamp with purge
    alembic_cmds.stamp(revision="head", sql=False, tag=None, purge=True)


def test_heads_executes(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test heads command executes."""
    alembic_cmds.heads(verbose=False, resolve_dependencies=False)


def test_heads_verbose_mode(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test heads command with verbose flag."""
    alembic_cmds.heads(verbose=True, resolve_dependencies=False)


def test_heads_with_resolve_dependencies(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test heads command with dependency resolution."""
    alembic_cmds.heads(verbose=False, resolve_dependencies=True)


def test_heads_no_migrations(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test heads command with no migrations."""
    alembic_cmds.heads(verbose=False, resolve_dependencies=False)


def test_history_shows_migrations(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test history command lists migrations."""
    alembic_cmds.history(rev_range=None, verbose=False, indicate_current=False)


def test_history_verbose_mode(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test history command with verbose output."""
    alembic_cmds.history(rev_range=None, verbose=True, indicate_current=False)


def test_history_with_rev_range(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test history command with revision range."""
    alembic_cmds.history(rev_range="base:head", verbose=False, indicate_current=False)


def test_history_indicate_current(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test history command with current revision indicator."""
    # Ensure version table and stamp
    alembic_cmds.ensure_version(sql=False)
    alembic_cmds.stamp(revision=sample_migration, sql=False, tag=None, purge=False)
    # Show history with current indicator
    alembic_cmds.history(rev_range=None, verbose=False, indicate_current=True)


def test_history_no_migrations(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test history command with no migrations."""
    alembic_cmds.history(rev_range=None, verbose=False, indicate_current=False)


def test_show_head_revision(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test show command displays head revision."""
    alembic_cmds.show(rev="head")


def test_show_specific_revision(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test show command with specific revision ID."""
    alembic_cmds.show(rev=sample_migration)


def test_show_base_revision(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test show command with base revision."""
    alembic_cmds.show(rev="base")


def test_show_invalid_revision(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test show command with invalid revision raises error."""
    with pytest.raises(CommandError):
        alembic_cmds.show(rev="nonexistent_revision_12345")


def test_branches_executes(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test branches command executes."""
    alembic_cmds.branches(verbose=False)


def test_branches_verbose_mode(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test branches command with verbose output."""
    alembic_cmds.branches(verbose=True)


def test_branches_with_multiple_heads(
    alembic_cmds: commands.AlembicCommands, initialized_migrations: Path
) -> None:
    """Test branches command with branched migrations."""
    # Create branched migrations
    alembic_cmds.revision(message="main_branch", autogenerate=False, head="base", branch_label="main")
    alembic_cmds.revision(message="feature_branch", autogenerate=False, head="base", branch_label="feature")
    # Show branches
    alembic_cmds.branches(verbose=False)


def test_merge_creates_revision(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test merge command creates merge revision."""
    # Create two branches
    alembic_cmds.revision(message="branch_a", autogenerate=False, head="base", branch_label="branch_a")
    alembic_cmds.revision(message="branch_b", autogenerate=False, head="base", branch_label="branch_b")
    # Merge
    result = alembic_cmds.merge(
        revisions="branch_a+branch_b",
        message="merge branches",
        branch_label=None,
        rev_id=None,
    )
    assert result is not None


def test_merge_with_custom_message(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test merge command with custom message."""
    alembic_cmds.revision(message="feature_1", autogenerate=False, head="base", branch_label="feature_1")
    alembic_cmds.revision(message="feature_2", autogenerate=False, head="base", branch_label="feature_2")
    result = alembic_cmds.merge(
        revisions="feature_1+feature_2",
        message="custom merge message",
        branch_label=None,
        rev_id=None,
    )
    assert result is not None


def test_merge_with_branch_label(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test merge command with branch label."""
    alembic_cmds.revision(message="dev_1", autogenerate=False, head="base", branch_label="dev_1")
    alembic_cmds.revision(message="dev_2", autogenerate=False, head="base", branch_label="dev_2")
    result = alembic_cmds.merge(
        revisions="dev_1+dev_2",
        message="merge development branches",
        branch_label="merged_dev",
        rev_id=None,
    )
    assert result is not None


def test_merge_with_custom_rev_id(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test merge command with custom revision ID."""
    alembic_cmds.revision(message="work_1", autogenerate=False, head="base", branch_label="work_1")
    alembic_cmds.revision(message="work_2", autogenerate=False, head="base", branch_label="work_2")
    custom_id = "custom_merge_001"
    result = alembic_cmds.merge(
        revisions="work_1+work_2",
        message="merge with custom id",
        branch_label=None,
        rev_id=custom_id,
    )
    assert result is not None
    assert result.revision == custom_id


def test_merge_heads_shortcut(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test merge command with 'heads' shortcut."""
    alembic_cmds.revision(message="head_1", autogenerate=False, head="base", branch_label="head_1")
    alembic_cmds.revision(message="head_2", autogenerate=False, head="base", branch_label="head_2")
    result = alembic_cmds.merge(
        revisions="heads",
        message="merge all heads",
        branch_label=None,
        rev_id=None,
    )
    assert result is not None


def test_edit_with_editor(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test edit command with editor set."""
    # Use 'true' as a safe test editor (exits successfully without interaction)
    with patch.dict(os.environ, {"EDITOR": "true"}):
        alembic_cmds.edit(revision=sample_migration)


def test_edit_head_revision(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test edit command with 'head' revision."""
    with patch.dict(os.environ, {"EDITOR": "true"}):
        alembic_cmds.edit(revision="head")


def test_edit_without_editor(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test edit command without $EDITOR set."""
    # Remove EDITOR from environment
    env = {k: v for k, v in os.environ.items() if k != "EDITOR"}
    with patch.dict(os.environ, env, clear=True):
        # Should raise error or use fallback editor
        try:
            alembic_cmds.edit(revision=sample_migration)
        except (CommandError, OSError, KeyError):
            # Expected - no editor configured
            pass


def test_edit_invalid_revision(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test edit command with invalid revision."""
    with patch.dict(os.environ, {"EDITOR": "true"}):
        with pytest.raises(CommandError):
            alembic_cmds.edit(revision="invalid_revision_xyz")


def test_list_templates_executes(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test list-templates command executes."""
    alembic_cmds.list_templates()


def test_current_executes(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test current command executes."""
    # Ensure version table exists
    alembic_cmds.ensure_version(sql=False)
    alembic_cmds.current(verbose=False)


def test_current_verbose_mode(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test current command with verbose output."""
    alembic_cmds.ensure_version(sql=False)
    alembic_cmds.stamp(revision=sample_migration, sql=False, tag=None, purge=False)
    alembic_cmds.current(verbose=True)


def test_workflow_check_heads_history(alembic_cmds: commands.AlembicCommands, sample_migration: str) -> None:
    """Test workflow of check, heads, and history commands."""
    # Check for pending migrations
    try:
        alembic_cmds.check()
    except CommandError:
        pass
    # Show heads
    alembic_cmds.heads(verbose=False, resolve_dependencies=False)
    # Show history
    alembic_cmds.history(rev_range=None, verbose=False, indicate_current=False)


def test_workflow_branch_and_merge(alembic_cmds: commands.AlembicCommands, initialized_migrations: Path) -> None:
    """Test workflow of creating branches and merging."""
    # Create branches
    alembic_cmds.revision(message="branch_x", autogenerate=False, head="base", branch_label="branch_x")
    alembic_cmds.revision(message="branch_y", autogenerate=False, head="base", branch_label="branch_y")
    # Show branches
    alembic_cmds.branches(verbose=False)
    # Merge
    alembic_cmds.merge(
        revisions="branch_x+branch_y",
        message="merged branches",
        branch_label=None,
        rev_id=None,
    )
    # Show history after merge
    alembic_cmds.history(rev_range=None, verbose=False, indicate_current=False)

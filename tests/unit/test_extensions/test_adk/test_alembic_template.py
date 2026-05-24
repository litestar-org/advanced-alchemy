import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("adk_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copy_adk_template_refuses_to_overwrite_existing_revision(tmp_path: Path) -> None:
    from advanced_alchemy.alembic.templates.adk import copy_adk_template

    versions_dir = tmp_path / "versions"
    first_path = copy_adk_template(versions_dir)

    assert first_path.name == "0001_adk_v1_create_adk_tables.py"
    assert first_path.exists()

    with pytest.raises(FileExistsError, match="ADK migration already exists"):
        copy_adk_template(versions_dir)


def test_adk_migration_template_upgrades_and_downgrades_sqlite(tmp_path: Path) -> None:
    from advanced_alchemy.alembic.templates.adk import copy_adk_template

    migration_path = copy_adk_template(tmp_path / "versions")
    migration = _load_migration(migration_path)
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "adk_internal_metadata",
        "app_states",
        "events",
        "sessions",
        "user_states",
    }
    assert inspector.get_pk_constraint("sessions")["constrained_columns"] == ["app_name", "user_id", "id"]
    assert inspector.get_foreign_keys("events")[0]["options"] == {"ondelete": "CASCADE"}

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()

    assert inspect(engine).get_table_names() == []

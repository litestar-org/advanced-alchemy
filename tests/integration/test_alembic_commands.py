from __future__ import annotations

from pathlib import Path
from typing import Type, cast

import pytest
from _pytest.monkeypatch import MonkeyPatch
from pytest import FixtureRequest
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from advanced_alchemy.alembic import commands
from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from alembic.util.exc import CommandError
from tests import models_uuid

AuthorModel = Type[models_uuid.UUIDAuthor]
RuleModel = Type[models_uuid.UUIDRule]
ModelWithFetchedValue = Type[models_uuid.UUIDModelWithFetchedValue]
ItemModel = Type[models_uuid.UUIDItem]
TagModel = Type[models_uuid.UUIDTag]

pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture(
    params=[
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
            ],
        ),
        pytest.param(
            "duckdb_engine",
            marks=[
                pytest.mark.duckdb,
                pytest.mark.integration,
                pytest.mark.xdist_group("duckdb"),
            ],
        ),
        pytest.param(
            "oracle18c_engine",
            marks=[
                pytest.mark.oracledb,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23c_engine",
            marks=[
                pytest.mark.oracledb,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle23"),
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
        pytest.param(
            "spanner_engine",
            marks=[
                pytest.mark.spanner,
                pytest.mark.integration,
                pytest.mark.xdist_group("spanner"),
            ],
        ),
        pytest.param(
            "mssql_engine",
            marks=[
                pytest.mark.mssql,
                pytest.mark.integration,
                pytest.mark.xdist_group("mssql"),
            ],
        ),
        pytest.param(
            "cockroachdb_engine",
            marks=[
                pytest.mark.cockroachdb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
    ],
)
def sync_sqlalchemy_config(request: FixtureRequest) -> SQLAlchemySyncConfig:
    engine = cast(Engine, request.getfixturevalue(request.param))

    return SQLAlchemySyncConfig(engine_instance=engine, session_maker=sessionmaker(bind=engine, expire_on_commit=False))


@pytest.fixture(
    name="async_engine",
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
            ],
        ),
        pytest.param(
            "asyncmy_engine",
            marks=[
                pytest.mark.asyncmy,
                pytest.mark.integration,
                pytest.mark.xdist_group("mysql"),
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
        pytest.param(
            "psycopg_async_engine",
            marks=[
                pytest.mark.psycopg_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "cockroachdb_async_engine",
            marks=[
                pytest.mark.cockroachdb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
    ],
)
def async_sqlalchemy_config(
    request: FixtureRequest,
) -> SQLAlchemyAsyncConfig:
    async_engine = cast(AsyncEngine, request.getfixturevalue(request.param))
    return SQLAlchemyAsyncConfig(
        engine_instance=async_engine,
        session_maker=async_sessionmaker(bind=async_engine, expire_on_commit=False),
    )


@pytest.fixture(params=["sync_sqlalchemy_config", "async_sqlalchemy_config"])
def alembic_commands(request: FixtureRequest) -> commands.AlembicCommands:
    config = cast(SQLAlchemySyncConfig | SQLAlchemyAsyncConfig, request.getfixturevalue(request.param))
    return commands.AlembicCommands(sqlalchemy_config=config)


@pytest.fixture
def tmp_project_dir(monkeypatch: MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "project_dir"
    path.mkdir(exist_ok=True)
    monkeypatch.chdir(path)
    return path


async def test_alembic_init(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert Path(dir).is_dir()
    for file in expected_files:
        assert Path(file).is_file()


async def test_alembic_init_already(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert Path(dir).is_dir()
    for file in expected_files:
        assert Path(file).is_file()
    with pytest.raises(CommandError):
        alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")


"""
async def test_alembic_revision(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)


async def test_alembic_upgrade(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)
    alembic_commands.upgrade(revision="head")
"""

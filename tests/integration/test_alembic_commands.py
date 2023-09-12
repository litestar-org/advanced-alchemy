from __future__ import annotations

from pathlib import Path
from typing import Type

import pytest
from _pytest.monkeypatch import MonkeyPatch
from pytest import FixtureRequest
from pytest_lazyfixture import lazy_fixture
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.alembic import commands
from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from alembic.util.exc import CommandError
from tests import models_uuid

AuthorModel = Type[models_uuid.UUIDAuthor]
RuleModel = Type[models_uuid.UUIDRule]
ModelWithFetchedValue = Type[models_uuid.UUIDModelWithFetchedValue]
ItemModel = Type[models_uuid.UUIDItem]
TagModel = Type[models_uuid.UUIDTag]


@pytest.fixture()
async def sync_sqlalchemy_config(engine: Engine, session_maker: sessionmaker[Session]) -> SQLAlchemySyncConfig:
    return SQLAlchemySyncConfig(engine_instance=engine, session_maker=session_maker)


@pytest.fixture()
async def async_sqlalchemy_config(
    async_engine: AsyncEngine,
    async_session_maker: async_sessionmaker[AsyncSession],
) -> SQLAlchemyAsyncConfig:
    return SQLAlchemyAsyncConfig(engine_instance=async_engine, session_maker=async_session_maker)


@pytest.fixture(params=[lazy_fixture("sync_sqlalchemy_config"), lazy_fixture("async_sqlalchemy_config")])
async def alembic_commands(request: FixtureRequest) -> commands.AlembicCommands:
    return commands.AlembicCommands(sqlalchemy_config=request.param)


@pytest.fixture
async def tmp_project_dir(monkeypatch: MonkeyPatch, tmp_path: Path) -> Path:
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


async def test_alembic_revision(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)


"""
async def test_alembic_upgrade(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)
    alembic_commands.upgrade(revision="head")
"""

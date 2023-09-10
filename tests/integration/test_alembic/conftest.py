from __future__ import annotations

from typing import cast

import pytest
from pytest import FixtureRequest
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.alembic import commands
from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig


@pytest.fixture()
async def sync_sqlalchemy_config(engine: Engine, session_maker: sessionmaker[Session]) -> SQLAlchemySyncConfig:
    return SQLAlchemySyncConfig(engine_instance=engine, session_maker=session_maker)


@pytest.fixture()
async def async_sqlalchemy_config(
    async_engine: AsyncEngine,
    async_session_maker: async_sessionmaker[AsyncSession],
) -> SQLAlchemyAsyncConfig:
    return SQLAlchemyAsyncConfig(engine_instance=async_engine, session_maker=async_session_maker)


@pytest.fixture()
async def sync_alembic_commands(sync_sqlalchemy_config: SQLAlchemySyncConfig) -> commands.AlembicCommands:
    return commands.AlembicCommands(sqlalchemy_config=sync_sqlalchemy_config)


@pytest.fixture()
async def async_alembic_commands(async_sqlalchemy_config: SQLAlchemyAsyncConfig) -> commands.AlembicCommands:
    return commands.AlembicCommands(sqlalchemy_config=async_sqlalchemy_config)


@pytest.fixture(params=[pytest.param("sync_alembic_commands"), pytest.param("async_alembic_commands")])
async def alembic_commands(request: FixtureRequest) -> commands.AlembicCommands:
    return cast(commands.AlembicCommands, request.getfixturevalue(request.param))

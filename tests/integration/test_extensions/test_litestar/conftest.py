from __future__ import annotations

from typing import cast

import pytest
from litestar.app import Litestar
from pytest import FixtureRequest
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.extensions.litestar.alembic import AlembicCommands
from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyPlugin
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig


@pytest.fixture()
async def sync_sqlalchemy_plugin(engine: Engine, session_maker: sessionmaker[Session]) -> SQLAlchemyPlugin:
    return SQLAlchemyPlugin(config=SQLAlchemySyncConfig(engine_instance=engine, session_maker=session_maker))


@pytest.fixture()
async def async_sqlalchemy_plugin(
    async_engine: AsyncEngine,
    async_session_maker: async_sessionmaker[AsyncSession],
) -> SQLAlchemyPlugin:
    return SQLAlchemyPlugin(
        config=SQLAlchemyAsyncConfig(engine_instance=async_engine, session_maker=async_session_maker),
    )


@pytest.fixture()
async def sync_app(sync_sqlalchemy_plugin: SQLAlchemyPlugin) -> Litestar:
    return Litestar(plugins=[sync_sqlalchemy_plugin])


@pytest.fixture()
async def async_app(async_sqlalchemy_plugin: SQLAlchemyPlugin) -> Litestar:
    return Litestar(plugins=[async_sqlalchemy_plugin])


@pytest.fixture()
async def sync_alembic_commands(sync_app: Litestar) -> AlembicCommands:
    return AlembicCommands(app=sync_app)


@pytest.fixture()
async def async_alembic_commands(async_app: Litestar) -> AlembicCommands:
    return AlembicCommands(app=async_app)


@pytest.fixture(params=[pytest.param("sync_alembic_commands"), pytest.param("async_alembic_commands")])
async def alembic_commands(request: FixtureRequest) -> AlembicCommands:
    return cast(AlembicCommands, request.getfixturevalue(request.param))


@pytest.fixture(params=[pytest.param("sync_app"), pytest.param("async_app")])
async def app(request: FixtureRequest) -> Litestar:
    return cast(Litestar, request.getfixturevalue(request.param))

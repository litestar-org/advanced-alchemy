from __future__ import annotations

from typing import cast

import pytest
from pytest import FixtureRequest
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from litestar.app import Litestar
from litestar.contrib.sqlalchemy.plugins import SQLAlchemyPlugin
from litestar.contrib.sqlalchemy.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from litestar.contrib.sqlalchemy.plugins.init.config.sync import SQLAlchemySyncConfig


@pytest.fixture()
async def sync_sqlalchemy_plugin(engine: Engine, session_maker: sessionmaker[Session]) -> SQLAlchemyPlugin:
    return SQLAlchemyPlugin(config=SQLAlchemySyncConfig(engine_instance=engine, session_maker=session_maker))


@pytest.fixture()
async def async_sqlalchemy_plugin(
    async_engine: AsyncEngine, async_session_maker: async_sessionmaker[AsyncSession]
) -> SQLAlchemyPlugin:
    return SQLAlchemyPlugin(
        config=SQLAlchemyAsyncConfig(engine_instance=async_engine, session_maker=async_session_maker)
    )


@pytest.fixture()
async def sync_app(sync_sqlalchemy_plugin: SQLAlchemyPlugin) -> Litestar:
    return Litestar(plugins=[sync_sqlalchemy_plugin])


@pytest.fixture()
async def async_app(async_sqlalchemy_plugin: SQLAlchemyPlugin) -> Litestar:
    return Litestar(plugins=[async_sqlalchemy_plugin])


@pytest.fixture(params=[pytest.param("sync_app"), pytest.param("async_app")])
async def app(request: FixtureRequest) -> Litestar:
    return cast(Litestar, request.getfixturevalue(request.param))

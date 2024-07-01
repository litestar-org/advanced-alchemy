from __future__ import annotations

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyPlugin
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig


async def test_sync_db_session(sync_sqlalchemy_plugin: SQLAlchemyPlugin) -> None:
    config = cast("SQLAlchemySyncConfig", sync_sqlalchemy_plugin.config)

    with config.get_session() as session:
        assert isinstance(session, Session)


async def test_async_db_session(async_sqlalchemy_plugin: SQLAlchemyPlugin) -> None:
    config = cast("SQLAlchemyAsyncConfig", async_sqlalchemy_plugin.config)

    async with config.get_session() as session:
        assert isinstance(session, AsyncSession)

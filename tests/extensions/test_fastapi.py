"""Tests for FastAPI integration."""

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.extensions.fastapi import SQLAlchemyAsyncConfig, get_session


@pytest.mark.asyncio
async def test_fastapi_integration(async_engine):
    """Test FastAPI integration."""
    app = FastAPI()
    config = SQLAlchemyAsyncConfig(engine_instance=async_engine)
    config.init_app(app)

    async with config.get_session() as session:
        assert isinstance(session, AsyncSession)

    # Test middleware
    async with config.get_session() as session:
        assert isinstance(session, AsyncSession)

    # Test session getter
    session = await get_session()
    assert isinstance(session, AsyncSession)

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sybil import Sybil
from sybil.parsers.rest import PythonCodeBlockParser


@pytest.fixture(name="engine")
async def engine_fixture() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


@pytest.fixture(name="db_session")
async def db_session_fixture(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async_session_factory: sessionmaker[AsyncSession] = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session


pytest_collect_file = Sybil(
    parsers=[PythonCodeBlockParser()],
    patterns=["*.rst", "*.md"],
    fixtures=["db_session", "engine"],
).pytest()

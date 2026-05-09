from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sybil import Sybil
from sybil.parsers.rest import PythonCodeBlockParser

EXECUTABLE_DOCS = (
    "usage/modeling/basics.rst",
    "usage/modeling/inheritance.rst",
    "usage/modeling/sqlmodel.rst",
    "usage/modeling/types.rst",
    "usage/repositories/advanced.rst",
    "usage/repositories/basics.rst",
    "usage/repositories/filtering.rst",
    "usage/database_seeding.rst",
    "usage/services.rst",
)

NON_EXECUTABLE_DOCS = (
    "usage/caching.rst",
    "usage/cli.rst",
    "usage/frameworks/fastapi.rst",
    "usage/frameworks/flask.rst",
    "usage/frameworks/litestar.rst",
    "usage/frameworks/sanic.rst",
    "usage/frameworks/starlette.rst",
    "usage/repositories/relationship-filtering.rst",
    "usage/routing.rst",
)


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
    patterns=EXECUTABLE_DOCS,
    fixtures=["db_session", "engine"],
).pytest()

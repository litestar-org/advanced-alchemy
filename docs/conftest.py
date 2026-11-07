"""Sybil doctest configuration and fixtures for documentation examples."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sybil import Sybil
from sybil.parsers.rest import PythonCodeBlockParser, SkipParser

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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
    "usage/frameworks/litestar.rst",
)

NON_EXECUTABLE_DOCS = (
    "usage/caching.rst",
    "usage/cli.rst",
    "usage/frameworks/fastapi.rst",
    "usage/frameworks/flask.rst",
    "usage/frameworks/sanic.rst",
    "usage/frameworks/starlette.rst",
    "usage/routing.rst",
)


@pytest.fixture(name="engine")
async def engine_fixture() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an in-memory SQLite async engine for documentation code blocks."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


@pytest.fixture(name="db_session")
async def db_session_fixture(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an AsyncSession bound to the documentation engine fixture."""
    async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session


pytest_collect_file = Sybil(
    parsers=[PythonCodeBlockParser(), SkipParser()],
    patterns=EXECUTABLE_DOCS,
    fixtures=["db_session", "engine"],
).pytest()

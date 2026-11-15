"""Sybil doctest configuration and fixtures for documentation examples."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sybil import Sybil
from sybil.integration.pytest import SybilItem
from sybil.parsers.rest import PythonCodeBlockParser, SkipParser

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

EXECUTABLE_DOCS = (
    "usage/database_seeding.rst",
    "usage/service_composition.rst",
    "usage/**/*.rst",
    "getting-started.rst",
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
    async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session


def _setup_sybil_namespace(namespace: dict[str, object]) -> None:
    """Assign a unique module name to each Sybil document execution namespace."""
    namespace["__name__"] = f"sybil_doc_{id(namespace)}"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Keep each document's shared example namespace on one xdist worker."""
    for item in items:
        if isinstance(item, SybilItem):
            item.add_marker(pytest.mark.xdist_group(name=str(item.path)))


pytest_collect_file = Sybil(
    parsers=[PythonCodeBlockParser(), SkipParser()],
    patterns=list(EXECUTABLE_DOCS),
    fixtures=["db_session", "engine"],
    setup=_setup_sybil_namespace,
).pytest()

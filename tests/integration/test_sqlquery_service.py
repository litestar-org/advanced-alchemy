from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, Session

from advanced_alchemy.base import CommonTableAttributes, DeclarativeBase, UUIDPrimaryKey, create_registry
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.utils.fixtures import open_fixture, open_fixture_async

if TYPE_CHECKING:
    pass

pytestmark = [
    pytest.mark.integration,
]
here = Path(__file__).parent
fixture_path = here.parent.parent / "examples"
state_registry = create_registry()


class UUIDBase(UUIDPrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID primary keys."""

    registry = state_registry


class USState(UUIDBase):
    __tablename__ = "us_state_lookup"  # type: ignore[assignment]
    abbreviation: Mapped[str]
    name: Mapped[str]


class USStateSyncRepository(SQLAlchemySyncRepository[USState]):
    """US State repository."""

    model_type = USState


class USStateAsyncRepository(SQLAlchemyAsyncRepository[USState]):
    """US State repository."""

    model_type = USState


def test_sync_fixture_and_query() -> None:
    engine = create_engine("sqlite://")

    state_registry.metadata.create_all(engine)

    with Session(engine) as session:
        repo = USStateSyncRepository(session=session)
        fixture = open_fixture(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _objs = repo.add_many([USStateSyncRepository.model_type(**raw_obj) for raw_obj in fixture])


async def test_async_fixture_and_query() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(state_registry.metadata.create_all)

    async with AsyncSession(engine) as session:
        repo = USStateAsyncRepository(session=session)
        fixture = await open_fixture_async(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _objs = await repo.add_many([USStateSyncRepository.model_type(**raw_obj) for raw_obj in fixture])

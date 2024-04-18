from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, MappedAsDataclass, Session

from advanced_alchemy.base import CommonTableAttributes, DeclarativeBase, SQLQuery, UUIDPrimaryKey, create_registry
from advanced_alchemy.repository import (
    SQLAlchemyAsyncQueryRepository,
    SQLAlchemyAsyncRepository,
    SQLAlchemySyncQueryRepository,
    SQLAlchemySyncRepository,
)
from advanced_alchemy.service import SQLAlchemyAsyncQueryService, SQLAlchemySyncQueryService
from advanced_alchemy.utils.fixtures import open_fixture, open_fixture_async

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


class StateQuery(MappedAsDataclass, SQLQuery):
    """Nonsensical query to test custom SQL queries."""

    __table__ = select(  # type: ignore
        USState.abbreviation.label("state_abbreviation"),
        USState.name.label("state_name"),
    ).alias("state_lookup")
    __mapper_args__ = {
        "primary_key": [USState.abbreviation],
    }
    state_abbreviation: str
    state_name: int


def test_sync_fixture_and_query() -> None:
    engine = create_engine("sqlite://")

    state_registry.metadata.create_all(engine)

    with Session(engine) as session:
        repo = USStateSyncRepository(session=session)
        _query_service = SQLAlchemySyncQueryService(session=session)
        query_repo = SQLAlchemySyncQueryRepository(session=session)
        fixture = open_fixture(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _objs = repo.add_many([USStateSyncRepository.model_type(**raw_obj) for raw_obj in fixture])
        _query_objs, _query_count = query_repo.list_and_count(statement=select(StateQuery))


async def test_async_fixture_and_query() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(state_registry.metadata.create_all)

    async with AsyncSession(engine) as session:
        repo = USStateAsyncRepository(session=session)
        _query_service = SQLAlchemyAsyncQueryService(session=session)
        query_repo = SQLAlchemyAsyncQueryRepository(session=session)
        fixture = await open_fixture_async(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _objs = await repo.add_many([USStateSyncRepository.model_type(**raw_obj) for raw_obj in fixture])

        _query_objs = await query_repo.list(statement=select(StateQuery))

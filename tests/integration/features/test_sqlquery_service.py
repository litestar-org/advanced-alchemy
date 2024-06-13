from __future__ import annotations

from pathlib import Path

import msgspec
import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, MappedAsDataclass, Session

from advanced_alchemy.base import CommonTableAttributes, DeclarativeBase, SQLQuery, UUIDPrimaryKey, create_registry
from advanced_alchemy.repository import (
    SQLAlchemyAsyncRepository,
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
    state_name: str


class StateQueryStruct(msgspec.Struct):
    state_abbreviation: str
    state_name: str


class StateQueryBaseModel(BaseModel):
    state_abbreviation: str
    state_name: str


def test_sync_fixture_and_query() -> None:
    engine = create_engine("sqlite://")

    state_registry.metadata.create_all(engine)

    with Session(engine) as session:
        repo = USStateSyncRepository(session=session)
        query_service = SQLAlchemySyncQueryService(session=session)
        fixture = open_fixture(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _add_objs = repo.add_many([USState(**raw_obj) for raw_obj in fixture])
        query_count = query_service.repository.count(statement=select(StateQuery))
        assert query_count > 0
        list_query_objs, list_query_count = query_service.repository.list_and_count(
            statement=select(StateQuery),
        )
        assert list_query_count >= 50
        _paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
        )
        _pydantic_paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
            schema_type=StateQueryBaseModel,
        )
        _msgspec_paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
            schema_type=StateQueryStruct,
        )
        _list_service_objs = query_service.repository.list(statement=select(StateQuery))
        assert len(_list_service_objs) >= 50
        _get_ones = query_service.repository.list(statement=select(StateQuery), state_name="Alabama")
        assert len(_get_ones) == 1
        _get_one = query_service.repository.get_one(statement=select(StateQuery), state_name="Alabama")
        assert _get_one.state_name == "Alabama"
        _get_one_or_none_1 = query_service.repository.get_one_or_none(
            statement=select(StateQuery).where(StateQuery.state_name == "Texas"),  # type: ignore
        )
        assert _get_one_or_none_1 is not None
        assert _get_one_or_none_1.state_name == "Texas"
        _obj = query_service.to_schema(
            data=_get_one_or_none_1,
        )
        _pydantic_obj = query_service.to_schema(
            data=_get_one_or_none_1,
            schema_type=StateQueryBaseModel,
        )
        _msgspec_objs = query_service.to_schema(
            data=_get_one_or_none_1,
            schema_type=StateQueryStruct,
        )

        _get_one_or_none = query_service.repository.get_one_or_none(
            statement=select(StateQuery).filter_by(state_name="Nope"),
        )
        assert _get_one_or_none is None


async def test_async_fixture_and_query() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(state_registry.metadata.create_all)

    async with AsyncSession(engine) as session:
        repo = USStateAsyncRepository(session=session)
        query_service = SQLAlchemyAsyncQueryService(session=session)
        fixture = await open_fixture_async(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _add_objs = await repo.add_many(
            [
                USStateSyncRepository.model_type(**raw_obj)  # pyright: ignore[reportGeneralTypeIssues]
                for raw_obj in fixture
            ],
        )
        query_count = await query_service.repository.count(statement=select(StateQuery))
        assert query_count > 0
        list_query_objs, list_query_count = await query_service.repository.list_and_count(
            statement=select(StateQuery),
        )
        assert list_query_count >= 50
        _paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
        )
        _pydantic_paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
            schema_type=StateQueryBaseModel,
        )
        _msgspec_paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
            schema_type=StateQueryStruct,
        )
        _list_service_objs = await query_service.repository.list(statement=select(StateQuery))
        assert len(_list_service_objs) >= 50
        _get_ones = await query_service.repository.list(statement=select(StateQuery), state_name="Alabama")
        assert len(_get_ones) == 1
        _get_one = await query_service.repository.get_one(statement=select(StateQuery), state_name="Alabama")
        assert _get_one.state_name == "Alabama"
        _get_one_or_none_1 = await query_service.repository.get_one_or_none(
            statement=select(StateQuery).where(StateQuery.state_name == "Texas"),  # type: ignore
        )
        assert _get_one_or_none_1 is not None
        assert _get_one_or_none_1.state_name == "Texas"
        _obj = query_service.to_schema(
            data=_get_one_or_none_1,
        )
        _pydantic_obj = query_service.to_schema(
            data=_get_one_or_none_1,
            schema_type=StateQueryBaseModel,
        )
        _msgspec_objs = query_service.to_schema(
            data=_get_one_or_none_1,
            schema_type=StateQueryStruct,
        )

        _get_one_or_none = await query_service.repository.get_one_or_none(
            statement=select(StateQuery).filter_by(state_name="Nope"),
        )
        assert _get_one_or_none is None

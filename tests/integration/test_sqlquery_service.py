from __future__ import annotations

from pathlib import Path

import pytest
from msgspec import Struct
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
from advanced_alchemy.service._async import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.service._sync import SQLAlchemySyncRepositoryService
from advanced_alchemy.service.typing import (
    is_msgspec_model,
    is_msgspec_model_with_field,
    is_msgspec_model_without_field,
    is_pydantic_model,
    is_pydantic_model_with_field,
    is_pydantic_model_without_field,
)
from advanced_alchemy.utils.fixtures import open_fixture, open_fixture_async

pytestmark = [  # type: ignore
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


class USStateStruct(Struct):
    abbreviation: str
    name: str


class USStateBaseModel(BaseModel):
    abbreviation: str
    name: str


class USStateSyncRepository(SQLAlchemySyncRepository[USState]):
    """US State repository."""

    model_type = USState


class USStateSyncService(SQLAlchemySyncRepositoryService[USState]):
    """US State repository."""

    repository_type = USStateSyncRepository
    model_type = USState


class USStateAsyncRepository(SQLAlchemyAsyncRepository[USState]):
    """US State repository."""

    model_type = USState


class USStateAsyncService(SQLAlchemyAsyncRepositoryService[USState]):
    """US State repository."""

    repository_type = USStateAsyncRepository
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


class StateQueryStruct(Struct):
    state_abbreviation: str
    state_name: str


class StateQueryBaseModel(BaseModel):
    state_abbreviation: str
    state_name: str


def test_sync_fixture_and_query() -> None:
    engine = create_engine("sqlite://")

    state_registry.metadata.create_all(engine)

    with Session(engine) as session:
        state_service = USStateSyncService(session=session)
        query_service = SQLAlchemySyncQueryService(session=session)
        fixture = open_fixture(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _add_objs = state_service.create_many(
            data=[USStateStruct(**raw_obj) for raw_obj in fixture],
        )
        _ordered_objs = state_service.list(order_by=(USState.name, True))
        assert _ordered_objs[0].name == "Wyoming"
        _ordered_objs_2 = state_service.list_and_count(order_by=[(USState.name, True)])
        assert _ordered_objs_2[0][0].name == "Wyoming"
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
        assert isinstance(_pydantic_paginated_objs.items[0], StateQueryBaseModel)
        _msgspec_paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
            schema_type=StateQueryStruct,
        )
        assert isinstance(_msgspec_paginated_objs.items[0], StateQueryStruct)
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
        assert isinstance(_pydantic_obj, StateQueryBaseModel)
        assert is_pydantic_model(_pydantic_obj)
        assert is_pydantic_model_with_field(_pydantic_obj, "state_abbreviation")
        assert not is_pydantic_model_without_field(_pydantic_obj, "state_abbreviation")

        _msgspec_obj = query_service.to_schema(
            data=_get_one_or_none_1,
            schema_type=StateQueryStruct,
        )
        assert isinstance(_msgspec_obj, StateQueryStruct)
        assert is_msgspec_model(_msgspec_obj)
        assert is_msgspec_model_with_field(_msgspec_obj, "state_abbreviation")
        assert not is_msgspec_model_without_field(_msgspec_obj, "state_abbreviation")

        _get_one_or_none = query_service.repository.get_one_or_none(
            statement=select(StateQuery).filter_by(state_name="Nope"),
        )
        assert _get_one_or_none is None


async def test_async_fixture_and_query() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(state_registry.metadata.create_all)

    async with AsyncSession(engine) as session:
        state_service = USStateAsyncService(session=session)

        query_service = SQLAlchemyAsyncQueryService(session=session)
        fixture = await open_fixture_async(fixture_path, USStateSyncRepository.model_type.__tablename__)  # type: ignore[has-type]
        _add_objs = await state_service.create_many(
            data=[USStateBaseModel(**raw_obj) for raw_obj in fixture],
        )
        _ordered_objs = await state_service.list(order_by=(USState.name, True))
        assert _ordered_objs[0].name == "Wyoming"
        _ordered_objs_2 = await state_service.list_and_count(order_by=(USState.name, True))
        assert _ordered_objs_2[0][0].name == "Wyoming"
        query_count = await query_service.repository.count(statement=select(StateQuery))
        assert query_count > 0
        list_query_objs, list_query_count = await query_service.repository.list_and_count(
            statement=select(StateQuery),
        )
        assert list_query_count >= 50
        _paginated_objs = query_service.to_schema(
            list_query_objs,
            total=list_query_count,
        )

        _pydantic_paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
            schema_type=StateQueryBaseModel,
        )
        assert isinstance(_pydantic_paginated_objs.items[0], StateQueryBaseModel)
        _msgspec_paginated_objs = query_service.to_schema(
            data=list_query_objs,
            total=list_query_count,
            schema_type=StateQueryStruct,
        )
        assert isinstance(_msgspec_paginated_objs.items[0], StateQueryStruct)
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
        assert isinstance(_pydantic_obj, StateQueryBaseModel)
        assert is_pydantic_model(_pydantic_obj)
        assert is_pydantic_model_with_field(_pydantic_obj, "state_abbreviation")
        assert not is_pydantic_model_without_field(_pydantic_obj, "state_abbreviation")

        _msgspec_obj = query_service.to_schema(
            data=_get_one_or_none_1,
            schema_type=StateQueryStruct,
        )
        assert isinstance(_msgspec_obj, StateQueryStruct)
        assert is_msgspec_model(_msgspec_obj)
        assert is_msgspec_model_with_field(_msgspec_obj, "state_abbreviation")
        _get_one_or_none = await query_service.repository.get_one_or_none(
            select(StateQuery).filter_by(state_name="Nope"),
        )
        assert not is_msgspec_model_without_field(_msgspec_obj, "state_abbreviation")
        assert _get_one_or_none is None

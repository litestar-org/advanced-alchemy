from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, Session

from advanced_alchemy.base import UUIDBase, orm_registry
from advanced_alchemy.repository import SQLAlchemySyncRepository

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any


@pytest.fixture(scope="module", name="rows")
def generate_mock_data() -> Iterator[list[dict[str, Any]]]:
    rows = [{"col_1": i, "col_2": f"value_{i}", "col_3": i} for i in range(1, 3)]
    # Duplicate the last row in the list to violate the unique constraint
    rows.extend([rows[-1]] * 3)  # 3 is arbitrary
    yield rows


class USState(UUIDBase):
    abbreviation: Mapped[str]
    name: Mapped[str]


class USStateRepository(SQLAlchemySyncRepository[USState]):
    """US State repository."""

    model_type = USState


def test_as_unique_sync(rows: list[dict[str, Any]]) -> None:
    engine = create_engine("sqlite://")

    orm_registry.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(USState(**row) for row in rows)
        with pytest.raises(IntegrityError):
            # An exception should be raised when not using ``as_unique_sync``
            session.flush()

    with Session(engine) as session:
        session.add_all(USState.as_unique_sync(session, **row) for row in rows)
        statement = select(func.count()).select_from(USState)
        count = session.scalar(statement)
        assert count == 2


async def test_as_unique_async(rows: list[dict[str, Any]]) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(orm_registry.metadata.create_all)

    async with AsyncSession(engine) as session:
        session.add_all(USState(**row) for row in rows)
        with pytest.raises(IntegrityError):
            # An exception should be raised when not using ``as_unique_async``
            await session.flush()

    async with AsyncSession(engine) as session:
        session.add_all([await USState.as_unique_async(session, **row) for row in rows])
        statement = select(func.count()).select_from(USState)
        count = await session.scalar(statement)
        assert count == 2

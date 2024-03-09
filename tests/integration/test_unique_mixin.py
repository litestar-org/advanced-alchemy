from __future__ import annotations

from collections.abc import Hashable
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import ColumnElement, String, UniqueConstraint, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.mixins import UniqueMixin

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any


@pytest.fixture(scope="module", name="rows")
def generate_mock_data() -> Iterator[list[dict[str, Any]]]:
    rows = [{"col_1": i, "col_2": f"value_{i}", "col_3": i} for i in range(1, 3)]
    # Duplicate the last row in the list three times to violate the unique constraint
    rows.extend([rows[-1]] * 3)
    yield rows


class BigIntModelWithUniqueValue(UniqueMixin, BigIntBase):
    col_1: Mapped[int]
    col_2: Mapped[str] = mapped_column(String(50))
    col_3: Mapped[int]

    __table_args__ = (UniqueConstraint("col_1", "col_3"),)

    @classmethod
    def unique_hash(cls, col_1: int, col_2: int, col_3: str) -> Hashable:
        return (col_1, col_3)

    @classmethod
    def unique_filter(cls, col_1: int, col_2: int, col_3: str) -> ColumnElement[bool]:
        return (cls.col_1 == col_1) & (cls.col_3 == col_3)


def test_as_unique_sync(rows: list[dict[str, Any]]) -> None:
    engine = create_engine("sqlite://")

    BigIntModelWithUniqueValue.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(BigIntModelWithUniqueValue(**row) for row in rows)
        with pytest.raises(IntegrityError):
            # An exception should be raised when not using ``as_unique_sync``
            session.flush()

    with Session(engine) as session:
        session.add_all(BigIntModelWithUniqueValue.as_unique_sync(session, **row) for row in rows)
        statement = select(func.count()).select_from(BigIntModelWithUniqueValue)
        count = session.scalar(statement)
        assert count == 2


async def test_as_unique_async(rows: list[dict[str, Any]]) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")

    async with engine.begin() as conn:
        await conn.run_sync(BigIntModelWithUniqueValue.metadata.create_all)

    async with AsyncSession(engine) as session:
        session.add_all(BigIntModelWithUniqueValue(**row) for row in rows)
        with pytest.raises(IntegrityError):
            # An exception should be raised when not using ``as_unique_async``
            await session.flush()

    async with AsyncSession(engine) as session:
        session.add_all([await BigIntModelWithUniqueValue.as_unique_async(session, **row) for row in rows])
        statement = select(func.count()).select_from(BigIntModelWithUniqueValue)
        count = await session.scalar(statement)
        assert count == 2

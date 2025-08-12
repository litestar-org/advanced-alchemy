from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Hashable
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import ColumnElement, Engine, String, UniqueConstraint, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy import base, mixins
from advanced_alchemy.base import create_registry
from advanced_alchemy.exceptions import MultipleResultsFoundError
from advanced_alchemy.mixins import UniqueMixin

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("unique_mixin"),
]


@pytest.fixture(name="rows")
def generate_mock_data() -> Iterator[list[dict[str, Any]]]:
    rows = [{"col_1": i, "col_2": f"value_{i}", "col_3": i} for i in range(1, 3)]
    # Duplicate the last row in the list to violate the unique constraint
    rows.extend([rows[-1]] * 3)  # 3 is arbitrary
    yield rows


custom_registry = create_registry()


class CustomBigIntBase(mixins.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with BigInt primary keys using custom registry."""

    registry = custom_registry


@pytest.fixture(scope="session")
def sync_engine() -> Generator[Engine, None, None]:
    """Session-scoped sync engine for unique mixin testing."""
    engine = create_engine("sqlite://")
    custom_registry.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async engine for unique mixin testing."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(custom_registry.metadata.create_all)
    yield engine
    await engine.dispose()


class BigIntModelWithUniqueValue(UniqueMixin, CustomBigIntBase):
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


class BigIntModelWithMaybeUniqueValue(UniqueMixin, CustomBigIntBase):
    col_1: Mapped[int]
    col_2: Mapped[str] = mapped_column(String(50))
    col_3: Mapped[int]

    @classmethod
    def unique_hash(cls, col_1: int, col_2: int, col_3: str) -> Hashable:
        return (col_1, col_3)

    @classmethod
    def unique_filter(cls, col_1: int, col_2: int, col_3: str) -> ColumnElement[bool]:
        return (cls.col_1 == col_1) & (cls.col_3 == col_3)


@pytest.mark.xdist_group("unique_mixin")
def test_as_unique_sync(sync_engine: Engine, rows: list[dict[str, Any]]) -> None:
    # Skip for Spanner and CockroachDB - BigInt PK issues
    if sync_engine.dialect.name.startswith(("spanner", "cockroach")):
        pytest.skip(f"{sync_engine.dialect.name} doesn't support bigint PKs well")
    with Session(sync_engine) as session:
        session.add_all(BigIntModelWithUniqueValue(**row) for row in rows)
        with pytest.raises(IntegrityError):
            # An exception should be raised when not using ``as_unique_sync``
            session.flush()

    with Session(sync_engine) as session:
        session.add_all(BigIntModelWithUniqueValue.as_unique_sync(session, **row) for row in rows)
        statement = select(func.count()).select_from(BigIntModelWithUniqueValue)
        count = session.scalar(statement)
        assert count == 2

    with Session(sync_engine) as session:
        # Add non unique rows on purpose to check if the mixin triggers ``MultipleResultsFound``
        session.add_all(BigIntModelWithMaybeUniqueValue(**row) for row in rows)
        # flush here so that when the mixin queries the db, the non unique rows are in the transaction
        session.flush()
        with pytest.raises(MultipleResultsFoundError):
            session.add_all(BigIntModelWithMaybeUniqueValue.as_unique_sync(session, **row) for row in rows)


@pytest.mark.xdist_group("unique_mixin")
async def test_as_unique_async(async_engine: AsyncEngine, rows: list[dict[str, Any]]) -> None:
    # Skip for Spanner and CockroachDB - BigInt PK issues
    if async_engine.dialect.name.startswith(("spanner", "cockroach")):
        pytest.skip(f"{async_engine.dialect.name} doesn't support bigint PKs well")
    async with AsyncSession(async_engine) as session:
        session.add_all(BigIntModelWithUniqueValue(**row) for row in rows)
        with pytest.raises(IntegrityError):
            # An exception should be raised when not using ``as_unique_async``
            await session.flush()

    async with AsyncSession(async_engine) as session:
        session.add_all([await BigIntModelWithUniqueValue.as_unique_async(session, **row) for row in rows])
        statement = select(func.count()).select_from(BigIntModelWithUniqueValue)
        count = await session.scalar(statement)
        assert count == 2

    async with AsyncSession(async_engine) as session:
        # Add non unique rows on purpose to check if the mixin triggers ``MultipleResultsFound``
        session.add_all(BigIntModelWithMaybeUniqueValue(**row) for row in rows)
        # flush here so that when the mixin queries the db, the non unique rows are in the transaction
        await session.flush()
        with pytest.raises(MultipleResultsFoundError):
            session.add_all([await BigIntModelWithMaybeUniqueValue.as_unique_async(session, **row) for row in rows])

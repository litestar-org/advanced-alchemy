from __future__ import annotations

from collections.abc import Hashable
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import ColumnElement, Engine, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy import base, mixins
from advanced_alchemy.base import create_registry
from advanced_alchemy.exceptions import MultipleResultsFoundError
from advanced_alchemy.mixins import UniqueMixin
from tests.integration.test_models import DatabaseCapabilities

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


@pytest.fixture()
def unique_test_tables(engine: Engine) -> None:
    """Create unique mixin test tables for sync engines."""
    # Skip for databases that don't support unique constraints
    if DatabaseCapabilities.should_skip_unique_constraints(engine.dialect.name):
        pytest.skip(f"{engine.dialect.name} doesn't support unique constraints")
    if getattr(engine.dialect, "name", "") != "mock":
        custom_registry.metadata.create_all(engine)


@pytest.fixture()
async def unique_test_tables_async(async_engine: AsyncEngine) -> None:
    """Create unique mixin test tables for async engines."""
    # Skip for databases that don't support unique constraints
    if DatabaseCapabilities.should_skip_unique_constraints(async_engine.dialect.name):
        pytest.skip(f"{async_engine.dialect.name} doesn't support unique constraints")
    if getattr(async_engine.dialect, "name", "") != "mock":
        async with async_engine.begin() as conn:
            await conn.run_sync(custom_registry.metadata.create_all)


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


def test_as_unique_sync(engine: Engine, unique_test_tables: None, rows: list[dict[str, Any]]) -> None:
    # Skip for databases that don't support unique constraints
    if DatabaseCapabilities.should_skip_unique_constraints(engine.dialect.name):
        pytest.skip(f"{engine.dialect.name} doesn't support unique constraints")
    # Skip for Spanner and CockroachDB - BigInt PK issues
    if DatabaseCapabilities.should_skip_bigint(engine.dialect.name):
        pytest.skip(f"{engine.dialect.name} doesn't support bigint PKs well")
    # Skip for mock engines - they don't handle multi-row INSERT properly
    if getattr(engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engines don't support multi-row INSERT for unique mixin tests")
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

    with Session(engine) as session:
        # Add non unique rows on purpose to check if the mixin triggers ``MultipleResultsFound``
        session.add_all(BigIntModelWithMaybeUniqueValue(**row) for row in rows)
        # flush here so that when the mixin queries the db, the non unique rows are in the transaction
        session.flush()
        with pytest.raises(MultipleResultsFoundError):
            session.add_all(BigIntModelWithMaybeUniqueValue.as_unique_sync(session, **row) for row in rows)


async def test_as_unique_async(
    async_engine: AsyncEngine, unique_test_tables_async: None, rows: list[dict[str, Any]]
) -> None:
    # Skip for databases that don't support unique constraints
    if DatabaseCapabilities.should_skip_unique_constraints(async_engine.dialect.name):
        pytest.skip(f"{async_engine.dialect.name} doesn't support unique constraints")
    # Skip for Spanner and CockroachDB - BigInt PK issues
    if DatabaseCapabilities.should_skip_bigint(async_engine.dialect.name):
        pytest.skip(f"{async_engine.dialect.name} doesn't support bigint PKs well")
    # Skip for mock engines - they don't handle multi-row INSERT properly
    if getattr(async_engine.dialect, "name", "") == "mock":
        pytest.skip("Mock engines don't support multi-row INSERT for unique mixin tests")
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

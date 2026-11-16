"""SQLite parity for SQLAlchemy literal predicates in mock repositories."""

from typing import Optional

import pytest
from sqlalchemy import Boolean, ColumnElement, Integer, create_engine, literal, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.repository.memory.base import InMemoryFilterEvaluator


class LiteralBase(DeclarativeBase):
    """Isolated metadata for predicate parity."""


class LiteralRow(LiteralBase):
    """Nullable boolean values exercise SQL literal semantics."""

    __tablename__ = "literal_row"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[Optional[bool]] = mapped_column(Boolean)


@pytest.mark.parametrize(
    "predicate",
    [
        LiteralRow.enabled == True,  # noqa: E712
        LiteralRow.enabled == False,  # noqa: E712
        LiteralRow.enabled != True,  # noqa: E712
        LiteralRow.enabled != False,  # noqa: E712
        LiteralRow.enabled.is_(True),
        LiteralRow.enabled.is_(False),
        LiteralRow.enabled.is_not(True),
        LiteralRow.enabled.is_not(False),
        LiteralRow.enabled == literal(None),
        LiteralRow.enabled != literal(None),
        LiteralRow.enabled < literal(None),
        LiteralRow.enabled.is_(None),
        LiteralRow.enabled.is_not(None),
    ],
)
def test_mock_literal_predicates_match_sqlite(predicate: ColumnElement[bool]) -> None:
    """Mock filtering selects the same rows as SQLite for true, false, and null."""
    engine = create_engine("sqlite:///:memory:")
    LiteralBase.metadata.create_all(engine)
    with Session(engine) as session:
        rows = [LiteralRow(id=1, enabled=True), LiteralRow(id=2, enabled=False), LiteralRow(id=3, enabled=None)]
        session.add_all(rows)
        session.commit()
        expected = list(session.scalars(select(LiteralRow.id).where(predicate).order_by(LiteralRow.id)))
        actual = [row.id for row in rows if InMemoryFilterEvaluator.evaluate_sql_expression(row, predicate) is True]
        assert actual == expected

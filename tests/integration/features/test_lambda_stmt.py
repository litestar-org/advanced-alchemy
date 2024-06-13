from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import ForeignKey, String, create_engine, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, sessionmaker

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository

if TYPE_CHECKING:
    from pytest import MonkeyPatch

xfail = pytest.mark.xfail


# This test does not work when run in group for some reason.
# If you run individually, it'll pass.
@pytest.mark.xdist_group("lambda")
@xfail()
def test_lambda_statement_quirks(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base

    orm_registry = base.create_registry()

    class NewUUIDBase(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

    class NewBigIntBase(base.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)

    monkeypatch.setattr(base, "BigIntBase", NewBigIntBase)

    class Country(UUIDBase):
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore

    class State(UUIDBase):
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        country_id: Mapped[str] = mapped_column(ForeignKey(Country.id))

        country = relationship(Country)

    class USStateRepository(SQLAlchemySyncRepository[State]):
        model_type = State

    engine = create_engine("sqlite:///:memory:", echo=True)
    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)

    with engine.begin() as conn:
        State.metadata.create_all(conn)

    engine.clear_compiled_cache()
    with session_factory() as db_session:
        usa = Country(name="United States of America")
        france = Country(name="France")
        db_session.add(usa)
        db_session.add(france)

        california = State(name="California", country=usa)
        oregon = State(name="Oregon", country=usa)
        ile_de_france = State(name="Île-de-France", country=france)

        repo = USStateRepository(session=db_session)
        repo.add(california)
        repo.add(oregon)
        repo.add(ile_de_france)
        db_session.commit()

        # Using only the ORM, this works fine:

        stmt = select(State).where(State.country_id == usa.id).with_only_columns(func.count())
        count = db_session.execute(stmt).scalar_one()
        assert count == 2, f"Expected 2, got {count}"
        count = db_session.execute(stmt).scalar_one()
        assert count == 2, f"Expected 2, got {count}"

        stmt = select(State).where(State.country == usa).with_only_columns(func.count(), maintain_column_froms=True)
        count = db_session.execute(stmt).scalar_one()
        assert count == 2, f"Expected 2, got {count}"
        count = db_session.execute(stmt).scalar_one()
        assert count == 2, f"Expected 2, got {count}"

        # Using the repository, this works:
        stmt1 = select(State).where(State.country_id == usa.id)

        count = repo.count(statement=stmt1)
        assert count == 2, f"Expected 2, got {count}"

        count = repo.count(statement=stmt1)
        assert count == 2, f"Expected 2, got {count}"

        # But this would fail (only after the second query) (lambda caching test):
        stmt2 = select(State).where(State.country == usa)

        count = repo.count(statement=stmt2)
        assert count == 2, f"Expected 2, got {count}"

        count = repo.count(State.country == usa)
        assert count == 2, f"Expected 2, got {count}"

        count = repo.count(statement=stmt2)
        assert count == 2, f"Expected 2, got {count}"

        # It also failed with
        states = repo.list(statement=stmt2)
        count = len(states)
        assert count == 2, f"Expected 2, got {count}"

        _states, count = repo.list_and_count(statement=stmt2)
        assert count == 2, f"Expected 2, got {count}"
        _states, count = repo.list_and_count(statement=stmt2, force_basic_query_mode=True)
        assert count == 2, f"Expected 2, got {count}"

from sqlalchemy import ForeignKey, create_engine, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, sessionmaker

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository


def test_lambda_statement_quirks() -> None:

    class Country(UUIDBase):
        name: Mapped[str]

    class State(UUIDBase):
        name: Mapped[str]
        country_id: Mapped[str] = mapped_column(ForeignKey(Country.id))

        country = relationship(Country)

    class USStateRepository(SQLAlchemySyncRepository[State]):
        model_type = State

    engine = create_engine("sqlite:///:memory:", future=True, echo=True)
    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)

    with engine.begin() as conn:
        State.metadata.create_all(conn)

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

        stmt = select(State).where(State.country == usa).with_only_columns(func.count())
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

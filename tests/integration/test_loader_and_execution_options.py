from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, selectinload, sessionmaker

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository


def test_loader() -> None:
    class Country(UUIDBase):
        name: Mapped[str]
        states: Mapped[List[State]] = relationship(back_populates="country", uselist=True)

    class State(UUIDBase):
        name: Mapped[str]
        country_id: Mapped[UUID] = mapped_column(ForeignKey(Country.id))

        country: Mapped[Country] = relationship(uselist=False, back_populates="states", lazy="raise")

    class USStateRepository(SQLAlchemySyncRepository[State]):
        model_type = State

    class CountryRepository(SQLAlchemySyncRepository[Country]):
        model_type = Country

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
        del repo
        repo = USStateRepository(session=db_session, load="*")
        star_california = repo.get_one(name="California")
        assert star_california.country.name == "United States of America"
        del repo

        repo = USStateRepository(session=db_session, load=State.country)
        string_california = repo.get_one(name="California")
        assert string_california.id == star_california.id
        del repo

        country_repo = CountryRepository(session=db_session, load="*")
        usa_country = country_repo.get_one(name="United States of America")
        assert len(usa_country.states) == 2
        del country_repo
        del usa_country

        country_repo = CountryRepository(session=db_session)
        usa_country = country_repo.get_one(name="United States of America", load=[selectinload(Country.states)])
        assert len(usa_country.states) == 2
        del country_repo

        country_repo = CountryRepository(session=db_session, load=[selectinload(Country.states)])
        usa_country = country_repo.get_one(name="United States of America")
        assert len(usa_country.states) == 2
        del country_repo

    with engine.begin() as conn:
        State.metadata.drop_all(conn)

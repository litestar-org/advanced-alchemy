from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, selectinload, sessionmaker

from advanced_alchemy.base import BigIntBase, UUIDBase
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository


def test_loader() -> None:
    class UUIDCountry(UUIDBase):
        name: Mapped[str]
        states: Mapped[List[UUIDState]] = relationship(back_populates="country", uselist=True)

    class UUIDState(UUIDBase):
        name: Mapped[str]
        country_id: Mapped[UUID] = mapped_column(ForeignKey(UUIDCountry.id))

        country: Mapped[UUIDCountry] = relationship(uselist=False, back_populates="states", lazy="raise")

    class USStateRepository(SQLAlchemySyncRepository[UUIDState]):
        model_type = UUIDState

    class CountryRepository(SQLAlchemySyncRepository[UUIDCountry]):
        model_type = UUIDCountry

    engine = create_engine("sqlite:///:memory:", echo=True)
    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)

    with engine.begin() as conn:
        UUIDState.metadata.create_all(conn)

    with session_factory() as db_session:
        usa = UUIDCountry(name="United States of America")
        france = UUIDCountry(name="France")
        db_session.add(usa)
        db_session.add(france)

        california = UUIDState(name="California", country=usa)
        oregon = UUIDState(name="Oregon", country=usa)
        ile_de_france = UUIDState(name="Île-de-France", country=france)

        repo = USStateRepository(session=db_session)
        repo.add(california)
        repo.add(oregon)
        repo.add(ile_de_france)
        db_session.commit()
        del repo

        si0_country_repo = CountryRepository(session=db_session)
        usa_country = si0_country_repo.get_one(
            name="United States of America",
            load=UUIDCountry.states,
            execution_options={"populate_existing": True},
        )
        assert len(usa_country.states) == 2
        del si0_country_repo

        si1_country_repo = CountryRepository(session=db_session)
        usa_country = si1_country_repo.get_one(name="United States of America", load=[selectinload(UUIDCountry.states)])
        assert len(usa_country.states) == 2
        del si1_country_repo

        si2_country_repo = CountryRepository(session=db_session, load=[selectinload(UUIDCountry.states)])
        usa_country = si2_country_repo.get_one(name="United States of America")
        assert len(usa_country.states) == 2
        del si2_country_repo

        repo = USStateRepository(session=db_session, load=UUIDState.country)
        string_california = repo.get_one(name="California")
        assert string_california.id == california.id
        del repo

        repo = USStateRepository(session=db_session, load="*")
        star_california = repo.get_one(name="California")
        assert star_california.country.name == "United States of America"
        del repo

        star_country_repo = CountryRepository(session=db_session, load="*")
        usa_country = star_country_repo.get_one(name="United States of America")
        assert len(usa_country.states) == 2
        del star_country_repo
        del usa_country

    with engine.begin() as conn:
        UUIDState.metadata.drop_all(conn)


async def test_async_loader() -> None:
    class BigIntCountry(BigIntBase):
        name: Mapped[str]
        states: Mapped[List[BigIntState]] = relationship(back_populates="country", uselist=True)

    class BigIntState(BigIntBase):
        name: Mapped[str]
        country_id: Mapped[int] = mapped_column(ForeignKey(BigIntCountry.id))

        country: Mapped[BigIntCountry] = relationship(uselist=False, back_populates="states", lazy="raise")

    class USStateRepository(SQLAlchemyAsyncRepository[BigIntState]):
        model_type = BigIntState

    class CountryRepository(SQLAlchemyAsyncRepository[BigIntCountry]):
        model_type = BigIntCountry

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True, echo=True)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(BigIntState.metadata.create_all)

    async with session_factory() as db_session:
        usa = BigIntCountry(name="United States of America")
        france = BigIntCountry(name="France")
        db_session.add(usa)
        db_session.add(france)

        california = BigIntState(name="California", country=usa)
        oregon = BigIntState(name="Oregon", country=usa)
        ile_de_france = BigIntState(name="Île-de-France", country=france)

        repo = USStateRepository(session=db_session)
        await repo.add(california)
        await repo.add(oregon)
        await repo.add(ile_de_france)
        await db_session.commit()
        del repo

        si0_country_repo = CountryRepository(session=db_session)
        usa_country = await si0_country_repo.get_one(
            name="United States of America",
            load=BigIntCountry.states,
            execution_options={"populate_existing": True},
        )
        assert len(usa_country.states) == 2
        del si0_country_repo

        country_repo = CountryRepository(session=db_session)
        usa_country = await country_repo.get_one(
            name="United States of America", load=[selectinload(BigIntCountry.states)],
        )
        assert len(usa_country.states) == 2
        del country_repo

        country_repo = CountryRepository(session=db_session, load=[selectinload(BigIntCountry.states)])
        usa_country = await country_repo.get_one(name="United States of America")
        assert len(usa_country.states) == 2
        del country_repo

        repo = USStateRepository(session=db_session, load=BigIntState.country)
        string_california = await repo.get_one(name="California")
        assert string_california.id == california.id
        del repo

        repo = USStateRepository(session=db_session, load="*")
        star_california = await repo.get_one(name="California")
        assert star_california.country.name == "United States of America"
        del repo

        country_repo = CountryRepository(session=db_session, load="*")
        usa_country = await country_repo.get_one(name="United States of America")
        assert len(usa_country.states) == 2
        del country_repo
        del usa_country

    async with engine.begin() as conn:
        await conn.run_sync(BigIntState.metadata.drop_all)

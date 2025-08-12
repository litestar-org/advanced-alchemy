from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from sqlalchemy import Engine, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, Session, mapped_column, noload, relationship, selectinload, sessionmaker

from advanced_alchemy.base import BigIntBase, UUIDBase
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository

if TYPE_CHECKING:
    from pytest import MonkeyPatch

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("loader_execution"),
]


@pytest.mark.xdist_group("loader")
def test_loader(monkeypatch: MonkeyPatch, engine: Engine) -> None:
    import uuid

    from advanced_alchemy import base, mixins

    # Use a unique bind key for this test to avoid metadata conflicts
    bind_key = f"test_loader_{uuid.uuid4().hex[:8]}"

    class NewUUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        __abstract__ = True
        __bind_key__ = bind_key

    class NewBigIntBase(mixins.BigIntPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        __abstract__ = True
        __bind_key__ = bind_key

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)

    monkeypatch.setattr(base, "BigIntBase", NewBigIntBase)

    class UUIDCountry(UUIDBase):
        __tablename__ = "uuid_country_test_loader"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        states: Mapped[list[UUIDState]] = relationship(back_populates="country", uselist=True, lazy="noload")

    class UUIDState(UUIDBase):
        __tablename__ = "uuid_state_test_loader"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        country_id: Mapped[UUID] = mapped_column(ForeignKey("uuid_country_test_loader.id"))

        country: Mapped[UUIDCountry] = relationship(uselist=False, back_populates="states", lazy="raise")

    class USStateRepository(SQLAlchemySyncRepository[UUIDState]):
        model_type = UUIDState

    class CountryRepository(SQLAlchemySyncRepository[UUIDCountry]):
        model_type = UUIDCountry

    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)

    with engine.begin() as conn:
        # Use the metadata from the bind key
        NewUUIDBase.metadata.create_all(conn)

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
        db_session.expire_all()

        si1_country_repo = CountryRepository(session=db_session, load=[noload(UUIDCountry.states)])
        usa_country_1 = si1_country_repo.get_one(
            name="United States of America",
        )
        assert len(usa_country_1.states) == 0
        si0_country_repo = CountryRepository(session=db_session)

        db_session.expire_all()
        usa_country_0 = si0_country_repo.get_one(
            name="United States of America",
            load=UUIDCountry.states,
            execution_options={"populate_existing": True},
        )
        assert len(usa_country_0.states) == 2
        db_session.expire_all()

        si2_country_repo = CountryRepository(session=db_session, load=[selectinload(UUIDCountry.states)])
        usa_country_2 = si2_country_repo.get_one(name="United States of America")
        assert len(usa_country_2.states) == 2
        db_session.expire_all()

        ia_repo = USStateRepository(session=db_session, load=UUIDState.country)
        string_california = ia_repo.get_one(name="California")
        assert string_california.name == "California"
        db_session.expire_all()

        star_repo = USStateRepository(session=db_session, load="*")
        star_california = star_repo.get_one(name="California")
        assert star_california.country.name == "United States of America"
        db_session.expire_all()

        star_country_repo = CountryRepository(session=db_session, load="*")
        usa_country_3 = star_country_repo.get_one(name="United States of America")
        assert len(usa_country_3.states) == 2
        db_session.expunge_all()
        db_session.expire_all()

        si1_country_repo = CountryRepository(session=db_session)
        usa_country_1 = si1_country_repo.get_one(
            name="United States of America",
            load=[noload(UUIDCountry.states)],
        )
        assert len(usa_country_1.states) == 0
        si0_country_repo = CountryRepository(session=db_session)
        db_session.expire_all()


@pytest.mark.xdist_group("loader")
async def test_async_loader(monkeypatch: MonkeyPatch, async_engine: AsyncEngine) -> None:
    from advanced_alchemy import base, mixins

    orm_registry = base.create_registry()

    class NewUUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        __abstract__ = True
        registry = orm_registry

    class NewBigIntBase(mixins.BigIntPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        __abstract__ = True
        registry = orm_registry

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)

    monkeypatch.setattr(base, "BigIntBase", NewBigIntBase)

    class BigIntCountry(BigIntBase):
        __tablename__ = "bigint_country_async_loader"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        states: Mapped[list[BigIntState]] = relationship(back_populates="country", uselist=True)

    class BigIntState(BigIntBase):
        __tablename__ = "bigint_state_async_loader"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        country_id: Mapped[int] = mapped_column(ForeignKey("bigint_country_async_loader.id"))

        country: Mapped[BigIntCountry] = relationship(uselist=False, back_populates="states", lazy="raise")

    class USStateRepository(SQLAlchemyAsyncRepository[BigIntState]):
        model_type = BigIntState

    class CountryRepository(SQLAlchemyAsyncRepository[BigIntCountry]):
        model_type = BigIntCountry

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(async_engine, expire_on_commit=False)

    async with async_engine.begin() as conn:
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
        db_session.expire_all()

        si1_country_repo = CountryRepository(session=db_session, load=[noload(BigIntCountry.states)])
        usa_country_21 = await si1_country_repo.get_one(
            name="United States of America",
        )
        assert len(usa_country_21.states) == 0
        db_session.expire_all()

        si0_country_repo = CountryRepository(session=db_session)
        usa_country_0 = await si0_country_repo.get_one(
            name="United States of America",
            load=BigIntCountry.states,
            execution_options={"populate_existing": True},
        )
        assert len(usa_country_0.states) == 2
        db_session.expire_all()

        country_repo = CountryRepository(session=db_session)
        usa_country_1 = await country_repo.get_one(
            name="United States of America",
            load=[selectinload(BigIntCountry.states)],
        )
        assert len(usa_country_1.states) == 2
        db_session.expire_all()

        si_country_repo = CountryRepository(session=db_session, load=[selectinload(BigIntCountry.states)])
        usa_country_02 = await si_country_repo.get_one(name="United States of America")
        assert len(usa_country_02.states) == 2
        db_session.expire_all()

        ia_repo = USStateRepository(session=db_session, load=BigIntState.country)
        string_california = await ia_repo.get_one(name="California")
        assert string_california.name == "California"
        db_session.expire_all()

        star_repo = USStateRepository(session=db_session, load="*")
        star_california = await star_repo.get_one(name="California")
        assert star_california.country.name == "United States of America"
        db_session.expire_all()

        star_country_repo = CountryRepository(session=db_session, load="*")
        usa_country_3 = await star_country_repo.get_one(name="United States of America")
        assert len(usa_country_3.states) == 2
        db_session.expire_all()


@pytest.mark.xdist_group("loader")
def test_default_overrides_loader(monkeypatch: MonkeyPatch, engine: Engine) -> None:
    from advanced_alchemy import base, mixins

    orm_registry = base.create_registry()

    class NewUUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        __abstract__ = True
        registry = orm_registry

    class NewBigIntBase(mixins.BigIntPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        __abstract__ = True
        registry = orm_registry

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)

    monkeypatch.setattr(base, "BigIntBase", NewBigIntBase)

    class UUIDCountryTest(UUIDBase):
        __tablename__ = "uuid_country_test_override"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        states: Mapped[list[UUIDStateTest]] = relationship(back_populates="country", uselist=True, lazy="selectin")

    class UUIDStateTest(UUIDBase):
        __tablename__ = "uuid_state_test_override"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        country_id: Mapped[UUID] = mapped_column(ForeignKey("uuid_country_test_override.id"))

        country: Mapped[UUIDCountryTest] = relationship(uselist=False, back_populates="states", lazy="noload")

    class USStateRepository(SQLAlchemySyncRepository[UUIDStateTest]):
        model_type = UUIDStateTest
        merge_loader_options = False
        loader_options = [noload(UUIDStateTest.country)]

    class CountryRepository(SQLAlchemySyncRepository[UUIDCountryTest]):
        inherit_lazy_relationships = False
        model_type = UUIDCountryTest

    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)

    with engine.begin() as conn:
        UUIDStateTest.metadata.create_all(conn)

    with session_factory() as db_session:
        usa = UUIDCountryTest(name="United States of America")
        france = UUIDCountryTest(name="France")
        db_session.add(usa)
        db_session.add(france)

        california = UUIDStateTest(name="California", country=usa)
        oregon = UUIDStateTest(name="Oregon", country=usa)
        ile_de_france = UUIDStateTest(name="Île-de-France", country=france)

        repo = USStateRepository(session=db_session)
        repo.add(california)
        repo.add(oregon)
        repo.add(ile_de_france)
        db_session.commit()
        db_session.expire_all()

        si1_country_repo = CountryRepository(session=db_session)
        usa_country_1 = si1_country_repo.get_one(
            name="United States of America",
        )
        assert len(usa_country_1.states) == 2
        usa_country_2 = si1_country_repo.get_one(
            name="United States of America",
            load="*",
            execution_options={"populate_existing": True},
        )
        assert len(usa_country_2.states) == 2


@pytest.mark.xdist_group("loader")
async def test_default_overrides_async_loader(monkeypatch: MonkeyPatch, async_engine: AsyncEngine) -> None:
    from advanced_alchemy import base, mixins

    orm_registry = base.create_registry()

    class NewUUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        registry = orm_registry

    class NewBigIntBase(mixins.BigIntPrimaryKey, base.CommonTableAttributes, base.AdvancedDeclarativeBase):
        registry = orm_registry

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)

    monkeypatch.setattr(base, "BigIntBase", NewBigIntBase)

    class BigIntCountryTest(BigIntBase):
        __tablename__ = "bigint_country_test_async_override"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        states: Mapped[list[BigIntStateTest]] = relationship(back_populates="country", uselist=True, lazy="selectin")
        notes: Mapped[list[BigIntCountryNote]] = relationship(back_populates="country", uselist=True, lazy="selectin")

    class BigIntCountryNote(BigIntBase):
        __tablename__ = "bigint_country_note_async_override"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        country_id: Mapped[int] = mapped_column(ForeignKey("bigint_country_test_async_override.id"))
        country: Mapped[BigIntCountryTest] = relationship(uselist=False, back_populates="notes", lazy="raise")

    class BigIntStateTest(BigIntBase):
        __tablename__ = "bigint_state_test_async_override"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        country_id: Mapped[int] = mapped_column(ForeignKey("bigint_country_test_async_override.id"))

        country: Mapped[BigIntCountryTest] = relationship(uselist=False, back_populates="states", lazy="raise")

    class USStateRepository(SQLAlchemyAsyncRepository[BigIntStateTest]):
        model_type = BigIntStateTest

    class CountryRepository(SQLAlchemyAsyncRepository[BigIntCountryTest]):
        model_type = BigIntCountryTest
        merge_loader_options = False
        loader_options = [noload(BigIntCountryTest.states), noload(BigIntCountryTest.notes)]

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(async_engine, expire_on_commit=False)

    async with async_engine.begin() as conn:
        await conn.run_sync(BigIntStateTest.metadata.create_all)

    async with session_factory() as db_session:
        usa = BigIntCountryTest(name="United States of America")
        usa.notes.append(BigIntCountryNote(name="Note 1"))
        france = BigIntCountryTest(name="France")
        db_session.add(usa)
        db_session.add(france)

        california = BigIntStateTest(name="California", country=usa)
        oregon = BigIntStateTest(name="Oregon", country=usa)
        ile_de_france = BigIntStateTest(name="Île-de-France", country=france)

        repo = USStateRepository(session=db_session)
        await repo.add(california)
        await repo.add(oregon)
        await repo.add(ile_de_france)
        await db_session.commit()
        db_session.expire_all()

        si1_country_repo = CountryRepository(session=db_session, load=[noload(BigIntCountryTest.states)])
        usa_country_21 = await si1_country_repo.get_one(
            name="United States of America",
        )
        assert len(usa_country_21.states) == 0
        db_session.expire_all()

        si0_country_repo = CountryRepository(session=db_session)
        usa_country_0 = await si0_country_repo.get_one(
            name="United States of America",
            load=BigIntCountryTest.states,
            execution_options={"populate_existing": True},
        )
        assert len(usa_country_0.states) == 2
        db_session.expire_all()

        country_repo = CountryRepository(session=db_session)
        usa_country_1 = await country_repo.get_one(
            name="United States of America",
            load=[selectinload(BigIntCountryTest.states)],
        )
        assert len(usa_country_1.states) == 2
        db_session.expire_all()

        si_country_repo = CountryRepository(session=db_session, load=[noload(BigIntCountryTest.notes)])
        usa_country_02 = await si_country_repo.get_one(
            name="United States of America", load=[selectinload(BigIntCountryTest.states)]
        )
        assert len(usa_country_02.notes) == 1
        db_session.expire_all()

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Engine, ForeignKey, String, Table, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, sessionmaker

if TYPE_CHECKING:
    from pytest import MonkeyPatch

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("bigint_identity"),
]


@pytest.mark.xdist_group("loader")
def test_ap_sync(monkeypatch: MonkeyPatch, engine: Engine) -> None:
    # Skip problematic engines
    dialect_name = getattr(engine.dialect, "name", "")
    if dialect_name == "duckdb":
        pytest.skip("DuckDB doesn't support BIGSERIAL type")
    if dialect_name == "mock":
        pytest.skip("Mock engines don't properly support multi-row inserts with RETURNING")
    if "oracle" in dialect_name:
        pytest.skip("Oracle has issues with BIGSERIAL syntax")
    if dialect_name == "mssql":
        pytest.skip("MSSQL requires VARCHAR length specification")
    
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base, mixins

    orm_registry = base.create_registry()

    class NewIdentityBase(mixins.IdentityPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

    monkeypatch.setattr(base, "IdentityBase", NewIdentityBase)

    product_tag_table = Table(
        "product_tag_identity_sync",
        orm_registry.metadata,
        Column("product_id", ForeignKey("product_identity_sync.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
        Column("tag_id", ForeignKey("tag_identity_sync.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
    )

    class Tag(NewIdentityBase):
        __tablename__ = "tag_identity_sync"
        name: Mapped[str] = mapped_column(String(100), index=True)
        products: Mapped[list[Product]] = relationship(
            secondary=lambda: product_tag_table,
            back_populates="product_tags",
            cascade="all, delete",
            passive_deletes=True,
            lazy="noload",
        )

    class Product(NewIdentityBase):
        __tablename__ = "product_identity_sync"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        product_tags: Mapped[list[Tag]] = relationship(
            secondary=lambda: product_tag_table,
            back_populates="products",
            cascade="all, delete",
            passive_deletes=True,
            lazy="joined",
        )
        tags: AssociationProxy[list[str]] = association_proxy(
            "product_tags",
            "name",
            creator=lambda name: Tag(name=name),  # pyright: ignore[reportUnknownArgumentType,reportUnknownLambdaType]
        )

    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)

    with engine.begin() as conn:
        Product.metadata.create_all(conn)

    with session_factory() as db_session:
        product_1 = Product(name="Product 1", tags=["a new tag", "second tag"])
        db_session.add(product_1)

        tags = db_session.execute(select(Tag)).unique().fetchall()
        assert len(tags) == 2

        product_2 = Product(name="Product 2", tags=["third tag"])
        db_session.add(product_2)
        tags = db_session.execute(select(Tag)).unique().fetchall()
        assert len(tags) == 3

        product_2.tags = []
        db_session.add(product_2)

        product_2_validate = db_session.execute(select(Product).where(Product.name == "Product 2")).unique().fetchone()
        assert product_2_validate
        tags_2 = db_session.execute(select(Tag)).unique().fetchall()
        assert len(product_2_validate[0].product_tags) == 0
        assert len(tags_2) == 3
        # add more assertions


@pytest.mark.xdist_group("loader")
async def test_ap_async(monkeypatch: MonkeyPatch, async_engine: AsyncEngine) -> None:
    # Skip problematic engines
    dialect_name = getattr(async_engine.dialect, "name", "")
    if dialect_name == "duckdb":
        pytest.skip("DuckDB doesn't support BIGSERIAL type")
    if dialect_name == "mock":
        pytest.skip("Mock engines don't properly support multi-row inserts with RETURNING")
    if "oracle" in dialect_name:
        pytest.skip("Oracle has issues with BIGSERIAL syntax")
    if dialect_name in ("mssql", "asyncmy"):
        pytest.skip("MSSQL and MySQL require VARCHAR length specification")
    
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base, mixins

    orm_registry = base.create_registry()

    class NewIdentityBase(mixins.IdentityPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

    monkeypatch.setattr(base, "IdentityBase", NewIdentityBase)

    product_tag_table = Table(
        "product_tag_identity_async",
        orm_registry.metadata,
        Column("product_id", ForeignKey("product_identity_async.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
        Column("tag_id", ForeignKey("tag_identity_async.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
    )

    class Tag(NewIdentityBase):
        __tablename__ = "tag_identity_async"
        name: Mapped[str] = mapped_column(String(100), index=True)
        products: Mapped[list[Product]] = relationship(
            secondary=lambda: product_tag_table,
            back_populates="product_tags",
            cascade="all, delete",
            passive_deletes=True,
            lazy="noload",
        )

    class Product(NewIdentityBase):
        __tablename__ = "product_identity_async"
        name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
        product_tags: Mapped[list[Tag]] = relationship(
            secondary=lambda: product_tag_table,
            back_populates="products",
            cascade="all, delete",
            passive_deletes=True,
            lazy="joined",
        )
        tags: AssociationProxy[list[str]] = association_proxy(
            "product_tags",
            "name",
            creator=lambda name: Tag(name=name),  # pyright: ignore[reportUnknownArgumentType,reportUnknownLambdaType]
        )

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(async_engine, expire_on_commit=False)

    async with async_engine.begin() as conn:
        await conn.run_sync(Tag.metadata.create_all)

    async with session_factory() as db_session:
        product_1 = Product(name="Product 1 async", tags=["a new tag", "second tag"])
        db_session.add(product_1)

        tags = await db_session.execute(select(Tag))
        assert len(tags.unique().fetchall()) == 2

        product_2 = Product(name="Product 2 async", tags=["third tag"])
        db_session.add(product_2)
        tags = await db_session.execute(select(Tag))
        assert len(tags.unique().fetchall()) == 3

        # add more assertions

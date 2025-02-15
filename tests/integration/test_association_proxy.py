from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, ForeignKey, String, Table, create_engine, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, sessionmaker

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.mark.xdist_group("loader")
def test_ap_sync(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base, mixins

    orm_registry = base.create_registry()

    class NewUUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)

    product_tag_table = Table(
        "product_tag",
        orm_registry.metadata,
        Column("product_id", ForeignKey("product.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
        Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
    )

    class Tag(NewUUIDBase):
        name: Mapped[str] = mapped_column(index=True)
        products: Mapped[list[Product]] = relationship(
            secondary=lambda: product_tag_table,
            back_populates="product_tags",
            cascade="all, delete",
            passive_deletes=True,
            lazy="noload",
        )

    class Product(NewUUIDBase):
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

    engine = create_engine(f"sqlite:///{tmp_path}/test.sqlite1.db", echo=True)
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

        _product_2_validate = db_session.execute(select(Product).where(Product.name == "Product 2")).unique().fetchone()
        assert _product_2_validate
        tags_2 = db_session.execute(select(Tag)).unique().fetchall()
        assert len(_product_2_validate[0].product_tags) == 0
        assert len(tags_2) == 3
        # add more assertions


@pytest.mark.xdist_group("loader")
async def test_ap_async(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base, mixins

    orm_registry = base.create_registry()

    class NewUUIDBase(mixins.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)

    product_tag_table = Table(
        "product_tag",
        orm_registry.metadata,
        Column("product_id", ForeignKey("product.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
        Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore[reportUnknownArgumentType]
    )

    class Tag(NewUUIDBase):
        name: Mapped[str] = mapped_column(index=True)
        products: Mapped[list[Product]] = relationship(
            secondary=lambda: product_tag_table,
            back_populates="product_tags",
            cascade="all, delete",
            passive_deletes=True,
            lazy="noload",
        )

    class Product(NewUUIDBase):
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

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.sqlite2.db", echo=True)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
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

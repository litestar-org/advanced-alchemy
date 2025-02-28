# ruff: noqa: PLR2004, S101
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import create_async_engine

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped


class Item(UUIDBase):
    name: Mapped[str]
    # using ``Mapped[dict]`` with an AA provided base will map it to ``JSONB``
    data: Mapped[dict[str, Any]]


class ItemRepository(SQLAlchemyAsyncRepository[Item]):
    """Item repository."""

    model_type = Item


config = SQLAlchemyAsyncConfig(
    engine_instance=create_async_engine("postgresql+psycopg://app:super-secret@localhost:5432/app"),
    session_config=AsyncSessionConfig(expire_on_commit=False),
)


async def run_script() -> None:
    # Initializes the database.
    async with config.get_engine().begin() as conn:
        await conn.run_sync(Item.metadata.create_all)
    async with config.get_session() as db_session:
        repo = ItemRepository(session=db_session)
        # Add some data
        await repo.add_many(
            [
                Item(
                    name="Smartphone",
                    data={"price": 599.99, "brand": "XYZ"},
                ),
                Item(
                    name="Laptop",
                    data={"price": 1299.99, "brand": "ABC"},
                ),
                Item(
                    name="Headphones",
                    data={"not_price": 149.99, "brand": "DEF"},
                ),
            ],
            auto_commit=True,
        )

    async with config.get_session() as db_session:
        repo = ItemRepository(session=db_session)
        # Do some queries with JSON operations
        assert await repo.exists(Item.data["price"].as_float() == 599.99, Item.data["brand"].as_string() == "XYZ")

        assert await repo.count(Item.data.op("?")("price")) == 2

        products, total_products = await repo.list_and_count(Item.data.op("?")("not_price"))
        assert len(products) == 1
        assert total_products == 1
        assert products[0].name == "Headphones"


if __name__ == "__main__":
    asyncio.run(run_script())

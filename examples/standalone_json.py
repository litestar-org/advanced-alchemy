from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, Session

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository


class Item(UUIDBase):
    name: Mapped[str]
    # using ``Mapped[dict]`` with an AA provided base will map it to ``JSONB``
    data: Mapped[dict]


class ItemRepository(SQLAlchemySyncRepository[Item]):
    """Item repository."""

    model_type = Item


engine = create_engine("postgresql+psycopg://username:password@localhost:5432/database")


def run_script() -> None:
    # Initializes the database.
    with engine.begin() as conn:
        Item.metadata.create_all(conn)

    with Session(engine) as session:
        repo = ItemRepository(session=session)
        # Add some data
        Items = [
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
        ]
        repo.add_many(Items)
        session.commit()

    with Session(engine) as session:
        repo = ItemRepository(session=session)

        # Do some queries with JSON operations
        statement = (Item.data["price"].as_float() == 599.99) & (
            Item.data["brand"].as_string() == "XYZ"
        )
        assert repo.exists(statement)

        statement = Item.data.op("?")("price")
        assert repo.count(statement) == 2

        statement = Item.data.op("?")("not_price")
        products = repo.list(statement)
        assert len(products) == 1
        assert products[0].name == "Headphones"


if __name__ == "__main__":
    run_script()

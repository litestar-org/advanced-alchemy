====================================
Database Seeding and Fixture Loading
====================================

Advanced Alchemy provides :func:`~advanced_alchemy.utils.fixtures.open_fixture` and :func:`~advanced_alchemy.utils.fixtures.open_fixture_async` for loading JSON and CSV fixtures from disk (including ``.gz`` and ``.zip`` archives).

Creating Fixtures
-----------------

Fixtures can be stored as JSON or CSV. JSON preserves native numbers, booleans, and nested structures, while CSV returns string-valued dictionaries that should be coerced before constructing models.

.. code-block:: json
    :caption: fixtures/products.json

    [
        {
            "name": "Laptop",
            "description": "High-performance laptop with 16GB RAM and 1TB SSD",
            "price": 999.99,
            "in_stock": true
        },
        {
            "name": "Smartphone",
            "description": "Latest smartphone model with 5G and advanced camera",
            "price": 699.99,
            "in_stock": true
        }
    ]

Loading Fixtures
----------------

Synchronous Loading
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from pathlib import Path
    from typing import Optional

    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.config import SQLAlchemySyncConfig, SyncSessionConfig
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture

    alchemy_config = SQLAlchemySyncConfig(
        connection_string="sqlite:///db.sqlite3",
        session_config=SyncSessionConfig(expire_on_commit=False),
    )


    class SyncProduct(UUIDBase):
        __tablename__ = "sync_products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[Optional[str]] = mapped_column(String(length=500))
        price: Mapped[float]
        in_stock: Mapped[bool] = mapped_column(default=True)


    class SyncProductRepository(SQLAlchemySyncRepository[SyncProduct]):
        model_type = SyncProduct


    def seed_database(fixtures_path: Path = Path("fixtures")) -> None:
        with alchemy_config.get_session() as db_session:
            repository = SyncProductRepository(session=db_session)
            fixture_data = open_fixture(fixtures_path, "products")
            repository.add_many([SyncProduct(**item) for item in fixture_data], auto_commit=True)

Asynchronous Loading
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from pathlib import Path
    from typing import Optional

    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture_async

    async_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///db.sqlite3",
        session_config=AsyncSessionConfig(expire_on_commit=False),
    )


    class AsyncProduct(UUIDBase):
        __tablename__ = "async_products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[Optional[str]] = mapped_column(String(length=500))
        price: Mapped[float]
        in_stock: Mapped[bool] = mapped_column(default=True)


    class AsyncProductRepository(SQLAlchemyAsyncRepository[AsyncProduct]):
        model_type = AsyncProduct


    async def seed_async_database(fixtures_path: Path = Path("fixtures")) -> None:
        async with async_config.get_session() as db_session:
            repository = AsyncProductRepository(session=db_session)
            fixture_data = await open_fixture_async(fixtures_path, "products")
            await repository.add_many([AsyncProduct(**item) for item in fixture_data], auto_commit=True)

CSV Fixtures
~~~~~~~~~~~~

CSV fixtures use the header row as dictionary keys and return string values:

.. code-block:: text

    name,price,in_stock
    Widget,9.99,true
    Gadget,19.99,true

Coerce CSV strings before passing rows to a repository or service:

.. code-block:: python

    from pathlib import Path
    from typing import Any

    from advanced_alchemy.utils.fixtures import open_fixture_async


    def coerce_product_row(row: dict[str, str]) -> dict[str, Any]:
        return {
            "name": row["name"],
            "price": float(row["price"]),
            "in_stock": row["in_stock"].lower() == "true",
        }


    async def seed_from_csv(repository: AsyncProductRepository, fixtures_path: Path) -> None:
        raw_rows = await open_fixture_async(fixtures_path, "products")
        products = [AsyncProduct(**coerce_product_row(item)) for item in raw_rows]
        await repository.add_many(products, auto_commit=True)

Application Integration and Best Practices
------------------------------------------

Keep schema migrations (``alembic upgrade``) separate from fixture loading, and use ``upsert_many`` when seed commands must be idempotent across deployments:

.. code-block:: python

    from pathlib import Path
    from typing import Any

    from advanced_alchemy.utils.fixtures import open_fixture_async


    async def load_database_fixtures(role_service: Any, fixtures_path: Path) -> None:
        fixture_data = await open_fixture_async(fixtures_path, "role")
        await role_service.upsert_many(match_fields=["name"], data=fixture_data, auto_commit=True)

- Store fixtures in a dedicated version-controlled ``fixtures/`` directory (plain or ``.gz`` / ``.zip`` compressed).
- Seed parent tables before dependent child tables.
- Use `Polyfactory <https://github.com/litestar-org/polyfactory>`__ when generating synthetic test data rather than loading static seed files.

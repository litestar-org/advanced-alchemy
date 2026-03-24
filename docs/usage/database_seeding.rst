====================================
Database Seeding and Fixture Loading
====================================

Advanced Alchemy provides ``open_fixture()`` and ``open_fixture_async()`` helpers for loading JSON
and CSV fixtures from disk. Use them to keep seed data in version-controlled files while leaving the
actual upsert logic in your application code.

Creating Fixtures
-----------------

Fixtures can be stored as JSON or CSV. JSON preserves native types, while CSV returns a list of
string-valued dictionaries that you should coerce before creating typed models.

**Example JSON fixture:**

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

    DATABASE_URL = "sqlite:///db.sqlite3"
    fixtures_path = Path("fixtures")

    alchemy_config = SQLAlchemySyncConfig(
        connection_string=DATABASE_URL,
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

    def initialize_database() -> None:
        with alchemy_config.get_engine().begin() as conn:
            UUIDBase.metadata.create_all(conn)

    def seed_database() -> None:
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

    DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"
    fixtures_path = Path("fixtures")

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string=DATABASE_URL,
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

    async def initialize_async_database() -> None:
        async with alchemy_config.get_engine().begin() as conn:
            await conn.run_sync(UUIDBase.metadata.create_all)

    async def seed_async_database() -> None:
        async with alchemy_config.get_session() as db_session:
            repository = AsyncProductRepository(session=db_session)
            fixture_data = await open_fixture_async(fixtures_path, "products")
            await repository.add_many([AsyncProduct(**item) for item in fixture_data], auto_commit=True)


CSV Fixtures
~~~~~~~~~~~~

.. versionadded:: 1.9.0

CSV fixtures use the header row as dictionary keys, but each value is returned as a string. Coerce
those values before constructing models or sending data into a service layer.

**Example CSV (products.csv):**

.. code-block:: text

    name,price,in_stock
    Widget,9.99,true
    Gadget,19.99,true
    Thingy,4.99,false

**Loading CSV Fixtures:**

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


Application Integration
-----------------------

The Litestar fullstack reference applications keep schema migration and fixture loading as separate
application commands. Apply migrations first, then run an app-level command that loads or upserts
fixtures for your domain services.

.. code-block:: text

    uv run app database upgrade

For the fixture loader itself, keep the mapping logic close to the service that owns the data:

.. code-block:: python

    from pathlib import Path
    from typing import Any

    from advanced_alchemy.utils.fixtures import open_fixture_async

    async def load_database_fixtures(role_service: Any, fixtures_path: Path) -> None:
        fixture_data = await open_fixture_async(fixtures_path, "role")
        await role_service.upsert_many(match_fields=["name"], data=fixture_data, auto_commit=True)


Best Practices
--------------

1. Keep fixtures in a dedicated directory such as ``fixtures/``.
2. Keep migration commands and fixture-loading commands separate.
3. Use ``upsert_many()`` when your seed data should be re-runnable without creating duplicates.
4. Coerce CSV values before creating strongly typed models.
5. Seed parent tables before child tables when relationships are involved.
6. Keep fixtures under version control alongside your application code.

Tips for Efficient Seeding
--------------------------

- Use ``add_many()`` or ``upsert_many()`` instead of inserting one row at a time.
- Use JSON when you need native numbers, booleans, nested objects, or UUIDs preserved.
- Use CSV for flatter datasets when string-to-type coercion is straightforward.
- Large fixture files can be stored as ``.json.gz``, ``.json.zip``, ``.csv.gz``, or ``.csv.zip``.
- Application startup hooks, background jobs, and CLI commands are all reasonable places to invoke fixture loaders.
- Consider using `Polyfactory <https://github.com/litestar-org/polyfactory>`__ when you need generated data rather than static fixtures.

====================
Database Seeding
====================

When setting up a new environment or staging server, you often want starter rows—such as default roles, categories, or sample products—loaded from version-controlled ``.json`` or ``.csv`` files.

Advanced Alchemy's ``open_fixture`` and ``open_fixture_async`` helpers locate and parse fixture files (including compressed ``.gz`` and ``.zip`` files) in one call.

Writing a Fixture File
----------------------

Store your seed files in a ``fixtures/`` folder. JSON keeps numbers and booleans typed automatically, while CSV files load every column as strings:

.. tab-set::

    .. tab-item:: JSON Fixture

        .. code-block:: json
            :caption: fixtures/products.json

            [
                {
                    "name": "Laptop",
                    "description": "16GB RAM and 1TB SSD",
                    "price": 999.99,
                    "in_stock": true
                },
                {
                    "name": "Smartphone",
                    "description": "5G OLED display",
                    "price": 699.99,
                    "in_stock": true
                }
            ]

    .. tab-item:: CSV Fixture

        .. code-block:: text
            :caption: fixtures/products.csv

            name,price,in_stock
            Widget,9.99,true
            Gadget,19.99,true

Loading Fixtures Into Your Database
-----------------------------------

Pick ``open_fixture_async`` for async apps or ``open_fixture`` for sync scripts:

.. tab-set::

    .. tab-item:: Async Seeding

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
                description: Mapped[Optional[str]] = mapped_column(String(length=500), default=None)
                price: Mapped[float]
                in_stock: Mapped[bool] = mapped_column(default=True)


            class AsyncProductRepository(SQLAlchemyAsyncRepository[AsyncProduct]):
                model_type = AsyncProduct


            async def seed_async_products(fixtures_path: Path = Path("fixtures")) -> None:
                async with async_config.get_session() as db_session:
                    repo = AsyncProductRepository(session=db_session)
                    rows = await open_fixture_async(fixtures_path, "products")
                    await repo.add_many([AsyncProduct(**row) for row in rows], auto_commit=True)

    .. tab-item:: Sync Seeding

        .. code-block:: python

            from pathlib import Path
            from typing import Optional
            from sqlalchemy import String
            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import UUIDBase
            from advanced_alchemy.config import SQLAlchemySyncConfig, SyncSessionConfig
            from advanced_alchemy.repository import SQLAlchemySyncRepository
            from advanced_alchemy.utils.fixtures import open_fixture

            sync_config = SQLAlchemySyncConfig(
                connection_string="sqlite:///db.sqlite3",
                session_config=SyncSessionConfig(expire_on_commit=False),
            )


            class SyncProduct(UUIDBase):
                __tablename__ = "sync_products"

                name: Mapped[str] = mapped_column(String(length=100))
                description: Mapped[Optional[str]] = mapped_column(String(length=500), default=None)
                price: Mapped[float]
                in_stock: Mapped[bool] = mapped_column(default=True)


            class SyncProductRepository(SQLAlchemySyncRepository[SyncProduct]):
                model_type = SyncProduct


            def seed_sync_products(fixtures_path: Path = Path("fixtures")) -> None:
                with sync_config.get_session() as db_session:
                    repo = SyncProductRepository(session=db_session)
                    rows = open_fixture(fixtures_path, "products")
                    repo.add_many([SyncProduct(**row) for row in rows], auto_commit=True)

    .. tab-item:: Converting CSV Strings

        .. code-block:: python

            from pathlib import Path
            from typing import Any
            from advanced_alchemy.utils.fixtures import open_fixture_async


            def parse_csv_product(row: dict[str, str]) -> dict[str, Any]:
                return {
                    "name": row["name"],
                    "price": float(row["price"]),
                    "in_stock": row["in_stock"].lower() == "true",
                }


            async def seed_from_csv(repo: AsyncProductRepository, fixtures_path: Path) -> None:
                raw_rows = await open_fixture_async(fixtures_path, "products")
                products = [AsyncProduct(**parse_csv_product(item)) for item in raw_rows]
                await repo.add_many(products, auto_commit=True)

Safe Re-Runs Across Deployments
-------------------------------

Use ``upsert_many`` instead of ``add_many`` when a seed script runs on every deployment so existing rows are updated cleanly without duplicate errors:

.. code-block:: python

    from pathlib import Path
    from typing import Any
    from advanced_alchemy.utils.fixtures import open_fixture_async


    async def seed_roles(role_service: Any, fixtures_path: Path) -> None:
        rows = await open_fixture_async(fixtures_path, "role")
        await role_service.upsert_many(match_fields=["name"], data=rows, auto_commit=True)

.. tip::

    Seed parent tables (like ``Author``) before child tables (like ``Post``), and consider `Polyfactory <https://github.com/litestar-org/polyfactory>`__ when generating random test data in ``pytest``.

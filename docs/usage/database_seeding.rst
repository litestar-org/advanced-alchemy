====================
Database Seeding
====================

When setting up a new environment or staging server, you often want starter rows—such as default roles, categories, or sample products—loaded from version-controlled fixture files.

Advanced Alchemy's fixture helpers find, parse, stream, and write these files for you: ``open_fixture_sync`` and ``open_fixture_async`` load a whole fixture, ``iter_fixture_sync`` and ``iter_fixture_async`` stream it in batches, and ``write_fixture_sync`` and ``write_fixture_async`` write one.

Fixture Formats
---------------

Store your seed files in a ``fixtures/`` folder. Each format can be stored plain, gzip-compressed (``.gz``), or zipped (``.zip``):

.. list-table::
   :header-rows: 1
   :widths: 18 52 30

   * - Format
     - File Names
     - Loads As
   * - JSON
     - ``products.json``, ``products.json.gz``, ``products.json.zip``
     - The decoded value, with typed numbers and booleans
   * - JSON Lines
     - ``products.jsonl``, ``products.jsonl.gz``, ``products.jsonl.zip``
     - A list with one value per non-blank line
   * - CSV
     - ``products.csv``, ``products.csv.gz``, ``products.csv.zip``
     - A list of dicts whose values are strings

When several formats exist for the same name, JSON is used first, then JSON Lines, then CSV. Upper-case names are found for compressed files (``PRODUCTS.json.gz``), plain CSV (``PRODUCTS.csv``), and shards.

.. code-block:: text
    :caption: fixtures/products.jsonl

    {"name": "Laptop", "description": "16GB RAM and 1TB SSD", "price": 999.99, "in_stock": true}
    {"name": "Smartphone", "description": "5G OLED display", "price": 699.99, "in_stock": true}

Loading Fixtures Into Your Database
-----------------------------------

Pick ``open_fixture_async`` for async apps or ``open_fixture_sync`` for sync scripts:

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
            from advanced_alchemy.utils.fixtures import open_fixture_sync

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
                    rows = open_fixture_sync(fixtures_path, "products")
                    repo.add_many([SyncProduct(**row) for row in rows], auto_commit=True)

.. note::

    ``open_fixture`` still works as an alias of ``open_fixture_sync``, but it emits a ``DeprecationWarning`` and is removed in version 2.0.

CSV values always load as strings, so convert them before building models:

.. code-block:: python

    from typing import Any


    def parse_csv_product(row: dict[str, str]) -> dict[str, Any]:
        return {"name": row["name"], "price": float(row["price"]), "in_stock": row["in_stock"].lower() == "true"}

Streaming Large Fixtures in Batches
-----------------------------------

``iter_fixture_async`` and ``iter_fixture_sync`` yield lists of at most ``batch_size`` records, so a large JSON Lines or CSV fixture is never held in memory all at once:

.. code-block:: python

    from advanced_alchemy.utils.fixtures import iter_fixture_async


    async def seed_products_in_batches(fixtures_path: Path = Path("fixtures")) -> None:
        async with async_config.get_session() as db_session:
            repo = AsyncProductRepository(session=db_session)
            async for batch in iter_fixture_async(fixtures_path, "products", batch_size=500):
                await repo.add_many([AsyncProduct(**row) for row in batch], auto_commit=True)

A JSON array is decoded one file at a time, so prefer JSON Lines or sharded files for very large fixtures.

Sharded Fixtures
----------------

A large fixture can be split into numbered shards, such as ``products.001.jsonl.gz``, ``products.002.jsonl.gz``, and so on. Every shard is a complete file on its own, and shards may use different compression. The loaders read shards in numeric order and return their records as one list, and the iterators yield those records in batches that may span shard boundaries. A ``ValueError`` is raised when the numbers do not run ``1, 2, 3, ...`` without gaps, when two shards share a number, when an unsharded file and shards exist side by side, or when a JSON shard is not an array.

Writing Fixtures With Automatic Rollover
----------------------------------------

``write_fixture_sync`` and ``write_fixture_async`` write records one at a time in the chosen ``file_format`` and ``compression``. Set ``max_bytes`` (the size of each file on disk) or ``max_records`` to roll over to a new shard automatically:

.. code-block:: python

    import tempfile
    from advanced_alchemy.utils.fixtures import iter_fixture_sync, write_fixture_sync

    with tempfile.TemporaryDirectory() as tmp_dir:
        users = [{"id": index, "name": f"user-{index}"} for index in range(1, 6)]
        paths = write_fixture_sync(Path(tmp_dir), "users", users, file_format="jsonl", compression="gzip", max_records=2)
        assert [path.name for path in paths] == ["users.001.jsonl.gz", "users.002.jsonl.gz", "users.003.jsonl.gz"]
        assert open_fixture_sync(Path(tmp_dir), "users") == users
        assert [len(batch) for batch in iter_fixture_sync(Path(tmp_dir), "users", batch_size=4)] == [4, 1]

Files are written to temporary names first. Only after every record is written does the writer remove the old files for that fixture name, in any format or shard layout, and move the new files into place. If writing fails, the existing fixture is left untouched. A single record larger than ``max_bytes`` is written to its own shard with a ``UserWarning``. ``write_fixture_async`` also accepts an async iterable of records.

Safe Re-Runs Across Deployments
-------------------------------

Use ``upsert_many`` instead of ``add_many`` when a seed script runs on every deployment so existing rows are updated cleanly without duplicate errors:

.. code-block:: python

    async def seed_roles(role_service: Any, fixtures_path: Path) -> None:
        rows = await open_fixture_async(fixtures_path, "role")
        await role_service.upsert_many(match_fields=["name"], data=rows, auto_commit=True)

.. tip::

    Seed parent tables (like ``Author``) before child tables (like ``Post``), export existing tables with :doc:`dump-data <cli_commands>`, and consider `Polyfactory <https://github.com/litestar-org/polyfactory>`__ when generating random test data in ``pytest``.

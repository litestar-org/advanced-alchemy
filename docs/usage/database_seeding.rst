====================================
Database Seeding and Fixture Loading
====================================

Advanced Alchemy provides utilities for seeding your database with initial data through JSON fixtures. This documentation will show you how to create and load fixtures in both synchronous and asynchronous applications.

Creating Fixtures
-----------------

Fixtures in Advanced Alchemy are simple JSON files that contain the data you want to seed. Each fixture file should:

1. Contain a JSON object or a JSON array of objects, where each object represents a row in your database table
2. Include all required fields for your model

**Example Fixture:**

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
        },
        {
            "name": "Headphones",
            "description": "Noise-cancelling wireless headphones with 30-hour battery life",
            "price": 199.99,
            "in_stock": true
        },
        {
            "name": "Smartwatch",
            "description": "Fitness tracker with heart rate monitor and GPS",
            "price": 149.99,
            "in_stock": false
        },
        {
            "name": "Tablet",
            "description": "10-inch tablet with high-resolution display",
            "price": 349.99,
            "in_stock": true
        }
    ]

Loading Fixtures
----------------

Advanced Alchemy provides both synchronous and asynchronous functions for loading fixtures:

Synchronous Loading
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from pathlib import Path

    from sqlalchemy import String, create_engine
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.config import SQLAlchemySyncConfig, SyncSessionConfig
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture

    # Database connection string
    DATABASE_URL = "sqlite:///db.sqlite3"

    config = SQLAlchemySyncConfig(
        engine_instance=create_engine(DATABASE_URL),
        session_config=SyncSessionConfig(expire_on_commit=False)
    )

    class Product(UUIDBase):
        """Product model."""
        __tablename__ = "products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[str | None] = mapped_column(String(length=500))
        price: Mapped[float]
        in_stock: Mapped[bool] = mapped_column(default=True)


    # Repository
    class ProductRepository(SQLAlchemySyncRepository[Product]):
        """Product repository."""
        model_type = Product


    # Set up fixtures path
    fixtures_path = Path(__file__).parent / "fixtures"


    def initialize_database():
        """Initialize the database and create tables."""
        print("Creating database tables...")
        with config.get_engine().begin() as conn:
            UUIDBase.metadata.create_all(conn)
        print("Tables created successfully")


    def seed_database():
        """Seed the database with fixture data."""
        print("Seeding database...")

        # Create a session
        with config.get_session() as db_session:
            # Create repository for product model
            product_repo = ProductRepository(session=db_session)

            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = open_fixture(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                product_repo.add_many([Product(**item) for item in product_data])
                db_session.commit()
            except FileNotFoundError:
                print(f"Could not find fixture file at {fixtures_path}/product.json")


    if __name__ == "__main__":
        # Initialize the database
        initialize_database()

        # Seed the database
        seed_database()


Asynchronous Loading
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import asyncio
    from pathlib import Path
    from typing import Optional

    from sqlalchemy import String
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture_async

    # Database connection string
    DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"

    config = SQLAlchemyAsyncConfig(
        engine_instance=create_async_engine(DATABASE_URL),
        session_config=AsyncSessionConfig(expire_on_commit=False)
    )

    class Product(UUIDBase):
        """Product model."""
        __tablename__ = "products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[Optional[str]] = mapped_column(String(length=500))
        price: Mapped[float]
        in_stock: Mapped[bool] = mapped_column(default=True)


    # Repository
    class ProductRepository(SQLAlchemyAsyncRepository[Product]):
        """Product repository."""
        model_type = Product


    # Set up fixtures path
    fixtures_path = Path(__file__).parent / "fixtures"


    async def initialize_database():
        """Initialize the database and create tables."""
        print("Creating database tables...")
        async with config.get_engine().begin() as conn:
            await conn.run_sync(UUIDBase.metadata.create_all)
        print("Tables created successfully")


    async def seed_database():
        """Seed the database with fixture data."""
        print("Seeding database...")

        # Create a session
        async with config.get_session() as db_session:
            # Create repository for product model
            product_repo = ProductRepository(session=db_session)

            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = await open_fixture_async(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                await product_repo.add_many([Product(**item) for item in product_data])
                await db_session.commit()
            except FileNotFoundError:
                print(f"Could not find fixture file at {fixtures_path}/product.json")



    async def main():
        """Main async function to run the example."""
        # Initialize the database
        await initialize_database()

        # Seed the database
        await seed_database()



    if __name__ == "__main__":
        # Run the async main function
        asyncio.run(main())


Integration with Web Frameworks
-------------------------------

Litestar
~~~~~~~~

.. code-block:: python

    from pathlib import Path
    from typing import Optional

    import uvicorn
    from litestar import Litestar
    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.extensions.litestar import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture_async

    # Database connection string
    DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"

    # Set up fixtures path
    fixtures_path = Path(__file__).parent / "fixtures"

    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string=DATABASE_URL,
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)


    class Product(UUIDBase):
        """Product model."""
        __tablename__ = "products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[Optional[str]] = mapped_column(String(length=500))
        price: Mapped[float]
        in_stock: Mapped[bool] = mapped_column(default=True)


    # Repository
    class ProductRepository(SQLAlchemyAsyncRepository[Product]):
        """Product repository."""
        model_type = Product


    # Startup function to seed the database
    async def on_startup() -> None:
        """Seed the database during application startup."""
        print("Running startup routine...")

        # Create a session and seed data
        async with sqlalchemy_config.get_session() as db_session:
            # Create repository for product model
            product_repo = ProductRepository(session=db_session)
            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = await open_fixture_async(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                await product_repo.add_many([Product(**item) for item in product_data])
                await db_session.commit()
            except FileNotFoundError:
                print(f"Could not find fixture file at {fixtures_path}/product.json")

            # Verify data was added
            products = await product_repo.list()
            print(f"Database seeded with {len(products)} products")


    # Create the Litestar application
    app = Litestar(
        on_startup=[on_startup],
        plugins=[alchemy],
    )

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)

FastAPI
~~~~~~~

.. code-block:: python

    from contextlib import asynccontextmanager
    from pathlib import Path
    from typing import Optional

    import uvicorn
    from fastapi import FastAPI
    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.extensions.fastapi import (
        AdvancedAlchemy,
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
    )
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture_async

    # Database connection string
    DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"

    # Set up fixtures path
    fixtures_path = Path(__file__).parent / "fixtures"


    class Product(UUIDBase):
        """Product model."""
        __tablename__ = "products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[Optional[str]] = mapped_column(String(length=500))
        price: Mapped[float]
        in_stock: Mapped[bool] = mapped_column(default=True)


    # Repository
    class ProductRepository(SQLAlchemyAsyncRepository[Product]):
        """Product repository."""
        model_type = Product


    # Lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Handle startup and shutdown events."""
        # Startup: Initialize database and seed data
        print("Running startup routine...")

        # Create a session and seed data
        async with sqlalchemy_config.get_session() as db_session:
            # Create repository for product model
            product_repo = ProductRepository(session=db_session)
            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = await open_fixture_async(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                await product_repo.add_many([Product(**item) for item in product_data])
                await db_session.commit()
            except FileNotFoundError:
                print(f"Could not find fixture file at {fixtures_path}/product.json")

            # Verify data was added
            products = await product_repo.list()
            print(f"Database seeded with {len(products)} products")

        # Yield control back to FastAPI
        yield

        # Shutdown: Clean up resources if needed
        # This section runs when the application is shutting down
        print("Shutting down...")


    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string=DATABASE_URL,
        commit_mode="autocommit",
        session_config=session_config,
        create_all=True,
    )

    # Create the FastAPI application with lifespan
    app = FastAPI(lifespan=lifespan)

    alchemy = AdvancedAlchemy(config=sqlalchemy_config, app=app)

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)

Flask
~~~~~

.. code-block:: python

    from pathlib import Path
    from typing import Optional

    from flask import Flask
    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        SQLAlchemySyncConfig,
        SyncSessionConfig,
    )
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture

    # Database connection string
    DATABASE_URL = "sqlite:///db.sqlite3"

    # Set up fixtures path
    fixtures_path = Path(__file__).parent / "fixtures"

    class Product(UUIDBase):
        """Product model."""
        __tablename__ = "products"

        name: Mapped[str] = mapped_column(String(length=100))
        description: Mapped[Optional[str]] = mapped_column(String(length=500))
        price: Mapped[float]
        in_stock: Mapped[bool] = mapped_column(default=True)


    # Repository
    class ProductRepository(SQLAlchemySyncRepository[Product]):
        """Product repository."""
        model_type = Product


    app = Flask(__name__)

    sqlalchemy_config = SQLAlchemySyncConfig(
        connection_string=DATABASE_URL,
        commit_mode="autocommit",
        session_config=SyncSessionConfig(
            expire_on_commit=False,
        ),
        create_all=True
    )

    db = AdvancedAlchemy(config=sqlalchemy_config)
    db.init_app(app)

    with app.app_context():  # noqa: SIM117
        # Seed data
        with db.get_session() as session:
            product_repo = ProductRepository(session=db_session)
            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = open_fixture(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                product_repo.add_many([Product(**item) for item in product_data])
                db_session.commit()
            except FileNotFoundError:
                print(f"Could not find fixture file at {fixtures_path}/product.json")

            # Verify data was added
            products = product_repo.list()
            print(f"Database seeded with {len(products)} products")

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=5000)


Best Practices
--------------

1. **Directory Structure**: Keep your fixtures in a dedicated directory (e.g., ``fixtures/``).
2. **Naming Convention**: Name your fixture files after the corresponding table names.
3. **Idempotent Seeding**: Always check if data exists before seeding to avoid duplicates or update records.
4. **Dependencies**: Seed tables in the correct order to respect foreign key constraints.
5. **Data Validation**: Ensure your fixture data meets your model's constraints.
6. **Environment Separation**: Consider having different fixtures for development, testing, and production.
7. **Version Control**: Keep your fixtures under version control with your application code.

Tips for Efficient Seeding
--------------------------

- Use :func:`add_many (async) <advanced_alchemy.repository.SQLAlchemyAsyncRepository.add_many>` / :func:`add_many (sync) <advanced_alchemy.repository.SQLAlchemySyncRepository.add_many>` instead of adding objects one by one for better performance.
- Use :func:`upsert_many (async) <advanced_alchemy.repository.SQLAlchemyAsyncRepository.upsert_many>` / :func:`upsert_many (sync) <advanced_alchemy.repository.SQLAlchemySyncRepository.upsert_many>` to update your data if you are updating prices for example.
- You can use the database seeding from your cli, app startup or any route.
- For large datasets, consider chunking the data into smaller batches.
- When dealing with relationships, seed parent records before child records.
- Consider using factory libraries like `Polyfactory <https://github.com/litestar-org/polyfactory>`__ for generating test data.

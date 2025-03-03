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
    from typing import Optional

    from sqlalchemy import String, create_engine
    from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture

    # Database connection string
    DATABASE_URL = "sqlite:///db.sqlite3"

    # Create engine and session maker
    engine = create_engine(DATABASE_URL)
    session_maker = sessionmaker(engine, expire_on_commit=False)


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


    # Set up fixtures path
    fixtures_path = Path(__file__).parent / "fixtures"


    def initialize_database():
        """Initialize the database and create tables."""
        print("Creating database tables...")
        UUIDBase.metadata.create_all(engine)
        print("Tables created successfully")


    def seed_database():
        """Seed the database with fixture data."""
        print("Seeding database...")

        # Create a session
        with session_maker() as session:
            # Create repository for product model
            product_repo = ProductRepository(session=session)

            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = open_fixture(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                product_repo.add_many([Product(**item) for item in product_data])
                session.commit()
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
    from typing import List, Optional

    from sqlalchemy import String
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture_async

    # Database connection string
    DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"

    # Create engine and session maker
    engine = create_async_engine(DATABASE_URL)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


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
        async with engine.begin() as conn:
            await conn.run_sync(UUIDBase.metadata.create_all)
        print("Tables created successfully")


    async def seed_database():
        """Seed the database with fixture data."""
        print("Seeding database...")
        
        # Create a session
        async with async_session_maker() as session:
            # Create repository for product model
            product_repo = ProductRepository(session=session)
            
            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = await open_fixture_async(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                await product_repo.add_many([Product(**item) for item in product_data])
                await session.commit()
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
    from litestar.contrib.sqlalchemy.base import UUIDBase
    from litestar.di import Provide
    from sqlalchemy import String
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture_async

    # Database connection string
    DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"

    # Create engine and session maker
    engine = create_async_engine(DATABASE_URL)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


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


    # Dependency provider
    async def provide_db_session() -> AsyncSession: # type: ignore
        """Provide a database session."""
        async with async_session_maker() as session:
            yield session


    # Startup function to seed the database
    async def on_startup() -> None:
        """Seed the database during application startup."""
        print("Running startup routine...")

        # Create tables
        print("Creating database tables...")
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(UUIDBase.metadata.create_all)

        print("Tables created successfully")

        # Create a session and seed data
        async with async_session_maker() as session:
            # Create repository for product model
            product_repo = ProductRepository(session=session)
            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = await open_fixture_async(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                await product_repo.add_many([Product(**item) for item in product_data])
                await session.commit()
            except FileNotFoundError:
                print(f"Could not find fixture file at {fixtures_path}/product.json")

            # Verify data was added
            products = await product_repo.list()
            print(f"Database seeded with {len(products)} products")


    # Create the Litestar application
    app = Litestar(
        on_startup=[on_startup],
        dependencies={"db_session": Provide(provide_db_session)},
    )

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000)

FastAPI
~~~~~~~

.. code-block:: python

    from pathlib import Path
    from typing import Optional, AsyncGenerator
    from contextlib import asynccontextmanager

    import uvicorn
    from fastapi import FastAPI, Depends
    from sqlalchemy import String
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture_async

    # Database connection string
    DATABASE_URL = "sqlite+aiosqlite:///db.sqlite3"

    # Create engine and session maker
    engine = create_async_engine(DATABASE_URL)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


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


    # Dependency provider
    async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
        """Provide a database session."""
        async with async_session_maker() as session:
            try:
                yield session
            finally:
                await session.close()


    # Lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Handle startup and shutdown events."""
        # Startup: Initialize database and seed data
        print("Running startup routine...")

        # Create tables
        print("Creating database tables...")
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(UUIDBase.metadata.create_all)

        print("Tables created successfully")

        # Create a session and seed data
        async with async_session_maker() as session:
            # Create repository for product model
            product_repo = ProductRepository(session=session)
            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = await open_fixture_async(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                await product_repo.add_many([Product(**item) for item in product_data])
                await session.commit()
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


    # Create the FastAPI application with lifespan
    app = FastAPI(lifespan=lifespan)


    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8000) 

Flask
~~~~~

.. code-block:: python

    from pathlib import Path
    from typing import Generator, Optional

    from flask import Flask
    from sqlalchemy import String, create_engine
    from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from advanced_alchemy.utils.fixtures import open_fixture

    # Database connection string
    DATABASE_URL = "sqlite:///db.sqlite3"

    # Create engine and session maker
    engine = create_engine(DATABASE_URL)
    session_maker = sessionmaker(engine, expire_on_commit=False)


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


    # Set up fixtures path
    fixtures_path = Path(__file__).parent / "fixtures"


    # Dependency provider
    def get_db_session() -> Generator[Session, None, None]:
        """Provide a database session."""
        session = session_maker()
        try:
            yield session
        finally:
            session.close()


    # Initialize database and seed data
    def init_db() -> None:
        """Initialize the database and seed it with data."""
        print("Running database initialization...")

        # Create tables
        print("Creating database tables...")
        UUIDBase.metadata.create_all(engine)
        print("Tables created successfully")

        # Create a session and seed data
        with session_maker() as session:
            # Create repository for product model
            product_repo = ProductRepository(session=session)
            
            # Load and add product data
            try:
                print(f"Attempting to load fixtures from {fixtures_path}/product.json")
                product_data = open_fixture(fixtures_path, "product")
                print(f"Loaded {len(product_data)} products from fixture")
                product_repo.add_many([Product(**item) for item in product_data])
                session.commit()
            except FileNotFoundError:
                print(f"Could not find fixture file at {fixtures_path}/product.json")

            # Verify data was added
            products = product_repo.list()
            print(f"Database seeded with {len(products)} products")


    # Create the Flask application with app factory pattern
    def create_app():
        """Create and configure the Flask application."""
        app = Flask(__name__)
        
        # Initialize the database when the app is created
        with app.app_context():
            init_db()
        
        return app


    # Create the app instance
    app = create_app()

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=5000, debug=True) 


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

- Use :func:`add_many (async) <advanced_alchemy.repository.SQLAlchemyAsyncRepositoryProtocol.add_many>` / :func:`add_many (sync) <advanced_alchemy.repository.SQLAlchemySyncRepositoryProtocol.add_many>` instead of adding objects one by one for better performance.
- Use :func:`upsert_many (async) <advanced_alchemy.repository.SQLAlchemyAsyncRepositoryProtocol.upsert_many>` / :func:`upsert_many (sync) <advanced_alchemy.repository.SQLAlchemySyncRepositoryProtocol.upsert_many>` to update your data if you are updating prices for example.
- You can use the database seeding from your cli, app startup or any route.
- For large datasets, consider chunking the data into smaller batches.
- When dealing with relationships, seed parent records before child records.
- Consider using factory libraries like `Polyfactory <https://github.com/litestar-org/polyfactory>`__ for generating test data.

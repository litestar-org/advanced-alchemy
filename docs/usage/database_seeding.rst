====================================
Database Seeding and Fixture Loading
====================================

Advanced Alchemy provides utilities for seeding your database with initial data through JSON fixtures. This documentation will show you how to create and load fixtures in both synchronous and asynchronous applications.

Creating Fixtures
-----------------

Fixtures in Advanced Alchemy are simple JSON files that contain the data you want to seed. Each fixture file should:

1. Contain a JSON array of objects, where each object represents a row in your database table
2. Include all required fields for your model

**Example Fixture:**

.. code-block:: json
    :caption: fixtures/products.json

    [
      {
        "name": "Product 1",
        "description": "Description for product 1",
        "price": 19.99,
        "in_stock": true
      },
      {
        "name": "Product 2",
        "description": "Description for product 2",
        "price": 29.99,
        "in_stock": false
      }
    ]

Loading Fixtures
----------------

Advanced Alchemy provides both synchronous and asynchronous functions for loading fixtures:

Synchronous Loading
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from pathlib import Path
    from advanced_alchemy.utils.fixtures import open_fixture
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from your_app.models import Product

    # Define the path where your fixtures are stored
    fixtures_path = Path("path/to/fixtures")

    # Inside a session context
    def seed_database(session):
        # Create repository
        product_repo = SQLAlchemySyncRepository[Product](session=session, model_type=Product)
        
        # Load fixture
        fixture_data = open_fixture(fixtures_path, "products")
        
        # Create objects from fixture data
        products = [Product(**item) for item in fixture_data]
        
        # Add to database
        product_repo.add_many(products)
        session.commit()

Asynchronous Loading
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import asyncio
    from pathlib import Path
    from advanced_alchemy.utils.fixtures import open_fixture_async
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from your_app.models import Product

    # Define the path where your fixtures are stored
    fixtures_path = Path("path/to/fixtures")

    # Inside an async session context
    async def seed_database(async_session):
        # Create repository
        product_repo = SQLAlchemyAsyncRepository[Product](session=async_session, model_type=Product)
        
        # Load fixture asynchronously
        fixture_data = await open_fixture_async(fixtures_path, "products")
        
        # Create objects from fixture data
        products = [Product(**item) for item in fixture_data]
        
        # Add to database
        await product_repo.add_many(products)
        await async_session.commit()

Integration with Web Frameworks
-------------------------------

.. note::

    You can use ``upsert_many`` to update data instead of ``add_many`` in the examples below.
    

Litestar
~~~~~~~~

.. code-block:: python

    from pathlib import Path
    from litestar import Litestar
    from litestar.plugins.sqlalchemy import SQLAlchemyPlugin, SQLAlchemyAsyncConfig
    from advanced_alchemy.utils.fixtures import open_fixture_async
    from your_app.models import Product, Base

    fixtures_path = Path("fixtures")

    async def on_startup(app: Litestar) -> None:
        """Seed the database during application startup."""
        async with app.state.db_plugin.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        async with app.state.db_plugin.get_session() as session:
            from advanced_alchemy.repository import SQLAlchemyAsyncRepository
            
            # Create repositories for each model you want to seed
            product_repo = SQLAlchemyAsyncRepository[Product](session=session, model_type=Product)
            
            # Load and add data for each model
            product_data = await open_fixture_async(fixtures_path, "products")
            await product_repo.add_many([Product(**item) for item in product_data])
            
            await session.commit()

    app = Litestar(
        on_startup=[on_startup],
        plugins=[
            SQLAlchemyPlugin(
                config=SQLAlchemyAsyncConfig(
                    connection_string="sqlite+aiosqlite:///db.sqlite3"
                )
            )
        ]
    )

FastAPI
~~~~~~~

.. code-block:: python

    from fastapi import FastAPI, Depends
    from pathlib import Path
    from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig
    from advanced_alchemy.utils.fixtures import open_fixture_async
    from sqlalchemy.ext.asyncio import AsyncSession
    from your_app.models import Product, Base

    app = FastAPI()
    fixtures_path = Path("fixtures")

    # Setup database
    alchemy = AdvancedAlchemy(
        config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///db.sqlite3"),
        app=app,
    )

    @app.on_event("startup")
    async def seed_database():
        # Create tables
        async with alchemy.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # Seed data
        async with alchemy.get_session() as session:
            from advanced_alchemy.repository import SQLAlchemyAsyncRepository
            
            # Check if data already exists to avoid duplicates
            product_repo = SQLAlchemyAsyncRepository[Product](session=session, model_type=Product)
            count = await product_repo.count()
            
            if count == 0:  # Only seed if no data exists
                product_data = await open_fixture_async(fixtures_path, "products")
                await product_repo.add_many([Product(**item) for item in product_data])
                await session.commit()

Flask
~~~~~

.. code-block:: python

    from flask import Flask
    from pathlib import Path
    from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig
    from advanced_alchemy.utils.fixtures import open_fixture
    from your_app.models import Product, Base

    app = Flask(__name__)
    fixtures_path = Path("fixtures")

    # Setup database
    alchemy = AdvancedAlchemy(
        config=SQLAlchemySyncConfig(connection_string="sqlite:///db.sqlite3"),
        app=app,
    )

    @app.before_first_request
    def seed_database():
        # Create tables
        Base.metadata.create_all(alchemy.engine)
        
        # Seed data
        with alchemy.get_session() as session:
            from advanced_alchemy.repository import SQLAlchemySyncRepository
            
            # Check if data already exists to avoid duplicates
            product_repo = SQLAlchemySyncRepository[Product](session=session, model_type=Product)
            count = product_repo.count()
            
            if count == 0:  # Only seed if no data exists
                product_data = open_fixture(fixtures_path, "products")
                product_repo.add_many([Product(**item) for item in product_data])
                session.commit()
    

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

- Use ``add_many()`` instead of adding objects one by one for better performance.
- Use ``upsert_many()`` to update your data if you are updating prices for example.
- You can use the database seeding from your cli, app startup or any route.
- For large datasets, consider chunking the data into smaller batches.
- When dealing with relationships, seed parent records before child records.
- Consider using factory libraries like Polyfactory for generating test data.
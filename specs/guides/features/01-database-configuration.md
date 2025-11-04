# Guide: Database Configuration

`advanced-alchemy` provides a flexible and robust configuration system for setting up your database connection and session management. It uses dataclasses to define configuration objects, making them easy to create, customize, and type-check.

## Core Configuration Objects

There are two main configuration classes, one for asynchronous applications and one for synchronous applications:

-   `SQLAlchemyAsyncConfig`: For `asyncio`-based applications.
-   `SQLAlchemySyncConfig`: For traditional synchronous applications.

These configuration objects are the central point for setting up the database engine and session maker.

## Key Configuration Parameters

Both `SQLAlchemyAsyncConfig` and `SQLAlchemySyncConfig` share a common set of parameters, with types adjusted for their respective async/sync nature.

-   `connection_string`: The database connection URL. This is the only required parameter.
-   `engine_config`: A dictionary of options to pass to the SQLAlchemy `create_engine` or `create_async_engine` function. This is where you can configure things like connection pooling, statement logging, etc.
-   `session_config`: A `SyncSessionConfig` or `AsyncSessionConfig` object to configure the `sessionmaker`. You can set options like `expire_on_commit`.
-   `alembic_config`: An `AlembicSyncConfig` or `AlembicAsyncConfig` object for configuring Alembic database migrations.

## Creating a Database Engine and Session Maker

The primary role of the configuration object is to create a SQLAlchemy Engine and a session maker.

-   `create_engine()`: Returns a SQLAlchemy `Engine` or `AsyncEngine`.
-   `create_session_maker()`: Returns a SQLAlchemy `sessionmaker` or `async_sessionmaker`.

### Async Configuration Example

This example demonstrates how to configure an asynchronous connection to a PostgreSQL database using `psycopg`.

```python
from advanced_alchemy.config import SQLAlchemyAsyncConfig

# 1. Create the configuration object
db_config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+psycopg://user:pass@host:port/db",
)

# 2. Create the engine
async_engine = db_config.create_engine()

# 3. Create the session maker
AsyncSessionLocal = db_config.create_session_maker()

# 4. Use the session maker to get a session
async with AsyncSessionLocal() as session:
    # ... use the session
    pass
```

### Sync Configuration Example

This example shows how to configure a synchronous connection to an in-memory SQLite database.

```python
from advanced_alchemy.config import SQLAlchemySyncConfig

# 1. Create the configuration object
db_config = SQLAlchemySyncConfig(
    connection_string="sqlite:///:memory:",
)

# 2. Create the engine
sync_engine = db_config.create_engine()

# 3. Create the session maker
SyncSessionLocal = db_config.create_session_maker()

# 4. Use the session maker to get a session
with SyncSessionLocal() as session:
    # ... use the session
    pass
```

## Using the `get_session` Context Manager

The configuration objects also provide a convenient context manager called `get_session()` that handles session creation and closing for you. This is particularly useful for standalone scripts or simple applications.

**Async Example:**

```python
async with db_config.get_session() as session:
    # ... do work with the session
    result = await session.execute(...)
```

**Sync Example:**

```python
with db_config.get_session() as session:
    # ... do work with the session
    result = session.execute(...)
```

This guide covers the essentials of database configuration in `advanced-alchemy`. By using these configuration objects, you can ensure a consistent and reliable setup for your database interactions.

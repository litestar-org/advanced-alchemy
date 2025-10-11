# SQLite

SQLite driver configuration and Advanced Alchemy-specific patterns.

## Drivers

### aiosqlite (Async)

```bash
uv add aiosqlite
```

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///database.sqlite"
)
```

### sqlite3 (Sync)

Python's built-in SQLite driver:

```python
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig

config = SQLAlchemySyncConfig(
    connection_string="sqlite:///database.sqlite"
)
```

## Connection Strings

```python
# File-based (async)
config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///path/to/database.sqlite"
)

# In-memory (async)
config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///:memory:"
)

# Shared in-memory (for multi-connection tests)
config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared&uri=true"
)
```

## WAL Mode for Better Concurrency

```python
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

def configure_sqlite_wal(engine: "AsyncEngine") -> None:
    """Enable WAL mode for better concurrency."""

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

# Apply after engine creation
configure_sqlite_wal(plugin.engine)
```

## Advanced Alchemy Type Mappings

### JSON Storage (No Native JSONB)

SQLite stores JSON as text. Use Advanced Alchemy's `JsonB` type:

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import JsonB
from sqlalchemy.orm import Mapped, mapped_column

class Post(UUIDAuditBase):
    __tablename__ = "posts"

    title: "Mapped[str]"
    tags: "Mapped[list[str]]" = mapped_column(JsonB, default=list)
```

**Query JSON:**

```python
from sqlalchemy import func, select

# Extract JSON value (SQLite 3.38+)
stmt = select(Post).where(
    func.json_extract(Post.tags, "$").contains("python")
)

# Get array length
stmt = select(Post).where(
    func.json_array_length(Post.tags) > 3
)
```

### UUID Storage

SQLite stores UUIDs as strings:

```python
from advanced_alchemy.base import UUIDBase

class User(UUIDBase):
    """UUID stored as CHAR(36) in SQLite."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True)
    name: "Mapped[str]"
```

## Upsert Operations

Advanced Alchemy automatically uses SQLite's `ON CONFLICT`:

```python
# Single upsert
user = await repository.upsert(
    {"email": "user@example.com", "name": "John"},
    match_fields=["email"]
)

# Bulk upsert
users = await repository.upsert_many(
    users_data,
    match_fields=["email"]
)
```

## Connection Pooling

SQLite works best with single connection:

```python
config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///database.sqlite",
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=False,
)
```

## pytest Markers

```python
import pytest

@pytest.mark.aiosqlite
async def test_async_sqlite_feature(aiosqlite_engine):
    """Test async SQLite-specific functionality."""
    pass

@pytest.mark.sqlite
def test_sync_sqlite_feature(sqlite_engine):
    """Test sync SQLite functionality."""
    pass
```

Run tests:

```bash
# Run only async SQLite tests
uv run pytest tests/ -m aiosqlite -v

# Run all SQLite tests (async and sync)
uv run pytest tests/ -m "sqlite or aiosqlite" -v
```

## Common Gotchas

### No Concurrent Writes

SQLite locks the entire database for writes:

```python
# ❌ Concurrent writes wait/timeout
async def concurrent_writes():
    await repository1.create(user1)
    await repository2.create(user2)  # Must wait

# ✅ Use single transaction
async with session.begin():
    await repository.create(user1)
    await repository.create(user2)
```

### Foreign Key Enforcement

SQLite requires explicit foreign key enforcement:

```python
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

### No Native Array Support

Use JSON for arrays:

```python
# Store arrays as JSON
tags: "Mapped[list[str]]" = mapped_column(JsonB, default=list)
```

## Performance Tips

### Batch Operations

```python
# ✅ Bulk insert (single transaction)
users = await repository.create_many([
    {"email": "user1@example.com", "name": "User 1"},
    {"email": "user2@example.com", "name": "User 2"},
])

# ❌ Individual inserts (multiple transactions)
for user_data in users_data:
    await repository.create(user_data)  # Slower
```

### Optimize Pragma Settings

```python
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")      # 64MB cache
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()
```

## See Also

- [PostgreSQL Guide](../database-backends/postgresql.md) - Migration target for production
- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [SQLite Documentation](https://www.sqlite.org/docs.html) - Official SQLite docs
- [aiosqlite Documentation](https://aiosqlite.omnilib.dev/) - Async driver docs
- [SQLite JSON Functions](https://www.sqlite.org/json1.html) - JSON support details

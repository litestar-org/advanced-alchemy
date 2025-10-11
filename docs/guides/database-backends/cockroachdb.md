# CockroachDB

CockroachDB driver configuration and Advanced Alchemy-specific patterns.

## Drivers

CockroachDB uses PostgreSQL-compatible drivers with the `sqlalchemy-cockroachdb` dialect:

### asyncpg (Async)

```bash
uv add asyncpg sqlalchemy-cockroachdb
```

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="cockroachdb+asyncpg://user:password@localhost:26257/dbname"
)
```

### psycopg (Sync/Async)

```bash
uv add "psycopg[binary,pool]" sqlalchemy-cockroachdb
```

```python
# Async
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="cockroachdb+psycopg://user:password@localhost:26257/dbname"
)

# Sync
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig

config = SQLAlchemySyncConfig(
    connection_string="cockroachdb+psycopg://user:password@localhost:26257/dbname"
)
```

## Advanced Alchemy-Specific Patterns

### UUID Primary Keys

UUID primary keys avoid transaction contention hotspots in distributed systems:

```python
from advanced_alchemy.base import UUIDAuditBase

class User(UUIDAuditBase):
    """Uses UUID primary key."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True)
    name: "Mapped[str]"
```

**UUID characteristics in CockroachDB:**
- Sequential primary keys create hotspots in distributed systems
- UUIDs distribute writes across nodes
- No central counter coordination required

### Transaction Retry Logic

CockroachDB uses serializable isolation by default and may require automatic transaction retries:

```python
from sqlalchemy.exc import DBAPIError

async def create_with_retry(repository, data, max_retries=3):
    """Create with automatic retry on serialization errors."""
    for attempt in range(max_retries):
        try:
            return await repository.create(data)
        except DBAPIError as e:
            # CockroachDB retry error code: 40001
            if "40001" in str(e.orig) and attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt * 0.1)
                continue
            raise
```

### PostgreSQL Compatibility

CockroachDB supports most PostgreSQL features. See the [PostgreSQL guide](postgresql.md) for:
- JSONB support
- Array types
- UUID types
- ON CONFLICT upserts

### Upsert Operations

Advanced Alchemy automatically uses CockroachDB's `ON CONFLICT`:

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

## pytest Markers

```python
import pytest

@pytest.mark.cockroachdb_async
async def test_create_user_cockroachdb(cockroachdb_asyncpg_url: str):
    """Test user creation on CockroachDB with asyncpg."""
    pass

@pytest.mark.cockroachdb_sync
def test_transaction_retry_cockroachdb(cockroachdb_psycopg_url: str):
    """Test transaction retry logic on CockroachDB."""
    pass
```

Run tests:

```bash
# Run only CockroachDB tests
uv run pytest tests/ -m "cockroachdb_async or cockroachdb_sync" -v
```

## Connection Pooling

```python
config = SQLAlchemyAsyncConfig(
    connection_string="cockroachdb+asyncpg://user:pass@localhost:26257/db",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

## Docker Setup

```bash
# Single-node development
docker run -d \
  --name cockroach-dev \
  -p 26257:26257 \
  -p 8080:8080 \
  cockroachdb/cockroach:latest \
  start-single-node \
  --insecure

# Access web UI: http://localhost:8080
# Connection: cockroachdb+asyncpg://root@localhost:26257/defaultdb?sslmode=disable
```

## Key Differences

### Sequential Primary Keys

Sequential primary keys create transaction contention in distributed systems:

```python
# Sequential IDs create hotspots
class Order(BigIntBase):
    __tablename__ = "orders"

# UUIDs distribute writes across nodes
class Order(UUIDAuditBase):
    __tablename__ = "orders"
```

### Transaction Serialization Errors

Implement retry logic for contention errors (error code 40001).

## See Also

- [PostgreSQL Guide](postgresql.md) - CockroachDB is PostgreSQL-compatible
- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [CockroachDB Documentation](https://www.cockroachlabs.com/docs/) - Official docs
- [CockroachDB Best Practices](https://www.cockroachlabs.com/docs/stable/performance-best-practices-overview.html) - Performance guide
- [sqlalchemy-cockroachdb](https://github.com/cockroachdb/sqlalchemy-cockroachdb) - Dialect documentation

# PostgreSQL

PostgreSQL driver configuration and Advanced Alchemy-specific patterns.

## Drivers

### asyncpg (Async)

```bash
uv add asyncpg
```

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:password@localhost:5432/dbname"
)
```

### psycopg (Async/Sync)

```bash
uv add "psycopg[binary,pool]"
```

```python
# Async
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+psycopg://user:password@localhost:5432/dbname"
)

# Sync
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig

config = SQLAlchemySyncConfig(
    connection_string="postgresql://user:password@localhost:5432/dbname"
)
```

## Advanced Alchemy Type Mappings

### JSONB

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import JsonB
from sqlalchemy.orm import Mapped, mapped_column

class Document(UUIDAuditBase):
    __tablename__ = "documents"

    metadata: "Mapped[dict[str, Any]]" = mapped_column(JsonB)
    tags: "Mapped[list[str]]" = mapped_column(JsonB, default=list)
```

**Query JSONB:**

```python
from sqlalchemy import func, select

# Check if key exists
stmt = select(Document).where(
    Document.metadata["status"].as_string() == "active"
)

# Array contains
stmt = select(Document).where(
    Document.tags.contains(["python", "sqlalchemy"])
)

# JSONB path query
stmt = select(Document).where(
    func.jsonb_path_exists(Document.metadata, "$.user.email")
)
```

### Arrays

```python
from sqlalchemy import ARRAY, String, Integer

class Post(UUIDAuditBase):
    __tablename__ = "posts"

    tags: "Mapped[list[str]]" = mapped_column(ARRAY(String), default=list)
    view_counts: "Mapped[list[int]]" = mapped_column(ARRAY(Integer), default=list)
```

**Query arrays:**

```python
# Array contains
posts = await repository.list(Post.tags.contains(["python"]))

# Array overlap
posts = await repository.list(Post.tags.overlap(["python", "web"]))

# Array length
posts = await repository.list(func.array_length(Post.tags, 1) > 3)
```

### UUID Primary Keys

```python
from advanced_alchemy.base import UUIDBase

class User(UUIDBase):
    """Uses PostgreSQL UUID type for primary key."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True)
    name: "Mapped[str]"
```

## Upsert Operations

Advanced Alchemy automatically uses PostgreSQL's `ON CONFLICT`:

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

```python
config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost/db",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

## pytest Markers

```python
import pytest

@pytest.mark.asyncpg
async def test_create_user_postgresql(asyncpg_engine):
    """Test PostgreSQL-specific features with asyncpg."""
    pass

@pytest.mark.psycopg_async
async def test_jsonb_query_postgresql(psycopg_async_engine):
    """Test JSONB querying on PostgreSQL."""
    pass
```

Run tests:

```bash
# Run only asyncpg tests
uv run pytest tests/ -m asyncpg -v

# Run only psycopg tests
uv run pytest tests/ -m psycopg_async -v
```

## Common Gotchas

### RETURNING Clause

Advanced Alchemy uses RETURNING by default to fetch generated values:

```python
# Automatically uses RETURNING
user = await repository.create({"email": "user@example.com"})
# user.id and server defaults are populated immediately
```

### Indexes

```python
from sqlalchemy import Index, func

class User(UUIDAuditBase):
    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True, index=True)
    name: "Mapped[str]"
    metadata: "Mapped[dict]" = mapped_column(JsonB)

    __table_args__ = (
        # GIN index for JSONB
        Index("ix_user_metadata", "metadata", postgresql_using="gin"),
        # B-tree index for text search
        Index("ix_user_name_lower", func.lower(name)),
    )
```

## Docker Setup

```bash
docker run -d \
  --name postgres-test \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=testdb \
  -p 5432:5432 \
  postgres:16
```

## See Also

- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Litestar Playbook](../quick-reference/litestar-playbook.md) - Framework integration
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [PostgreSQL Documentation](https://www.postgresql.org/docs/) - Official PostgreSQL docs
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/) - asyncpg driver docs
- [psycopg Documentation](https://www.psycopg.org/psycopg3/docs/) - psycopg driver docs

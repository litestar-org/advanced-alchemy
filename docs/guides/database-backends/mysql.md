# MySQL/MariaDB

MySQL and MariaDB driver configuration and Advanced Alchemy-specific patterns.

## Drivers

### asyncmy (Async)

```bash
uv add asyncmy
```

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="mysql+asyncmy://user:password@localhost:3306/dbname?charset=utf8mb4"
)
```

### mysqlclient (Sync)

```bash
uv add mysqlclient
```

```python
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig

config = SQLAlchemySyncConfig(
    connection_string="mysql+mysqldb://user:password@localhost:3306/dbname?charset=utf8mb4"
)
```

**Important:** Always use `charset=utf8mb4` for full Unicode support (including emojis).

## Advanced Alchemy Type Mappings

### JSON Support

MySQL uses `JSON` type (not `JSONB`). Advanced Alchemy's `JsonB` maps to MySQL's `JSON` automatically:

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import JsonB
from sqlalchemy.orm import Mapped, mapped_column

class Document(UUIDAuditBase):
    __tablename__ = "documents"

    metadata: "Mapped[dict[str, Any]]" = mapped_column(JsonB)
    tags: "Mapped[list[str]]" = mapped_column(JsonB, default=list)
```

**Query JSON:**

```python
from sqlalchemy import func

# Extract JSON field
stmt = select(Document).where(
    func.json_extract(Document.metadata, "$.status") == "active"
)

# Array contains
stmt = select(Document).where(
    func.json_contains(Document.tags, '"python"')
)
```

### UUID Storage

MySQL stores UUIDs as BINARY(16):

```python
from advanced_alchemy.base import UUIDBase

class User(UUIDBase):
    """Stores UUID as BINARY(16) in MySQL."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True)
```

### AUTO_INCREMENT Primary Keys

```python
from advanced_alchemy.base import BigIntBase

class User(BigIntBase):
    """Uses AUTO_INCREMENT for primary key."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True)
```

## Upsert Operations

Advanced Alchemy uses MySQL's `ON DUPLICATE KEY UPDATE`:

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
    connection_string="mysql+asyncmy://user:pass@localhost/db?charset=utf8mb4",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,  # Important: recycle before MySQL timeout
    pool_pre_ping=True,
)
```

**Note:** MySQL closes idle connections after `wait_timeout` (default 8 hours). Set `pool_recycle` to less than this value.

## pytest Markers

```python
import pytest

@pytest.mark.asyncmy
async def test_create_user_mysql(asyncmy_engine):
    """Test user creation on MySQL with asyncmy."""
    pass

@pytest.mark.mysql
def test_sync_mysql(mysql_engine):
    """Test sync MySQL operations."""
    pass
```

Run tests:

```bash
# Run only MySQL tests
uv run pytest tests/ -m "asyncmy or mysql" -v
```

## Common Gotchas

### Character Encoding

Always specify utf8mb4:

```python
connection_string = "mysql+asyncmy://user:pass@localhost/db?charset=utf8mb4"
```

### Case Sensitivity

MySQL table/column names are case-sensitive on Unix/Linux but case-insensitive on Windows/macOS. Use lowercase:

```python
class User(UUIDAuditBase):
    __tablename__ = "users"  # lowercase
```

### Index Length Limits

MySQL has index length limits (767 bytes for InnoDB):

```python
# Limit string length for indexed columns
email: "Mapped[str]" = mapped_column(String(255), unique=True)

# Or specify index prefix length
__table_args__ = (
    Index("ix_long_field", "long_field", mysql_length=100),
)
```

## Docker Setup

```bash
# MySQL 8.0
docker run -d \
  --name mysql-test \
  -e MYSQL_ROOT_PASSWORD=test \
  -e MYSQL_DATABASE=testdb \
  -e MYSQL_USER=testuser \
  -e MYSQL_PASSWORD=testpass \
  -p 3306:3306 \
  mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

# MariaDB 11.0
docker run -d \
  --name mariadb-test \
  -e MARIADB_ROOT_PASSWORD=test \
  -e MARIADB_DATABASE=testdb \
  -e MARIADB_USER=testuser \
  -e MARIADB_PASSWORD=testpass \
  -p 3306:3306 \
  mariadb:11.0
```

## See Also

- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [MySQL Documentation](https://dev.mysql.com/doc/) - Official MySQL docs
- [MariaDB Documentation](https://mariadb.com/kb/en/documentation/) - Official MariaDB docs
- [asyncmy Documentation](https://github.com/long2ice/asyncmy) - Driver docs

# Oracle Database

Oracle Database driver configuration and Advanced Alchemy-specific patterns.

## Driver

### python-oracledb (Sync/Async)

```bash
uv add "oracledb>=2.4.1"
```

Thin mode requires no Oracle Client installation.

```python
# Async
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="oracle+oracledb://user:password@host:1521/?service_name=ORCLPDB1"
)

# Sync
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig

config = SQLAlchemySyncConfig(
    connection_string="oracle+oracledb://user:password@host:1521/?service_name=ORCLPDB1"
)
```

## Connection Strings

```python
# Standard connection
connection_string = "oracle+oracledb://user:password@host:1521/?service_name=ORCLPDB1"

# With TNS alias
connection_string = "oracle+oracledb://user:password@tns_alias"

# Easy Connect syntax
connection_string = "oracle+oracledb://user:password@//host:1521/service_name"
```

## Advanced Alchemy-Specific Patterns

### String Length Constraints

Oracle VARCHAR2 has a 4000-byte limit. **Always specify lengths explicitly**:

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class User(UUIDAuditBase):
    __tablename__ = "users"

    # ✅ Always specify length
    email: "Mapped[str]" = mapped_column(String(255), unique=True)
    name: "Mapped[str]" = mapped_column(String(200))

    # ❌ Will fail - no length specified
    # username: "Mapped[str]" = mapped_column(String)
```

### Use CLOB for Large Text

```python
from sqlalchemy import Text

class Article(UUIDAuditBase):
    __tablename__ = "articles"

    title: "Mapped[str]" = mapped_column(String(500))
    content: "Mapped[str]" = mapped_column(Text)  # Maps to CLOB
```

### Primary Key Strategies

**Sequence-Based (Traditional):**

```python
from advanced_alchemy.base import BigIntBase

class User(BigIntBase):
    """Uses sequence-generated BigInt primary key."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(String(255), unique=True)
    name: "Mapped[str]" = mapped_column(String(200))
```

**IDENTITY Columns (Oracle 12c+):**

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import Identity, Integer
from sqlalchemy.orm import Mapped, mapped_column

class User(UUIDAuditBase):
    """Uses Oracle IDENTITY column."""

    __tablename__ = "users"

    # Override id with IDENTITY
    id: "Mapped[int]" = mapped_column(
        Integer,
        Identity(start=1, increment=1),
        primary_key=True,
    )
    email: "Mapped[str]" = mapped_column(String(255), unique=True)
```

**UUID Primary Keys:**

```python
from advanced_alchemy.base import UUIDBase

class User(UUIDBase):
    """Uses UUID primary key (stored as RAW(16))."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(String(255), unique=True)
```

### UPSERT with MERGE

Advanced Alchemy automatically uses Oracle's `MERGE` statement:

```python
# Single upsert
user = await repository.upsert(
    {"email": "user@example.com", "name": "John Doe"},
    match_fields=["email"],
)

# Bulk upsert
users = await repository.upsert_many(
    users_data,
    match_fields=["email"],
)
```

## pytest Markers

```python
import pytest

@pytest.mark.oracledb_sync
def test_create_user_oracle_18c(oracle18c_engine):
    """Test user creation on Oracle 18c (sync)."""
    pass

@pytest.mark.oracledb_async
async def test_query_user_oracle_23ai(oracle23ai_async_engine):
    """Test async query on Oracle 23ai."""
    pass
```

Run tests:

```bash
# Run only Oracle tests
uv run pytest tests/ -m "oracledb_sync or oracledb_async" -v
```

## Connection Pooling

```python
config = SQLAlchemyAsyncConfig(
    connection_string="oracle+oracledb://user:pass@host/service",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    connect_args={
        "encoding": "UTF-8",
        "nencoding": "UTF-8",
        "threaded": True,
    },
)
```

## Common Gotchas

### Identifier Length Limit

Oracle has a 30-character limit (128 in Oracle 12.2+). Use shorter names:

```python
# ❌ Too long
class VeryLongTableNameThatExceedsOracleLimit(UUIDAuditBase):
    __tablename__ = "very_long_table_name_that_exceeds_oracle_limit"

# ✅ Use shorter names
class UserActivity(UUIDAuditBase):
    __tablename__ = "user_activity"
```

### Case Sensitivity

Oracle converts unquoted identifiers to uppercase:

```python
class User(UUIDAuditBase):
    __tablename__ = "users"  # Becomes USERS in Oracle
```

### JSON Support

Oracle 21c+ has native JSON. For older versions, use CLOB:

```python
from advanced_alchemy.types import JsonB

class Document(UUIDAuditBase):
    __tablename__ = "documents"

    # Stored as CLOB, serialized as JSON
    metadata: "Mapped[dict]" = mapped_column(JsonB)
```

## Docker Setup

```bash
# Oracle 18c Express Edition
docker run -d \
  --name oracle18c \
  -p 1521:1521 \
  -e ORACLE_PWD=YourPassword123 \
  gvenzl/oracle-xe:18-slim

# Oracle 23ai Free
docker run -d \
  --name oracle23ai \
  -p 1521:1521 \
  -e ORACLE_PWD=YourPassword123 \
  gvenzl/oracle-free:23-slim
```

## See Also

- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [Oracle Documentation](https://docs.oracle.com/en/database/) - Official Oracle docs
- [python-oracledb Documentation](https://python-oracledb.readthedocs.io/) - Driver docs
- [SQLAlchemy Oracle Dialect](https://docs.sqlalchemy.org/en/20/dialects/oracle.html) - Dialect docs

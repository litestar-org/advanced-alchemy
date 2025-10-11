# Microsoft SQL Server

Microsoft SQL Server driver configuration and Advanced Alchemy-specific patterns.

## Drivers

### aioodbc (Async)

```bash
uv add aioodbc
```

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

config = SQLAlchemyAsyncConfig(
    connection_string="mssql+aioodbc://user:password@localhost:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)
```

### pyodbc (Sync)

```bash
uv add pyodbc
```

```python
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig

config = SQLAlchemySyncConfig(
    connection_string="mssql+pyodbc://user:password@localhost:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
)
```

## ODBC Driver Setup

Both drivers require Microsoft ODBC Driver for SQL Server.

**Linux (Ubuntu/Debian):**

```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
```

**macOS:**

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
brew install msodbcsql18 mssql-tools18
```

**Verify Installation:**

```bash
odbcinst -q -d
```

## Connection Strings

```python
# Standard connection
connection_string = "mssql+aioodbc://user:password@localhost:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

# Azure SQL Database
connection_string = "mssql+aioodbc://user:password@server.database.windows.net:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"

# Windows Authentication
connection_string = "mssql+pyodbc://localhost/dbname?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes"
```

## Advanced Alchemy Type Mappings

### UNIQUEIDENTIFIER for UUIDs

```python
from advanced_alchemy.base import UUIDAuditBase

class User(UUIDAuditBase):
    """Uses SQL Server UNIQUEIDENTIFIER type for primary key."""

    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True)
    name: "Mapped[str]"
```

The `GUID` type from Advanced Alchemy automatically uses `UNIQUEIDENTIFIER` for SQL Server.

### IDENTITY Columns

```python
from advanced_alchemy.base import BigIntAuditBase

class Product(BigIntAuditBase):
    __tablename__ = "products"

    # IDENTITY(1,1) is created automatically
    name: "Mapped[str]"
    sku: "Mapped[str]" = mapped_column(unique=True)
```

### JSON Support

SQL Server 2016+ has native JSON support:

```python
from sqlalchemy import JSON, func
from sqlalchemy.orm import Mapped, mapped_column

class Document(UUIDAuditBase):
    __tablename__ = "documents"

    metadata: "Mapped[dict]" = mapped_column(JSON)
    tags: "Mapped[list]" = mapped_column(JSON, default=list)
```

**Query JSON:**

```python
# JSON path query
stmt = select(Document).where(
    func.json_value(Document.metadata, "$.status") == "active"
)
```

## Upsert Operations

Advanced Alchemy handles SQL Server upserts automatically:

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
    connection_string="mssql+aioodbc://user:pass@localhost/db?driver=ODBC+Driver+18+for+SQL+Server",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

### Multiple Active Result Sets (MARS)

```python
connection_string = "mssql+aioodbc://user:pass@localhost/db?driver=ODBC+Driver+18+for+SQL+Server&MultipleActiveResultSets=yes"
```

## pytest Markers

```python
import pytest

@pytest.mark.mssql_sync
def test_create_user_mssql(mssql_engine):
    """Test user creation on SQL Server with pyodbc."""
    pass

@pytest.mark.aioodbc
async def test_async_mssql_operations(aioodbc_engine):
    """Test async operations on SQL Server."""
    pass
```

Run tests:

```bash
# Run only SQL Server tests
uv run pytest tests/ -m "mssql_sync or aioodbc" -v
```

## Common Gotchas

### OUTPUT Clause

SQL Server uses OUTPUT instead of RETURNING (handled automatically by Advanced Alchemy):

```python
# Automatically uses OUTPUT
user = await repository.create({"email": "user@example.com", "name": "John"})
# user.id and computed columns are populated
```

### Indexes

```python
from sqlalchemy import Index, func, text

class User(UUIDAuditBase):
    __tablename__ = "users"

    email: "Mapped[str]" = mapped_column(unique=True, index=True)
    name: "Mapped[str]"
    city: "Mapped[str]"

    __table_args__ = (
        # Filtered index
        Index("ix_active_users_email", "email", mssql_where=text("is_active = 1")),
        # Included columns for covering index
        Index("ix_user_city", "city", mssql_include=["name", "email"]),
    )
```

## Docker Setup

```bash
# Start SQL Server 2022 in Docker
docker run -d \
  --name mssql-test \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=YourStrong!Passw0rd" \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

# Create test database
docker exec -it mssql-test /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "YourStrong!Passw0rd" -C \
  -Q "CREATE DATABASE testdb;"
```

## See Also

- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [SQL Server Documentation](https://docs.microsoft.com/en-us/sql/sql-server/) - Official docs
- [aioodbc Documentation](https://aioodbc.readthedocs.io/) - Async driver docs
- [pyodbc Documentation](https://github.com/mkleehammer/pyodbc/wiki) - Sync driver docs

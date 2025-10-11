# Google Cloud Spanner

Google Cloud Spanner driver configuration and Advanced Alchemy-specific patterns.

## Driver

```bash
uv add "sqlalchemy-spanner>=1.7.0"
```

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

# Production instance
config = SQLAlchemyAsyncConfig(
    connection_string="spanner+spanner:///projects/my-project/instances/my-instance/databases/my-database"
)
```

## Spanner Emulator for Testing

**IMPORTANT:** Use the emulator for local development and testing.

**Install:**

```bash
# Using gcloud CLI
gcloud components install cloud-spanner-emulator

# Using Docker
docker pull gcr.io/cloud-spanner-emulator/emulator
docker run -d -p 9010:9010 --name spanner-emulator \
  gcr.io/cloud-spanner-emulator/emulator
```

**Start:**

```bash
# gcloud CLI
gcloud emulators spanner start

# Sets: SPANNER_EMULATOR_HOST=localhost:9010
```

**Configure for tests:**

```python
import os
from google.cloud import spanner

os.environ["SPANNER_EMULATOR_HOST"] = "localhost:9010"
os.environ["GOOGLE_CLOUD_PROJECT"] = "emulator-test-project"

# Create instance and database
client = spanner.Client(project="emulator-test-project")
instance = client.instance("test-instance")
instance.create()

database = instance.database("test-db")
database.create()

# Connection string
connection_string = "spanner+spanner:///projects/emulator-test-project/instances/test-instance/databases/test-db"
```

## Advanced Alchemy-Specific Patterns

### Interleaved Tables

Spanner's parent-child co-location feature:

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Author(UUIDAuditBase):
    __tablename__ = "authors"

    name: "Mapped[str]"
    books: "Mapped[list[Book]]" = relationship(back_populates="author")

class Book(UUIDAuditBase):
    __tablename__ = "books"

    author_id: "Mapped[uuid.UUID]" = mapped_column(ForeignKey("authors.id"))
    title: "Mapped[str]"
    author: "Mapped[Author]" = relationship(back_populates="books")

    __table_args__ = (
        {"spanner_interleave_in": "authors", "spanner_on_delete_cascade": True},
    )
```

### ARRAY Types

```python
from sqlalchemy import ARRAY, String, Integer

class Product(UUIDAuditBase):
    __tablename__ = "products"

    name: "Mapped[str]"
    tags: "Mapped[list[str]]" = mapped_column(ARRAY(String))
    ratings: "Mapped[list[int]]" = mapped_column(ARRAY(Integer))
```

**Query arrays:**

```python
from sqlalchemy import func

# Check if array contains value
stmt = select(Product).where(func.array_includes(Product.tags, "electronics"))

# Array length
stmt = select(Product).where(func.array_length(Product.tags) > 3)
```

### Upsert Operations

Advanced Alchemy uses Spanner's `INSERT OR UPDATE`:

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

@pytest.mark.spanner
async def test_create_user_spanner(spanner_engine):
    """Test user creation on Cloud Spanner."""
    pass

@pytest.mark.spanner
async def test_interleaved_tables(spanner_engine):
    """Test Spanner interleaved table feature."""
    pass
```

Run tests:

```bash
# Run only Spanner tests (requires emulator)
uv run pytest tests/ -m spanner -v
```

## Common Gotchas

### Transaction Limits

- Maximum 20,000 mutations per transaction
- Use bulk operations to stay within limits

```python
# ✅ Bulk operations stay within limits
users = await repository.create_many(users_data)
```

### No Foreign Keys

Spanner doesn't enforce foreign keys. Use interleaved tables or application-level validation:

```python
# Use interleaved tables instead
__table_args__ = (
    {"spanner_interleave_in": "parent_table"},
)
```

### Schema Changes Are Async

DDL operations take time for large databases. Be patient with migrations.

## See Also

- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [Cloud Spanner Documentation](https://cloud.google.com/spanner/docs) - Official docs
- [sqlalchemy-spanner GitHub](https://github.com/googleapis/python-spanner-sqlalchemy) - Driver repository
- [Spanner Emulator](https://cloud.google.com/spanner/docs/emulator) - Emulator documentation

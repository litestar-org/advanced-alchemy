# Guide: Model Mixins

`advanced-alchemy` includes a variety of model mixins that can be used to easily add common columns and functionality to your SQLAlchemy declarative models. These mixins help reduce boilerplate code and enforce consistency across your models.

## Using Mixins

To use a mixin, simply include it in the base classes of your model definition.

```python
from sqlalchemy.orm import DeclarativeBase
from advanced_alchemy.mixins import AuditColumns, BigIntPrimaryKey

class Base(DeclarativeBase):
    pass

class MyModel(BigIntPrimaryKey, AuditColumns, Base):
    __tablename__ = "my_model"
    # ... other columns
```

## Available Mixins

Here is a list of the available mixins and what they provide.

### Primary Key Mixins

These mixins add an `id` primary key column with different data types and generation strategies.

-   **`BigIntPrimaryKey`**: Adds an `id` column of type `BigInt` that uses a database sequence for value generation (`BIGSERIAL` on PostgreSQL).
-   **`IdentityPrimaryKey`**: Adds an `id` column of type `BigInt` that uses the database's `IDENTITY` feature. This is often more performant than sequences on supported backends.
-   **`UUIDPrimaryKey`**: Adds an `id` column of type `UUID` that defaults to generating a UUID version 4.
-   **`UUIDv6PrimaryKey`**: Adds an `id` column of type `UUID` that defaults to generating a time-ordered UUID version 6. Requires the `uuid-utils` package.
-   **`UUIDv7PrimaryKey`**: Adds an `id` column of type `UUID` that defaults to generating a time-ordered UUID version 7. Requires the `uuid-utils` package.
-   **`NanoIDPrimaryKey`**: Adds an `id` column of type `String` that defaults to generating a unique NanoID. Requires the `fastnanoid` package.

**Example:**

```python
from advanced_alchemy.mixins import UUIDPrimaryKey

class User(UUIDPrimaryKey, Base):
    __tablename__ = "user"
    name: Mapped[str]
```

### Audit Columns

-   **`AuditColumns`**: Adds two timestamp columns that are automatically managed by SQLAlchemy:
    -   `created_at`: A `DateTimeUTC` column that is set to the current UTC time when a record is first created.
    -   `updated_at`: A `DateTimeUTC` column that is set to the current UTC time whenever a record is created or updated.

**Example:**

```python
from advanced_alchemy.mixins import AuditColumns

class Post(AuditColumns, Base):
    __tablename__ = "post"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
```

### Slug Column

-   **`SlugKey`**: Adds a `slug` column of type `String(100)`. It also automatically creates a unique constraint or a unique index on this column to ensure that slug values are unique across the table.

**Example:**

```python
from advanced_alchemy.mixins import SlugKey

class Product(SlugKey, Base):
    __tablename__ = "product"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
```

### Uniqueness Enforcement

-   **`UniqueMixin`**: A more advanced mixin that provides a class-level method to create or retrieve unique objects from the database. It's useful for creating things like tags or categories where you want to avoid duplicate entries.

    To use it, you must implement two class methods:
    -   `unique_hash(*args, **kwargs)`: Should return a hashable value that uniquely identifies an object.
    -   `unique_filter(*args, **kwargs)`: Should return a SQLAlchemy filter expression to find the unique object in the database.

**Example:**

```python
from advanced_alchemy.mixins import UniqueMixin
from sqlalchemy import ColumnElement

class Tag(UniqueMixin, Base):
    __tablename__ = "tag"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)

    @classmethod
    def unique_hash(cls, name: str) -> str:
        return name

    @classmethod
    def unique_filter(cls, name: str) -> ColumnElement[bool]:
        return cls.name == name

# Usage (sync):
tag1 = Tag.as_unique_sync(session, name="python")
tag2 = Tag.as_unique_sync(session, name="python")
assert tag1 is tag2
```

These mixins provide a powerful way to quickly build out your SQLAlchemy models with common, reusable patterns.

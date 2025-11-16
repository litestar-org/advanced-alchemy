==============
Advanced Types
==============

Specialized SQLAlchemy types for advanced use cases.

MutableList
-----------

A list type that tracks mutations for proper SQLAlchemy change detection.

**Characteristics:**

- Python type: :class:`list`
- Storage: JSON/JSONB
- Mutation tracking: Automatic
- Use case: Lists that need in-place modification tracking

Problem Solved
~~~~~~~~~~~~~~

Standard Python lists don't trigger SQLAlchemy change tracking:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import JsonB

    class TodoList(UUIDBase):
        __tablename__ = "todo_lists"
        items: "Mapped[list[str]]" = mapped_column(JsonB)

    # This won't trigger change detection
    todo_list.items.append("New task")  # SQLAlchemy doesn't see the change
    await session.commit()  # Nothing saved!

Solution with MutableList
~~~~~~~~~~~~~~~~~~~~~~~~~~

MutableList tracks mutations automatically:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import MutableList

    class TodoList(UUIDBase):
        __tablename__ = "todo_lists"
        items: "Mapped[list[str]]" = mapped_column(MutableList)

    # Mutations tracked automatically
    todo_list.items.append("New task")  # Change detected
    await session.commit()  # Saved correctly

Supported Operations
~~~~~~~~~~~~~~~~~~~~

All list mutations are tracked:

.. code-block:: python

    # Append
    todo_list.items.append("Task 4")

    # Extend
    todo_list.items.extend(["Task 5", "Task 6"])

    # Insert
    todo_list.items.insert(0, "Task 0")

    # Remove
    todo_list.items.remove("Task 2")

    # Pop
    todo_list.items.pop()

    # Index assignment
    todo_list.items[0] = "Updated Task"

    # Slice assignment
    todo_list.items[1:3] = ["New Task 1", "New Task 2"]

    # Delete
    del todo_list.items[0]

    # All trigger change detection
    await session.commit()

Complex Data Structures
~~~~~~~~~~~~~~~~~~~~~~~

MutableList works with complex nested data:

.. code-block:: python

    from typing import Any
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import MutableList

    class Project(UUIDBase):
        __tablename__ = "projects"

        tasks: "Mapped[list[dict[str, Any]]]" = mapped_column(MutableList)

    project.tasks.append({
        "title": "Implement feature",
        "status": "in_progress",
        "assignee": "user@example.com",
        "due_date": "2025-10-25",
    })

    # Update nested value
    project.tasks[0]["status"] = "completed"
    await session.commit()

When to Use MutableList
~~~~~~~~~~~~~~~~~~~~~~~

Use MutableList when:

- Lists are modified in-place frequently
- Code relies on standard list methods (append, extend, etc.)
- Change tracking is critical

Alternative approach (reassignment):

.. code-block:: python

    # Without MutableList - use reassignment
    items = todo_list.items.copy()
    items.append("New task")
    todo_list.items = items  # Reassignment triggers change detection
    await session.commit()

ORA_JSONB
---------

Oracle-specific binary JSON type with CHECK constraint.

**Characteristics:**

- Database: Oracle only
- Storage: BLOB with JSON CHECK constraint
- Python type: :class:`dict` or :class:`list`
- Use case: Efficient JSON storage on Oracle

Implementation Details
~~~~~~~~~~~~~~~~~~~~~~

ORA_JSONB stores JSON as binary with database-level validation:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import ORA_JSONB

    class Document(UUIDBase):
        __tablename__ = "documents"

        # Oracle: BLOB with JSON CHECK constraint
        # Other databases: fallback to standard JSON
        metadata: "Mapped[dict[str, Any]]" = mapped_column(ORA_JSONB)

Generated SQL (Oracle):

.. code-block:: sql

    CREATE TABLE documents (
        id RAW(16) PRIMARY KEY,
        metadata BLOB,
        CONSTRAINT metadata_is_json CHECK (metadata IS JSON)
    );

Strict vs Non-Strict
~~~~~~~~~~~~~~~~~~~~

Control JSON validation strictness:

.. code-block:: python

    # Strict validation (default) - rejects duplicates
    metadata: "Mapped[dict[str, Any]]" = mapped_column(
        ORA_JSONB(oracle_strict=True)
    )

    # Non-strict - allows duplicate keys
    metadata: "Mapped[dict[str, Any]]" = mapped_column(
        ORA_JSONB(oracle_strict=False)
    )

JsonB vs ORA_JSONB
~~~~~~~~~~~~~~~~~~

:class:`~advanced_alchemy.types.JsonB` automatically uses ORA_JSONB on Oracle:

.. code-block:: python

    from advanced_alchemy.types import JsonB

    # Automatically uses:
    # - PostgreSQL: JSONB
    # - Oracle: ORA_JSONB (BLOB + CHECK)
    # - CockroachDB: JSONB
    # - Others: JSON
    data: "Mapped[dict[str, Any]]" = mapped_column(JsonB)

Prefer :class:`~advanced_alchemy.types.JsonB` for cross-database compatibility.

UUID Variants
-------------

Advanced Alchemy supports UUID v6 and v7 through optional dependencies.

UUID v6 (Sortable UUIDs)
~~~~~~~~~~~~~~~~~~~~~~~~

Time-ordered UUIDs compatible with UUID v1 but sortable:

.. code-block:: python

    from advanced_alchemy.base import UUIDv6Base

    class Event(UUIDv6Base):
        __tablename__ = "events"
        name: "Mapped[str]"

**Characteristics:**

- Time-ordered: Newer UUIDs sort after older ones
- Database indexing: Better performance for time-based queries
- Installation: ``pip install "advanced-alchemy[uuid]"``

UUID v7 (Time-Ordered UUIDs)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Modern time-ordered UUIDs with millisecond precision:

.. code-block:: python

    from advanced_alchemy.base import UUIDv7Base

    class LogEntry(UUIDv7Base):
        __tablename__ = "log_entries"
        message: "Mapped[str]"

**Characteristics:**

- Time-ordered: Timestamp embedded in UUID
- Sortable: Natural chronological ordering
- Installation: ``pip install "advanced-alchemy[uuid]"``

NanoID
------

Short, URL-safe unique identifiers as an alternative to UUIDs.

**Characteristics:**

- Length: 21 characters (default)
- Character set: URL-safe (alphanumeric plus underscore and hyphen)
- Collision resistance: High (comparable to UUID)
- Installation: ``pip install "advanced-alchemy[nanoid]"``

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.base import NanoIDBase

    class ShortLink(NanoIDBase):
        __tablename__ = "short_links"
        url: "Mapped[str]"

Example NanoID: ``V1StGXR8_Z5jdHi6B-myT``

When to Use NanoID
~~~~~~~~~~~~~~~~~~

Use NanoID when:

- Shorter IDs needed for URLs
- URL-safe characters required
- Human-readable IDs preferred over UUIDs

Comparison:

- UUID: ``550e8400-e29b-41d4-a716-446655440000`` (36 chars)
- NanoID: ``V1StGXR8_Z5jdHi6B-myT`` (21 chars)

Type Coercion and Validation
-----------------------------

Custom Types with Validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create custom types with validation logic:

.. code-block:: python

    from typing import Any, Optional
    from sqlalchemy import String
    from sqlalchemy.engine import Dialect
    from sqlalchemy.types import TypeDecorator

    class EmailType(TypeDecorator[str]):
        """Email address type with validation."""

        impl = String(255)
        cache_ok = True

        @property
        def python_type(self) -> type[str]:
            return str

        def process_bind_param(
            self,
            value: Optional[str],
            dialect: Dialect
        ) -> Optional[str]:
            if value is None:
                return value

            # Basic email validation
            if "@" not in value:
                raise ValueError(f"invalid email format: {value}")

            return value.lower()  # Normalize to lowercase

        def process_result_value(
            self,
            value: Optional[str],
            dialect: Dialect
        ) -> Optional[str]:
            return value

    # Usage
    class User(UUIDBase):
        __tablename__ = "users"
        email: "Mapped[str]" = mapped_column(EmailType)

Type Adaptation Pattern
~~~~~~~~~~~~~~~~~~~~~~~

Adapt Python types to database-specific types:

.. code-block:: python

    from enum import Enum
    from typing import Any, Optional
    from sqlalchemy import String
    from sqlalchemy.engine import Dialect
    from sqlalchemy.types import TypeDecorator

    class Status(Enum):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    class StatusType(TypeDecorator[Status]):
        """Enum type stored as string."""

        impl = String(20)
        cache_ok = True

        @property
        def python_type(self) -> type[Status]:
            return Status

        def process_bind_param(
            self,
            value: Optional[Status],
            dialect: Dialect
        ) -> Optional[str]:
            return value.value if value else None

        def process_result_value(
            self,
            value: Optional[str],
            dialect: Dialect
        ) -> Optional[Status]:
            return Status(value) if value else None

    # Usage
    class Application(UUIDBase):
        __tablename__ = "applications"
        status: "Mapped[Status]" = mapped_column(StatusType)

Performance Considerations
--------------------------

Type Selection Impact
~~~~~~~~~~~~~~~~~~~~~

Type selection affects database performance:

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Type
     - Index Performance
     - Storage Size
   * - GUID (binary)
     - Medium
     - 16 bytes
   * - GUID (string)
     - Lower
     - 32-36 bytes
   * - BigIntIdentity
     - High
     - 8 bytes
   * - JsonB
     - Medium (with indexes)
     - Variable
   * - EncryptedString
     - Not indexable
     - Variable (larger than plaintext)

UUID Performance
~~~~~~~~~~~~~~~~

Binary UUID storage is more efficient:

.. code-block:: python

    # More efficient
    id: "Mapped[UUID]" = mapped_column(GUID(binary=True), primary_key=True)

    # Less efficient but more portable
    id: "Mapped[UUID]" = mapped_column(GUID(binary=False), primary_key=True)

JSON Indexing
~~~~~~~~~~~~~

PostgreSQL supports JSON indexing:

.. code-block:: python

    from sqlalchemy import Index

    class UserSettings(UUIDBase):
        __tablename__ = "user_settings"

        preferences: "Mapped[dict[str, Any]]" = mapped_column(JsonB)

        # GIN index for JSONB queries
        __table_args__ = (
            Index(
                "ix_preferences_gin",
                "preferences",
                postgresql_using="gin"
            ),
        )

Migration Considerations
------------------------

Changing Column Types
~~~~~~~~~~~~~~~~~~~~~

Be cautious when changing column types in migrations:

.. code-block:: python

    # Alembic migration example
    def upgrade():
        # Add new column
        op.add_column("users", sa.Column("email_new", EmailType(), nullable=True))

        # Copy and transform data
        op.execute("UPDATE users SET email_new = LOWER(email)")

        # Drop old column
        op.drop_column("users", "email")

        # Rename new column
        op.alter_column("users", "email_new", new_column_name="email")

See Also
--------

- :doc:`basic-types` - Core SQLAlchemy types
- :doc:`security-types` - Encrypted and password types
- :doc:`file-storage` - File object storage
- :doc:`/reference/types` - Complete API reference

===========
Basic Types
===========

Core SQLAlchemy types for common data patterns across database backends.

GUID
----

Platform-independent UUID/GUID type with automatic dialect adaptation.

**Characteristics:**

- Python type: :class:`uuid.UUID`
- Storage format varies by database dialect
- Accepts UUID objects, hex strings, or bytes
- Returns Python :class:`uuid.UUID` objects

Database-Specific Storage
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Database
     - Storage Type
   * - PostgreSQL, DuckDB, CockroachDB
     - Native UUID type
   * - Microsoft SQL Server
     - UNIQUEIDENTIFIER
   * - Oracle
     - RAW(16) - 16 bytes binary
   * - SQLite, MySQL, others
     - BINARY(16) or CHAR(32) depending on configuration

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from uuid import UUID, uuid4
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import GUID

    class User(DefaultBase):
        __tablename__ = "users"

        id: "Mapped[UUID]" = mapped_column(GUID, primary_key=True, default=uuid4)
        email: "Mapped[str]" = mapped_column(unique=True)

Binary vs String Storage
~~~~~~~~~~~~~~~~~~~~~~~~

Control storage format on databases that don't have native UUID:

.. code-block:: python

    # Binary storage (default, more efficient)
    id: "Mapped[UUID]" = mapped_column(GUID(binary=True), primary_key=True)

    # String storage (32 hex characters)
    id: "Mapped[UUID]" = mapped_column(GUID(binary=False), primary_key=True)

Creating Records
~~~~~~~~~~~~~~~~

.. code-block:: python

    from uuid import uuid4
    from sqlalchemy.ext.asyncio import AsyncSession

    async def create_user(session: AsyncSession) -> User:
        user = User(
            id=uuid4(),  # Explicit UUID
            email="user@example.com",
        )
        session.add(user)
        await session.commit()
        return user

    # Or let default handle it
    async def create_user_auto(session: AsyncSession) -> User:
        user = User(email="user@example.com")  # UUID generated automatically
        session.add(user)
        await session.commit()
        return user

Querying
~~~~~~~~

.. code-block:: python

    from uuid import UUID

    async def get_user(session: AsyncSession, user_id: UUID) -> "Optional[User]":
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    # Works with string input too
    async def get_user_str(session: AsyncSession, user_id: str) -> "Optional[User]":
        stmt = select(User).where(User.id == UUID(user_id))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

Integration with Base Classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Advanced Alchemy base classes handle GUID automatically:

.. code-block:: python

    from advanced_alchemy.base import UUIDBase, UUIDAuditBase

    # Minimal setup - just define your fields
    class Product(UUIDBase):
        __tablename__ = "products"
        name: "Mapped[str]"
        price: "Mapped[float]"

    # With audit columns
    class Order(UUIDAuditBase):
        __tablename__ = "orders"
        product_id: "Mapped[UUID]" = mapped_column(GUID)
        quantity: "Mapped[int]"

DateTimeUTC
-----------

Timezone-aware datetime type that ensures UTC storage and returns timezone-aware Python datetime objects.

**Characteristics:**

- Python type: :class:`datetime.datetime`
- Storage: UTC timezone
- Input requirement: Timezone-aware datetime
- Output: Timezone-aware datetime (UTC)

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from datetime import datetime, timezone
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import DateTimeUTC

    class Event(DefaultBase):
        __tablename__ = "events"

        name: "Mapped[str]"
        scheduled_at: "Mapped[datetime]" = mapped_column(DateTimeUTC)
        created_at: "Mapped[datetime]" = mapped_column(
            DateTimeUTC,
            default=lambda: datetime.now(timezone.utc)
        )

Creating Records
~~~~~~~~~~~~~~~~

.. code-block:: python

    from datetime import datetime, timezone

    async def create_event(session: AsyncSession) -> Event:
        # Timezone-aware datetime required
        event = Event(
            name="Product Launch",
            scheduled_at=datetime.now(timezone.utc)
        )
        session.add(event)
        await session.commit()
        return event

    # Error: naive datetime not allowed
    async def create_event_error(session: AsyncSession) -> Event:
        event = Event(
            name="Meeting",
            scheduled_at=datetime.now()  # TypeError: tzinfo is required
        )
        session.add(event)
        await session.commit()
        return event

Timezone Conversion
~~~~~~~~~~~~~~~~~~~

Input datetimes are automatically converted to UTC:

.. code-block:: python

    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Create event with Eastern time
    eastern_time = datetime(2025, 10, 18, 14, 30, tzinfo=ZoneInfo("America/New_York"))

    event = Event(
        name="Regional Meeting",
        scheduled_at=eastern_time  # Stored as UTC in database
    )

    # Retrieved datetime is in UTC
    await session.commit()
    await session.refresh(event)
    print(event.scheduled_at)  # 2025-10-18 18:30:00+00:00 (UTC)

Integration with Base Classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Audit base classes include DateTimeUTC automatically:

.. code-block:: python

    from advanced_alchemy.base import UUIDAuditBase

    class Document(UUIDAuditBase):
        __tablename__ = "documents"

        title: "Mapped[str]"
        # created_at and updated_at are DateTimeUTC, added automatically

    # Access audit timestamps
    doc = Document(title="Report")
    await session.add(doc)
    await session.commit()

    print(doc.created_at)  # Timezone-aware UTC datetime
    print(doc.updated_at)  # Timezone-aware UTC datetime

JsonB
-----

Efficient JSON storage type that uses native binary JSON where available.

**Characteristics:**

- Python type: :class:`dict` or :class:`list`
- PostgreSQL/CockroachDB: Native JSONB (binary JSON)
- Oracle: BLOB with JSON constraint
- Other databases: Standard JSON type

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from typing import Any
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import JsonB

    class UserSettings(UUIDBase):
        __tablename__ = "user_settings"

        user_id: "Mapped[UUID]" = mapped_column(GUID)
        preferences: "Mapped[dict[str, Any]]" = mapped_column(JsonB)
        tags: "Mapped[list[str]]" = mapped_column(JsonB)

Storing Complex Data
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    async def create_settings(session: AsyncSession) -> UserSettings:
        settings = UserSettings(
            user_id=user.id,
            preferences={
                "theme": "dark",
                "language": "en",
                "notifications": {
                    "email": True,
                    "push": False,
                },
            },
            tags=["premium", "verified"],
        )
        session.add(settings)
        await session.commit()
        return settings

Querying JSON Data
~~~~~~~~~~~~~~~~~~

PostgreSQL JSON operators:

.. code-block:: python

    from sqlalchemy import select

    # PostgreSQL JSONB operators
    async def find_dark_theme_users(session: AsyncSession) -> "list[UserSettings]":
        stmt = select(UserSettings).where(
            UserSettings.preferences["theme"].astext == "dark"
        )
        result = await session.execute(stmt)
        return list(result.scalars())

    # Check if key exists
    async def find_with_notifications(session: AsyncSession) -> "list[UserSettings]":
        stmt = select(UserSettings).where(
            UserSettings.preferences["notifications"].isnot(None)
        )
        result = await session.execute(stmt)
        return list(result.scalars())

Updating JSON Data
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    async def update_preference(
        session: AsyncSession,
        settings: UserSettings,
        key: str,
        value: Any
    ) -> UserSettings:
        # Modify the dictionary
        settings.preferences[key] = value

        # SQLAlchemy tracks changes
        await session.commit()
        return settings

    # Or replace entirely
    async def replace_preferences(
        session: AsyncSession,
        settings: UserSettings
    ) -> UserSettings:
        settings.preferences = {
            "theme": "light",
            "language": "es",
        }
        await session.commit()
        return settings

BigIntIdentity
--------------

BigInteger type that automatically falls back to Integer for SQLite.

**Characteristics:**

- Python type: :class:`int`
- Most databases: BIGINT (8 bytes, ±9 quintillion)
- SQLite: INTEGER (SQLite integers are always 64-bit)
- Typically used for auto-incrementing primary keys

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import BigIntIdentity

    class Product(DefaultBase):
        __tablename__ = "products"

        id: "Mapped[int]" = mapped_column(BigIntIdentity, primary_key=True)
        sku: "Mapped[str]" = mapped_column(unique=True)
        name: "Mapped[str]"

Integration with Base Classes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

BigInt base classes use this type automatically:

.. code-block:: python

    from advanced_alchemy.base import BigIntBase, BigIntAuditBase

    # Minimal setup
    class Article(BigIntBase):
        __tablename__ = "articles"
        title: "Mapped[str]"
        content: "Mapped[str]"

    # With audit columns
    class Comment(BigIntAuditBase):
        __tablename__ = "comments"
        article_id: "Mapped[int]" = mapped_column(BigIntIdentity)
        content: "Mapped[str]"

See Also
--------

- :doc:`security-types` - Encrypted and password types
- :doc:`file-storage` - File object storage
- :doc:`../modeling/index` - Base class integration
- :doc:`/reference/types` - Complete API reference

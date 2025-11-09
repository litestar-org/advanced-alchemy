======
Basics
======

Advanced Alchemy provides pre-configured base classes for SQLAlchemy models with common primary key strategies and audit fields.

Base Classes
============

Advanced Alchemy includes several declarative base classes. Each provides different primary key strategies:

.. list-table:: Base Classes and Features
   :header-rows: 1
   :widths: 20 80

   * - Base Class
     - Features
   * - ``BigIntBase``
     - BIGINT primary keys for tables
   * - ``BigIntAuditBase``
     - BIGINT primary keys for tables, Automatic created_at/updated_at timestamps
   * - ``IdentityBase``
     - Primary keys using database IDENTITY feature instead of sequences
   * - ``IdentityAuditBase``
     - Primary keys using database IDENTITY feature, Automatic created_at/updated_at timestamps
   * - ``UUIDBase``
     - UUID (v4) primary keys
   * - ``UUIDAuditBase``
     - UUID (v4) primary keys, Automatic created_at/updated_at timestamps
   * - ``UUIDv6Base``
     - UUIDv6 primary keys
   * - ``UUIDv6AuditBase``
     - UUIDv6 primary keys, Automatic created_at/updated_at timestamps
   * - ``UUIDv7Base``
     - UUIDv7 primary keys
   * - ``UUIDv7AuditBase``
     - Time-sortable UUIDv7 primary keys, Automatic created_at/updated_at timestamps
   * - ``NanoIDBase``
     - URL-friendly unique identifiers, Shorter than UUIDs, collision resistant
   * - ``NanoIDAuditBase``
     - URL-friendly IDs with audit timestamps, Combines Nanoid benefits with audit trails
   * - ``DefaultBase``
     - Basic declarative base without primary key or audit fields

Basic Mixins
============

Advanced Alchemy provides mixins to enhance model functionality:

.. list-table:: Available Mixins
   :header-rows: 1
   :widths: 20 80

   * - Mixin
     - Features
   * - ``AuditColumns``
     - | Adds created_at/updated_at timestamps
   * - ``BigIntPrimaryKey``
     - | Adds BigInt primary key with sequence
   * - ``IdentityPrimaryKey``
     - | Adds primary key using database IDENTITY feature
   * - ``NanoIDPrimaryKey``
     - | Adds NanoID primary key (URL-friendly unique identifier)
   * - ``SentinelMixin``
     - | Adds sentinel column for optimistic locking and change detection
   * - ``SlugKey``
     - | Adds URL-friendly slug field
   * - ``UniqueMixin``
     - | Provides methods for unique constraint handling
   * - ``UUIDPrimaryKey``
     - | Adds UUID (v4) primary key
   * - ``UUIDv6PrimaryKey``
     - | Adds UUIDv6 primary key
   * - ``UUIDv7PrimaryKey``
     - | Adds time-sortable UUIDv7 primary key

Simple Model Example
====================

Creating a basic model with BigIntAuditBase:

.. code-block:: python

    import datetime
    from typing import Optional

    from advanced_alchemy.base import BigIntAuditBase
    from sqlalchemy.orm import Mapped, mapped_column

    class Post(BigIntAuditBase):
        """Blog post model with auto-incrementing ID and audit fields.

        Attributes:
            title: The post title
            content: The post content
            published: Publication status
            published_at: Timestamp of publication
            created_at: Timestamp of creation (from BigIntAuditBase)
            updated_at: Timestamp of last update (from BigIntAuditBase)
        """

        title: Mapped[str] = mapped_column(index=True)
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        published_at: Mapped[Optional[datetime.datetime]] = mapped_column(default=None)

This model includes:

- Auto-incrementing ``id`` column (BigInt primary key)
- ``created_at`` timestamp (set on creation)
- ``updated_at`` timestamp (refreshed on modification)
- Custom columns: ``title``, ``content``, ``published``, ``published_at``

Implementation Patterns
=======================

UUID vs BigInt Primary Keys
----------------------------

Different primary key types have distinct characteristics:

**BigInt Primary Keys**

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase

    class User(BigIntAuditBase):
        username: Mapped[str] = mapped_column(unique=True)

Characteristics:

- Sequential integers (1, 2, 3, ...)
- Smaller index size compared to UUIDs
- Database generates values via sequences
- Predictable ordering
- Visible in URLs (``/users/123``)

**UUID Primary Keys**

.. code-block:: python

    from advanced_alchemy.base import UUIDAuditBase

    class User(UUIDAuditBase):
        username: Mapped[str] = mapped_column(unique=True)

Characteristics:

- Random 128-bit identifiers
- Generated client-side (Python)
- Suitable for distributed systems
- Non-sequential
- Not guessable in URLs (``/users/550e8400-e29b-41d4-a716-446655440000``)

**UUIDv7 Primary Keys**

.. code-block:: python

    from advanced_alchemy.base import UUIDv7AuditBase

    class User(UUIDv7AuditBase):
        username: Mapped[str] = mapped_column(unique=True)

Characteristics:

- Time-ordered UUIDs
- Timestamp embedded in first 48 bits
- Combines benefits of sequential and random IDs
- Better database index performance than UUIDv4
- Sortable by creation time

**NanoID Primary Keys**

.. code-block:: python

    from advanced_alchemy.base import NanoIDAuditBase

    class User(NanoIDAuditBase):
        username: Mapped[str] = mapped_column(unique=True)

Characteristics:

- URL-friendly strings (uses ``A-Za-z0-9_-``)
- Shorter than UUIDs (21 characters vs 36)
- Collision resistant
- Generated client-side
- Requires ``nanoid`` dependency: ``pip install advanced-alchemy[nanoid]``

Using Mixins
------------

Mixins add functionality to models without inheritance from base classes:

.. code-block:: python

    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.mixins import SlugKey, AuditColumns
    from sqlalchemy.orm import Mapped, mapped_column

    class Article(UUIDBase, SlugKey, AuditColumns):
        """Article with UUID primary key, slug, and audit fields."""

        title: Mapped[str] = mapped_column(unique=True)
        content: Mapped[str]

This model combines:

- ``UUIDBase`` - UUID primary key
- ``SlugKey`` - Automatic slug field
- ``AuditColumns`` - created_at/updated_at timestamps

Technical Constraints
=====================

Audit Field Behavior
--------------------

The ``AuditColumns`` mixin provides automatic timestamps:

.. code-block:: python

    # === Automatic updated_at refresh ===
    user = await repository.get_one(User.id == 1)
    user.email = "new@example.com"
    await session.commit()
    # user.updated_at is automatically updated

    # === Explicit override of updated_at ===
    user = await repository.get_one(User.id == 1)
    user.updated_at = specific_timestamp
    await session.commit()
    # user.updated_at retains the explicit value

The ``updated_at`` field refreshes during flush when any mapped column changes, but preserves explicitly set values.

Primary Key Generation
-----------------------

Primary key generation differs by type:

.. code-block:: python

    # === BigInt - Database generates via sequence ===
    user = User(username="alice")  # No id needed
    session.add(user)
    await session.flush()
    # user.id is populated by database

    # === UUID - Python generates client-side ===
    user = User(username="bob")  # UUID generated automatically
    session.add(user)
    await session.flush()
    # user.id is populated before flush

    # === NanoID - Python generates client-side ===
    user = User(username="charlie")  # NanoID generated automatically
    session.add(user)
    await session.flush()
    # user.id is populated before flush

Next Steps
==========

Once you have basic models, you can add relationships between them.

See :doc:`relationships` for foreign keys and many-to-many patterns.

=====
Types
=====

Advanced Alchemy provides several custom SQLAlchemy types to enhance your database interactions.

DateTimeUTC
-----------

A timezone-aware DateTime type that ensures UTC timezone handling in the database.

.. code-block:: python

    from advanced_alchemy.types import DateTimeUTC

    class MyModel:
        created_at = Column(DateTimeUTC)

The ``DateTimeUTC`` type:

- Ensures all datetime values are stored in UTC
- Requires timezone information for input values
- Automatically converts stored values to UTC timezone
- Returns timezone-aware datetime objects

Encrypted Types
---------------

Two types for storing encrypted data with support for multiple encryption backends:

EncryptedString
~~~~~~~~~~~~~~~

For storing encrypted string values with configurable length.

.. code-block:: python

    from advanced_alchemy.types import EncryptedString

    class MyModel:
        secret = Column(EncryptedString(key="my-secret-key"))

EncryptedText
~~~~~~~~~~~~~

For storing larger encrypted text content (CLOB).

.. code-block:: python

    from advanced_alchemy.types import EncryptedText

    class MyModel:
        large_secret = Column(EncryptedText(key="my-secret-key"))

Encryption Backends
~~~~~~~~~~~~~~~~~~~

Two encryption backends are available:

- ``FernetBackend``: Uses Python's cryptography library with Fernet encryption
- ``PGCryptoBackend``: Uses PostgreSQL's pgcrypto extension (PostgreSQL only)

GUID
----

A platform-independent GUID/UUID type that adapts to different database backends:

- PostgreSQL/DuckDB/CockroachDB: Uses native UUID type
- MSSQL: Uses UNIQUEIDENTIFIER
- Oracle: Uses RAW(16)
- Others: Uses BINARY(16) or CHAR(32)

.. code-block:: python

    from advanced_alchemy.types import GUID

    class MyModel:
        id = Column(GUID, primary_key=True)

BigIntIdentity
--------------

A BigInteger type that automatically falls back to Integer for SQLite:

.. code-block:: python

    from advanced_alchemy.types import BigIntIdentity

    class MyModel:
        id = Column(BigIntIdentity, primary_key=True)

JsonB
-----

A JSON type that uses the most efficient JSON storage for each database:

- PostgreSQL/CockroachDB: Uses native JSONB
- Oracle: Uses Binary JSON (BLOB with JSON constraint)
- Others: Uses standard JSON type

.. code-block:: python

    from advanced_alchemy.types import JsonB

    class MyModel:
        data = Column(JsonB)

Type Features
-------------

All types include:

- Proper Python type annotations for modern IDE support
- Automatic dialect-specific implementations
- Consistent behavior across different database backends
- Integration with SQLAlchemy's type system

Usage Example
-------------

Here's a complete example using multiple types:

.. code-block:: python

    from sqlalchemy import Column
    from advanced_alchemy.types import (
        DateTimeUTC,
        EncryptedString,
        GUID,
        JsonB,
    )

    class User:
        id = Column(GUID, primary_key=True)
        created_at = Column(DateTimeUTC)
        password = Column(EncryptedString(key="secret-key"))
        preferences = Column(JsonB)

Using Types with Alembic
------------------------

If you are not using Advanced Alchemy's built-in `alembic` templates, you need to properly configure your ``script.py.mako`` template. The key is to make the custom types available through the ``sa`` namespace that Alembic uses.

Type Aliasing
~~~~~~~~~~~~~

In your ``script.py.mako``, you'll need both the imports and the type aliasing:

.. code-block:: python

    # Import the types
    from advanced_alchemy.types import (
        EncryptedString,
        EncryptedText,
        GUID,
        ORA_JSONB,
        DateTimeUTC
    )

    # Create aliases in the sa namespace
    sa.GUID = GUID
    sa.DateTimeUTC = DateTimeUTC
    sa.ORA_JSONB = ORA_JSONB
    sa.EncryptedString = EncryptedString
    sa.EncryptedText = EncryptedText

These assignments are necessary because:

1. Alembic uses the ``sa`` namespace when generating migrations
2. Custom types need to be accessible through this namespace
3. Without these aliases, Alembic might not properly detect or reference the custom types

Example Usage
~~~~~~~~~~~~~

This setup allows you to use the types in migrations like this:

.. code-block:: python

    # In generated migration file
    def upgrade():
        op.create_table(
            'users',
            sa.Column('id', sa.GUID(), primary_key=True),
            sa.Column('created_at', sa.DateTimeUTC(), nullable=False),
            sa.Column('secret', sa.EncryptedString(), nullable=True),
        )

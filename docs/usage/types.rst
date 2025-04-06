=====
Types
=====

Advanced Alchemy provides several custom SQLAlchemy types.

All types include:

- Proper Python type annotations for modern IDE support
- Automatic dialect-specific implementations
- Consistent behavior across different database backends
- Integration with SQLAlchemy's type system

Here's a short example using multiple types:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import (
        DateTimeUTC,
        EncryptedString,
        GUID,
        JsonB,
        StoredObject,
    )

    class User(DefaultBase):
        __tablename__ = "users"
        id: Mapped[UUID] = mapped_column(GUID, primary_key=True)
        created_at: Mapped[datetime] = mapped_column(DateTimeUTC)
        password: Mapped[str] = mapped_column(EncryptedString(key="secret-key"))
        preferences: Mapped[dict] = mapped_column(JsonB)
        avatar: Mapped[Optional[FileObject]] = mapped_column(StoredObject(backend="local_store"))


DateTimeUTC
-----------

- Ensures all datetime values are stored in UTC
- Requires timezone information for input values
- Automatically converts stored values to UTC timezone
- Returns timezone-aware datetime objects

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import DateTimeUTC

    class MyModel(DefaultBase):
        created_at: Mapped[datetime] = mapped_column(DateTimeUTC)


Encrypted Types
---------------

Two types for storing encrypted data with support for multiple encryption backends:

EncryptedString
~~~~~~~~~~~~~~~

For storing encrypted string values with configurable length.

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import EncryptedString

    class MyModel(DefaultBase):
        secret: Mapped[str] = mapped_column(EncryptedString(key="my-secret-key"))

EncryptedText
~~~~~~~~~~~~~

For storing larger encrypted text content (CLOB).

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import EncryptedText

    class MyModel(DefaultBase):
        large_secret: Mapped[str] = mapped_column(EncryptedText(key="my-secret-key"))

Encryption Backends
~~~~~~~~~~~~~~~~~~~

Two encryption backends are available:

- :class:`advanced_alchemy.types.FernetBackend`: Uses Python's cryptography library with Fernet encryption
- :class:`advanced_alchemy.types.PGCryptoBackend`: Uses PostgreSQL's pgcrypto extension (PostgreSQL only)

GUID
----

A platform-independent GUID/UUID type that adapts to different database backends:

- PostgreSQL/DuckDB/CockroachDB: Uses native UUID type
- MSSQL: Uses UNIQUEIDENTIFIER
- Oracle: Uses RAW(16)
- Others: Uses BINARY(16) or CHAR(32)

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import GUID
    from uuid import UUID

    class MyModel(DefaultBase):
        __tablename__ = "my_model"
        id: Mapped[UUID] = mapped_column(GUID, primary_key=True)

BigIntIdentity
--------------

A BigInteger type that automatically falls back to Integer for SQLite:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import BigIntIdentity

    class MyModel(DefaultBase):
        __tablename__ = "my_model"
        id: Mapped[int] = mapped_column(BigIntIdentity, primary_key=True)

JsonB
-----

A JSON type that uses the most efficient JSON storage for each database:

- PostgreSQL/CockroachDB: Uses native JSONB
- Oracle: Uses Binary JSON (BLOB with JSON constraint)
- Others: Uses standard JSON type

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import JsonB

    class MyModel(DefaultBase):
        data: Mapped[dict] = mapped_column(JsonB)

File Object Storage
-------------------

Advanced Alchemy provides a powerful file object storage system through the :class:`StoredObject` type. This system supports multiple storage backends and provides automatic file cleanup.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types.file_object import FileObject, StoredObject

    class Document(UUIDBase):
        __tablename__ = "documents"

        # Single file storage
        attachment: Mapped[Optional[FileObject]] = mapped_column(
            StoredObject(backend="local_test_store"),
            nullable=True,
        )

        # Multiple file storage
        images: Mapped[Optional[FileObjectList]] = mapped_column(
            StoredObject(backend="local_test_store", multiple=True),
            nullable=True,
        )

Storage Backends
~~~~~~~~~~~~~~~~

Two storage backends are available:

FSSpec Backend
^^^^^^^^^^^^^^

The FSSpec backend uses the `fsspec <https://filesystem-spec.readthedocs.io/>`_ library to support various storage systems:

.. code-block:: python

    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    # Local filesystem
    fs = fsspec.filesystem("file")
    backend = FSSpecBackend(fs=fs, key="local")

    # S3 storage
    fs = fsspec.S3FileSystem(
        anon=False,
        key="your-access-key",
        secret="your-secret-key",
        endpoint_url="https://your-s3-endpoint",
    )
    backend = FSSpecBackend(fs=fs, key="s3", prefix="your-bucket")

Obstore Backend
^^^^^^^^^^^^^^^

The Obstore backend provides a simple interface for object storage:

.. code-block:: python

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    # Local storage
    backend = ObstoreBackend(
        key="local",
        fs="file:///path/to/storage",
    )

    # S3 storage
    backend = ObstoreBackend(
        key="s3",
        fs="s3://your-bucket/",
        aws_access_key_id="your-access-key",
        aws_secret_access_key="your-secret-key",
        aws_endpoint="https://your-s3-endpoint",
    )

File Operations
~~~~~~~~~~~~~~~

The FileObject class provides various operations for managing files:

.. code-block:: python

    # Save a file
    file_obj = FileObject(
        backend="local_test_store",
        filename="test.txt",
        content=b"Hello, World!",
    )
    await file_obj.save_async()

    # Get file content
    content = await file_obj.get_content_async()

    # Delete a file
    await file_obj.delete_async()

    # Get signed URL
    url = await file_obj.sign_async(expires_in=3600)  # URL expires in 1 hour

Metadata
~~~~~~~~

File objects support metadata storage:

.. code-block:: python

    file_obj = FileObject(
        backend="local_test_store",
        filename="test.txt",
        metadata={
            "category": "document",
            "tags": ["important", "review"],
        },
    )

    # Update metadata
    file_obj.update_metadata({"priority": "high"})

Automatic Cleanup
~~~~~~~~~~~~~~~~~

When a file object is removed from a model or the model is deleted, the associated file is automatically deleted from storage:

.. code-block:: python

    # Update file
    doc.attachment = new_file_obj
    await session.commit()  # Old file is automatically deleted

    # Clear file
    doc.attachment = None
    await session.commit()  # File is automatically deleted

    # Delete model
    await session.delete(doc)
    await session.commit()  # All associated files are automatically deleted

Using Types with Alembic
------------------------

If you are not using Advanced Alchemy's built-in `alembic` templates, you need to properly configure your ``script.py.mako`` template. The key is to make the custom types available through the ``sa`` namespace that Alembic uses.

Type Aliasing
~~~~~~~~~~~~~

In your ``script.py.mako``, you'll need both the imports and the type aliasing:

.. code-block:: python
    :caption: script.py.mako

    """${message}

    Revision ID: ${up_revision}
    Revises: ${down_revision | comma,n}
    Create Date: ${create_date}

    """
    import sqlalchemy as sa
    # ...

    # Import the types
    from advanced_alchemy.types import (
        EncryptedString,
        EncryptedText,
        GUID,
        ORA_JSONB,
        DateTimeUTC,
        StoredObject,
    )

    # Create aliases in the sa namespace
    sa.GUID = GUID
    sa.DateTimeUTC = DateTimeUTC
    sa.ORA_JSONB = ORA_JSONB
    sa.EncryptedString = EncryptedString
    sa.EncryptedText = EncryptedText
    sa.StoredObject = StoredObject
    # ...

.. note::

    These assignments are necessary because alembic uses the ``sa`` namespace when generating migrations.
    Without these aliases, Alembic might not properly reference the custom types.


This allows you to use the types in migrations like this:

.. code-block:: python

    # In generated migration file
    def upgrade():
        op.create_table(
            'users',
            sa.Column('id', sa.GUID(), primary_key=True),
            sa.Column('created_at', sa.DateTimeUTC(), nullable=False),
            sa.Column('secret', sa.EncryptedString(), nullable=True),
            sa.Column('avatar', sa.StoredObject(backend="local_store"), nullable=True),
        )

==============
Advanced Types
==============

Advanced Alchemy provides several custom SQLAlchemy types that handle common requirements like encryption, UTC datetimes, and file storage.

All types include:

- Proper Python type annotations for modern IDE support
- Automatic dialect-specific implementations
- Consistent behavior across different database backends
- Integration with SQLAlchemy's type system

.. code-block:: python

    from typing import Optional, Union
    from uuid import UUID
    from datetime import datetime
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import (
        DateTimeUTC,
        EncryptedString,
        GUID,
        JsonB,
        StoredObject,
        FileObject,
    )

    class User(BigIntBase):
        __tablename__ = "users"
        id: Mapped[UUID] = mapped_column(GUID, primary_key=True)
        created_at: Mapped[datetime] = mapped_column(DateTimeUTC)
        password: Mapped[str] = mapped_column(EncryptedString(key="secret-key"))
        preferences: Mapped[dict] = mapped_column(JsonB)
        avatar: Mapped[Optional[FileObject]] = mapped_column(StoredObject(backend="local_store"))


DateTime UTC
------------

- Ensures all datetime values are stored in UTC
- Requires timezone information for input values
- Automatically converts stored values to UTC timezone
- Returns timezone-aware datetime objects

.. code-block:: python

    from datetime import datetime
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import DateTimeUTC

    class MyModel(BigIntBase):
        created_at: Mapped[datetime] = mapped_column(DateTimeUTC)


Encrypted Types
---------------

Advanced Alchemy supports two types for storing encrypted data with multiple encryption backends.

EncryptedString
~~~~~~~~~~~~~~~

For storing encrypted string values with configurable length.

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import EncryptedString

    class MyModel(BigIntBase):
        secret: Mapped[str] = mapped_column(EncryptedString(key="my-secret-key"))

EncryptedText
~~~~~~~~~~~~~

For storing larger encrypted text content (CLOB).

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import EncryptedText

    class MyModel(BigIntBase):
        large_secret: Mapped[str] = mapped_column(EncryptedText(key="my-secret-key"))

Encryption Backends
~~~~~~~~~~~~~~~~~~~

Two encryption backends are available:

- :class:`FernetBackend <advanced_alchemy.types.encrypted_string.FernetBackend>`: Uses Python's ``cryptography`` library with Fernet encryption.
- :class:`PGCryptoBackend <advanced_alchemy.types.encrypted_string.PGCryptoBackend>`: Uses PostgreSQL's ``pgcrypto`` extension (PostgreSQL only).

GUID
----

A platform-independent GUID/UUID type that adapts to different database backends:

- **PostgreSQL/DuckDB/CockroachDB**: Uses native UUID type
- **MSSQL**: Uses UNIQUEIDENTIFIER
- **Oracle**: Uses RAW(16)
- **Others**: Uses BINARY(16) or CHAR(32)

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import GUID
    from uuid import UUID

    class MyModel(BigIntBase):
        __tablename__ = "my_model"
        id: Mapped[UUID] = mapped_column(GUID, primary_key=True)

JsonB
-----

A JSON type that uses the most efficient JSON storage for each database:

- **PostgreSQL/CockroachDB**: Uses native JSONB
- **Oracle**: Uses Binary JSON (BLOB with JSON constraint)
- **Others**: Uses standard JSON type

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import JsonB

    class MyModel(BigIntBase):
        data: Mapped[dict] = mapped_column(JsonB)

Password Hash
-------------

A type for storing password hashes with configurable backends. Currently supports:

- :class:`~advanced_alchemy.types.password_hash.pwdlib.PwdlibHasher`: Uses ``pwdlib``
- :class:`~advanced_alchemy.types.password_hash.argon2.Argon2Hasher`: Uses ``argon2-cffi``
- :class:`~advanced_alchemy.types.password_hash.passlib.PasslibHasher`: Uses ``passlib``

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import PasswordHash
    from advanced_alchemy.types.password_hash.pwdlib import PwdlibHasher
    from pwdlib.hashers.argon2 import Argon2Hasher as PwdlibArgon2Hasher

    class MyModel(BigIntBase):
        __tablename__ = "my_model"
        password: Mapped[str] = mapped_column(
            PasswordHash(backend=PwdlibHasher(hasher=PwdlibArgon2Hasher()))
        )

File Object Storage
-------------------

Advanced Alchemy provides a powerful file object storage system through the :class:`StoredObject` type. This system supports multiple storage backends and provides automatic file cleanup.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from typing import Optional
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types.file_object import FileObject, FileObjectList, StoredObject
    from sqlalchemy.orm import Mapped, mapped_column

    class Document(UUIDBase):
        __tablename__ = "documents"

        # Single file storage
        attachment: Mapped[Optional[FileObject]] = mapped_column(
            StoredObject(backend="s3"),
            nullable=True
        )

        # Multiple file storage
        images: Mapped[Optional[FileObjectList]] = mapped_column(
            StoredObject(backend="s3", multiple=True),
            nullable=True
        )

Storage Backends
~~~~~~~~~~~~~~~~

- **FSSpec Backend**: Supports various storage systems using the ``fsspec`` library.
- **Obstore Backend**: Provides a simple interface for object storage (S3, GCS, etc).

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

When a file object is removed from a model or the model is deleted, the associated file is automatically saved or deleted from storage.

.. note::

    The listener events are automatically configured when using any of the framework adapters. You may manually configure these events by calling the ``configure_listeners`` method on the configuration class.

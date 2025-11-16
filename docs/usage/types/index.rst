=============
Custom Types
=============

Advanced Alchemy provides SQLAlchemy custom types that adapt to different database backends, ensure data integrity, and provide Python-native type annotations.

Learning Path
=============

Follow this progression to master Advanced Alchemy types:

.. grid:: 1 1 4 4
    :gutter: 2

    .. grid-item-card:: 1. Basic Types
        :link: basic-types
        :link-type: doc
        :text-align: center

        GUID, DateTimeUTC, JsonB, and identity types

    .. grid-item-card:: 2. Security Types
        :link: security-types
        :link-type: doc
        :text-align: center

        EncryptedString and PasswordHash

    .. grid-item-card:: 3. File Storage
        :link: file-storage
        :link-type: doc
        :text-align: center

        FileObject and cloud storage integration

    .. grid-item-card:: 4. Advanced Types
        :link: advanced-types
        :link-type: doc
        :text-align: center

        Mutable collections and custom types

.. toctree::
   :hidden:
   :maxdepth: 1

   basic-types
   security-types
   file-storage
   advanced-types

Prerequisites
=============

- Understanding of :doc:`../modeling/basics`
- Python 3.9+
- SQLAlchemy 2.0+

Overview
========

Advanced Alchemy custom types provide:

- Automatic dialect-specific implementations
- Python type annotation support
- Consistent behavior across database backends
- Integration with SQLAlchemy's type system

Quick Reference
---------------

.. code-block:: python

    from typing import Optional
    from uuid import UUID
    from datetime import datetime
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDAuditBase
    from advanced_alchemy.types import (
        GUID,
        DateTimeUTC,
        JsonB,
        EncryptedString,
        PasswordHash,
        FileObject,
        StoredObject,
    )

    class User(UUIDAuditBase):
        __tablename__ = "users"

        # UUID primary key (handled by UUIDAuditBase)
        email: "Mapped[str]" = mapped_column(unique=True)

        # UTC timezone-aware datetime
        last_login: "Mapped[Optional[datetime]]" = mapped_column(DateTimeUTC)

        # Efficient JSON storage
        preferences: "Mapped[dict]" = mapped_column(JsonB)

        # Encrypted password
        password: "Mapped[str]" = mapped_column(
            EncryptedString(key="encryption-key")
        )

        # File storage
        avatar: "Mapped[Optional[FileObject]]" = mapped_column(
            StoredObject(backend="s3")
        )

Database Compatibility
----------------------

Advanced Alchemy custom types work across all supported database backends:

.. list-table::
   :header-rows: 1
   :widths: 20 15 15 15 15 20

   * - Type
     - PostgreSQL
     - SQLite
     - Oracle
     - MySQL
     - Others
   * - GUID
     - UUID
     - BINARY(16)
     - RAW(16)
     - BINARY(16)
     - BINARY(16)
   * - DateTimeUTC
     - TIMESTAMP
     - DATETIME
     - TIMESTAMP
     - DATETIME
     - DATETIME
   * - JsonB
     - JSONB
     - JSON
     - BLOB+CHECK
     - JSON
     - JSON
   * - BigIntIdentity
     - BIGINT
     - INTEGER
     - NUMBER(19)
     - BIGINT
     - BIGINT
   * - EncryptedString
     - VARCHAR
     - VARCHAR
     - VARCHAR2
     - VARCHAR
     - VARCHAR
   * - FileObject
     - JSON/JSONB
     - JSON
     - BLOB+CHECK
     - JSON
     - JSON

Type Selection Guide
--------------------

**For UUID primary keys:**

- Use base classes: :class:`~advanced_alchemy.base.UUIDBase`, :class:`~advanced_alchemy.base.UUIDAuditBase`
- Manual column: :class:`~advanced_alchemy.types.GUID` type

**For timestamps:**

- Use base classes with audit columns: :class:`~advanced_alchemy.base.UUIDAuditBase`, :class:`~advanced_alchemy.base.BigIntAuditBase`
- Manual column: :class:`~advanced_alchemy.types.DateTimeUTC` type

**For JSON data:**

- PostgreSQL/Oracle/CockroachDB: :class:`~advanced_alchemy.types.JsonB` uses native binary JSON
- Other databases: Standard JSON type

**For sensitive data:**

- Passwords: :class:`~advanced_alchemy.types.PasswordHash` with automatic hashing
- Encrypted fields: :class:`~advanced_alchemy.types.EncryptedString` or :class:`~advanced_alchemy.types.EncryptedText`

**For file storage:**

- Cloud storage: :class:`~advanced_alchemy.types.StoredObject` with S3/GCS/Azure backends
- Local storage: :class:`~advanced_alchemy.types.StoredObject` with local filesystem backend

Next Steps
==========

- :doc:`basic-types` - GUID, DateTimeUTC, JsonB, and identity types
- :doc:`security-types` - EncryptedString and PasswordHash
- :doc:`file-storage` - FileObject and cloud storage integration
- :doc:`advanced-types` - Mutable collections and custom types

Related Topics
==============

- :doc:`../modeling/index` - Using types in models
- :doc:`../storage/index` - Storage backend configuration

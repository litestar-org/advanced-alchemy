==============
Advanced Types
==============

Advanced Alchemy provides dialect-adaptive SQLAlchemy column types in :mod:`advanced_alchemy.types` with strict Python type annotations. Security and file storage types are covered in :doc:`security_and_storage_types`.

DateTimeUTC
-----------

:class:`~advanced_alchemy.types.DateTimeUTC` normalizes timezone-aware ``datetime`` values to UTC on write and returns timezone-aware UTC ``datetime`` instances on read across all dialects:

.. code-block:: python

    from datetime import datetime
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import DateTimeUTC


    class AuditLogRecord(BigIntBase):
        __tablename__ = "audit_log_record"

        occurred_at: Mapped[datetime] = mapped_column(DateTimeUTC)

GUID and UUIDv7 Keys
--------------------

:class:`~advanced_alchemy.types.GUID` stores UUID values using the native ``UUID`` type on PostgreSQL, DuckDB, and CockroachDB, ``UNIQUEIDENTIFIER`` on MSSQL, ``RAW(16)`` on Oracle, and ``BINARY(16)`` or ``CHAR(32)`` on other dialects:

.. code-block:: python

    from uuid import UUID
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase, UUIDv7AuditBase
    from advanced_alchemy.types import GUID


    class ExternalIdentity(DefaultBase):
        __tablename__ = "external_identity"

        id: Mapped[UUID] = mapped_column(GUID, primary_key=True)


    class TimeOrderedOrder(UUIDv7AuditBase):
        __tablename__ = "time_ordered_orders"

For primary keys, prefer :class:`~advanced_alchemy.base.UUIDv7Base` or :class:`~advanced_alchemy.base.UUIDv7AuditBase` so monotonic RFC 9562 timestamps keep B-tree indexes balanced.

BigIntIdentity
--------------

:class:`~advanced_alchemy.types.BigIntIdentity` maps to ``BIGINT`` on relational databases while falling back to ``INTEGER`` on SQLite so auto-incrementing primary keys work seamlessly in SQLite test suites:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import DefaultBase
    from advanced_alchemy.types import BigIntIdentity


    class LedgerEntry(DefaultBase):
        __tablename__ = "ledger_entry"

        id: Mapped[int] = mapped_column(BigIntIdentity, primary_key=True)
        description: Mapped[str]

JsonB
-----

:class:`~advanced_alchemy.types.JsonB` selects native ``JSONB`` on PostgreSQL and CockroachDB, Binary JSON (``BLOB`` with JSON constraint) on Oracle, and standard ``JSON`` on other dialects:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import JsonB


    class SettingsRecord(BigIntBase):
        __tablename__ = "settings_record"

        preferences: Mapped[dict[str, str]] = mapped_column(JsonB)

Vector Embeddings
-----------------

:class:`~advanced_alchemy.types.Vector` stores fixed-dimension float embeddings for similarity search on PostgreSQL (``pgvector``), Oracle 23ai+, CockroachDB, DuckDB, and JSON/array fallbacks on SQLite:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import Vector


    class DocumentChunk(UUIDBase):
        __tablename__ = "document_chunk"

        embedding: Mapped[list[float]] = mapped_column(Vector(dim=3))

Related Guides
--------------

- :doc:`security_and_storage_types` — ``EncryptedString``, ``EncryptedText``, ``PasswordHash``, ``TOTPSecret``, ``OneTimeCode``, and ``StoredObject``.
- :doc:`/reference/types` — Complete custom types API reference.

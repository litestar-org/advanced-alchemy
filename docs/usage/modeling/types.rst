=====================
Portable Column Types
=====================

Different SQL databases use different column types for UUIDs, UTC timestamps, JSON, and AI vector embeddings—especially when you test against SQLite locally and deploy to PostgreSQL, MySQL, or Oracle in production.

Advanced Alchemy's column types automatically pick the best native database type on each engine while keeping your Python types consistent.

Common Column Types at a Glance
-------------------------------

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Column Type
     - What It Does
   * - ``DateTimeUTC``
     - Converts datetimes to UTC before saving and always returns timezone-aware UTC datetimes on read.
   * - ``GUID``
     - Stores Python ``UUID`` objects natively on PostgreSQL, CockroachDB, DuckDB, MSSQL, and Oracle, or compactly on SQLite/MySQL.
   * - ``BigIntIdentity``
     - Uses 64-bit ``BIGINT`` in production and ``INTEGER`` on SQLite so auto-incrementing IDs work in local tests.
   * - ``JsonB``
     - Uses fast binary JSON on PostgreSQL, CockroachDB, and Oracle, and standard ``JSON`` everywhere else.
   * - ``Vector(dim=...)``
     - Stores float embeddings for similarity search (``pgvector``, Oracle 23ai+, CockroachDB, DuckDB, and SQLite fallback).

Examples by Type
----------------

.. tab-set::

    .. tab-item:: Timestamps & JSON

        .. code-block:: python

            from datetime import datetime
            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import BigIntBase
            from advanced_alchemy.types import DateTimeUTC, JsonB


            class AuditEvent(BigIntBase):
                __tablename__ = "audit_event"

                occurred_at: Mapped[datetime] = mapped_column(DateTimeUTC)
                metadata_payload: Mapped[dict[str, str]] = mapped_column(JsonB)

    .. tab-item:: UUIDs & Integer Keys

        .. code-block:: python

            from uuid import UUID
            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import DefaultBase
            from advanced_alchemy.types import BigIntIdentity, GUID


            class LedgerEntry(DefaultBase):
                __tablename__ = "ledger_entry"

                id: Mapped[int] = mapped_column(BigIntIdentity, primary_key=True)
                external_ref: Mapped[UUID] = mapped_column(GUID, index=True)

    .. tab-item:: Vector Embeddings

        .. code-block:: python

            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import UUIDv7Base
            from advanced_alchemy.types import Vector


            class DocumentChunk(UUIDv7Base):
                __tablename__ = "document_chunk"

                embedding: Mapped[list[float]] = mapped_column(Vector(dim=3))

Related Guides
--------------

* :doc:`security_and_storage_types` — Field encryption, password hashing, authenticator codes, and uploaded files.
* :doc:`/reference/types` — Full API reference for ``advanced_alchemy.types``.

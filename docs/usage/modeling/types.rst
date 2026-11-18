=====================
Portable Column Types
=====================

Advanced Alchemy provides custom SQLAlchemy ``TypeDecorator`` implementations that compile to dialect-appropriate SQL types across SQLite, PostgreSQL, CockroachDB, MySQL, MariaDB, Oracle, DuckDB, SQL Server, and Spanner while preserving consistent Python types.

Common Column Types at a Glance
-------------------------------

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Column Type
     - Description
   * - ``DateTimeUTC``
     - Converts datetimes to UTC before saving, returns timezone-aware UTC datetimes on read, and supports configurable fractional-second precision (``DateTimeUTC(fsp=6)``).
   * - ``GUID``
     - Stores Python ``UUID`` objects using native ``UUID`` / ``UNIQUEIDENTIFIER`` types on PostgreSQL, CockroachDB, DuckDB, and SQL Server, ``RAW(16)`` or ``CHAR(32)`` on Oracle, and ``BINARY(16)`` or ``CHAR(32)`` on SQLite and MySQL.
   * - ``BigIntIdentity``
     - Compiles to 64-bit ``BIGINT`` on server databases and ``INTEGER`` on SQLite so auto-incrementing primary keys work across dialects.
   * - ``JsonB``
     - Compiles to binary JSON on PostgreSQL, CockroachDB (``JSONB``), and Oracle (``ORA_JSONB``), and standard ``JSON`` on other dialects.
   * - ``Vector(dim=...)``
     - Stores float vector embeddings using native vector columns on PostgreSQL (``pgvector``), CockroachDB, and Oracle 23ai+, with ``JSON`` array storage on SQLite, DuckDB, and other dialects.

Oracle JSON storage
-------------------

``JsonB`` and ``ORA_JSONB`` use native ``JSON`` on Oracle 21c and later
with SQLAlchemy 2.1 or later. Older combinations use a ``BLOB`` with an
``IS JSON`` check. On Oracle versions before 21c, JSON documents must be
objects or arrays at the top level. Python ``None`` maps to SQL ``NULL``.

Use ``ORA_JSONB(use_blob=True)`` to map an existing Oracle BLOB column
when upgrading to a combination that supports native JSON. If earlier
writes double-encoded a value, Oracle stores it as a JSON string. Repair
those rows explicitly using the expected application data shape.

Examples by Type
----------------

.. tab-set::

    .. tab-item:: Timestamps & JSON

        .. code-block:: python

            from datetime import datetime
            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import BigIntBase, UUIDBase, create_registry
            from advanced_alchemy.types import DateTimeUTC, JsonB


            class AuditEvent(BigIntBase):
                __tablename__ = "audit_event"

                occurred_at: Mapped[datetime] = mapped_column(DateTimeUTC(fsp=6))
                metadata_payload: Mapped[dict[str, str]] = mapped_column(JsonB)


            class PrecisionBase(UUIDBase):
                __abstract__ = True
                registry = create_registry(custom_annotation_map={datetime: DateTimeUTC(fsp=6)})

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

.. note::

    On MySQL/MariaDB and Oracle, SQLAlchemy's default ``DateTime(timezone=True)`` stores whole seconds only. Pass ``DateTimeUTC(fsp=6)`` (or set ``custom_annotation_map={datetime: DateTimeUTC(fsp=6)}`` via :func:`~advanced_alchemy.base.create_registry`) to preserve microseconds, or pass ``DateTimeUTC(fsp=0)`` to keep legacy whole-second DDL without migration churn. In v2.0, ``fsp=6`` becomes the default.

Storing Python Enums
--------------------

By default, SQLAlchemy's ``Enum`` persists member **names** (such as ``"ACTIVE"``). Pass ``values_callable`` when your database schema stores member **values** (such as ``"active"``), and set ``native_enum=False`` for portable ``VARCHAR`` constraints across backends:

.. code-block:: python

    import enum
    import sqlalchemy as sa
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase


    class JobState(str, enum.Enum):
        PENDING = "pending"
        RUNNING = "running"


    class BackgroundJob(BigIntBase):
        __tablename__ = "types_background_job"
        state: Mapped[JobState] = mapped_column(
            sa.Enum(JobState, values_callable=lambda obj: [item.value for item in obj], native_enum=False),
            default=JobState.PENDING,
        )

Related Guides
--------------

* :doc:`security_and_storage_types`: Field encryption, password hashing, authenticator codes, and file storage.
* :doc:`/reference/types`: Full API reference for ``advanced_alchemy.types``.

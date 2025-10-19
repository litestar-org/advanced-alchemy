====
base
====

.. currentmodule:: advanced_alchemy.base

Base model classes for SQLAlchemy ORM with common patterns and functionality.

.. automodule:: advanced_alchemy.base
    :no-members:
    :show-inheritance:

UUID Primary Key Models
------------------------

.. autoclass:: UUIDBase
   :members:
   :show-inheritance:

Base model with UUID primary key (UUID v4).

.. autoclass:: UUIDAuditBase
   :members:
   :show-inheritance:

Base model with UUID primary key and audit columns (created_at, updated_at).

.. autoclass:: UUIDv6Base
   :members:
   :show-inheritance:

Base model with UUID v6 primary key (time-ordered).

.. autoclass:: UUIDv7Base
   :members:
   :show-inheritance:

Base model with UUID v7 primary key (time-ordered, improved sorting).

BigInt Primary Key Models
--------------------------

.. autoclass:: BigIntBase
   :members:
   :show-inheritance:

Base model with BigInt auto-incrementing primary key.

.. autoclass:: BigIntAuditBase
   :members:
   :show-inheritance:

Base model with BigInt primary key and audit columns (created_at, updated_at).

NanoID Primary Key Models
--------------------------

.. autoclass:: NanoIDBase
   :members:
   :show-inheritance:

Base model with NanoID primary key (requires nanoid extra).

Declarative Base
----------------

.. autoclass:: AdvancedDeclarativeBase
   :members:
   :show-inheritance:
   :exclude-members: registry

Enhanced declarative base with additional functionality.

.. autoclass:: CommonTableAttributes
   :members:
   :show-inheritance:

Common attributes mixed into all base models.

.. autoclass:: BasicAttributes
   :members:
   :show-inheritance:
   :exclude-members: to_dict

Basic attributes for models (id, to_dict).

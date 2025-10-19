=====
types
=====

.. currentmodule:: advanced_alchemy.types

Custom SQLAlchemy types for use with the ORM.

.. automodule:: advanced_alchemy.types
    :no-members:
    :show-inheritance:

Core Types
----------

.. autoclass:: GUID
   :members:
   :show-inheritance:

SQLAlchemy type for UUID/GUID columns with database-specific implementations.

.. autoclass:: JsonB
   :members:
   :show-inheritance:

Enhanced JSON type with JSONB support for PostgreSQL and optimized storage for other databases.

.. autoclass:: DateTimeUTC
   :members:
   :show-inheritance:

DateTime type that enforces UTC timezone and provides timezone-aware operations.

.. autoclass:: ORA_JSONB
   :members:
   :show-inheritance:

Oracle-specific JSON type using native JSON column support (Oracle 21c+).

File Storage
------------

.. autoclass:: FileObject
   :members:
   :show-inheritance:

SQLAlchemy type for file storage with support for multiple backends (fsspec, obstore).

.. autoclass:: FileObjectList
   :members:
   :show-inheritance:

List of FileObject instances with SQLAlchemy integration.

.. autoclass:: StoredObject
   :members:
   :show-inheritance:

Internal representation of a stored file.

.. autoclass:: StorageBackend
   :members:
   :show-inheritance:

.. autoclass:: StorageRegistry
   :members:
   :show-inheritance:

Security Types
--------------

.. autoclass:: EncryptedString
   :members:
   :show-inheritance:

SQLAlchemy type for encrypted string storage.

.. autoclass:: EncryptedText
   :members:
   :show-inheritance:

SQLAlchemy type for encrypted text storage (longer content).

.. autoclass:: password_hash.HashedPassword
   :members:
   :show-inheritance:

SQLAlchemy type for password hashing with pluggable hashers.

.. autoclass:: PasswordHash
   :members:
   :show-inheritance:

Password hash type wrapper.

Encryption Backends
-------------------

.. autoclass:: EncryptionBackend
   :members:
   :show-inheritance:

.. autoclass:: FernetBackend
   :members:
   :show-inheritance:

.. autoclass:: encrypted_string.PGCryptoBackend
   :members:
   :show-inheritance:

Password Hashers
----------------

.. autoclass:: password_hash.argon2.Argon2Hasher
   :members:
   :show-inheritance:

.. autoclass:: password_hash.passlib.PasslibHasher
   :members:
   :show-inheritance:

.. autoclass:: password_hash.pwdlib.PwdlibHasher
   :members:
   :show-inheritance:

Mutable Types
-------------

.. autoclass:: MutableList
   :members:
   :show-inheritance:

SQLAlchemy mutable list type that tracks changes.

Utilities
---------

.. autoclass:: BigIntIdentity
   :members:
   :show-inheritance:

Constants
---------

.. autodata:: NANOID_INSTALLED
   :annotation:

Flag indicating if nanoid library is installed.

.. autodata:: UUID_UTILS_INSTALLED
   :annotation:

Flag indicating if uuid-utils library is installed.

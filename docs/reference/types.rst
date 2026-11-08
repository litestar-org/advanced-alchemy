=====
types
=====

.. py:module:: advanced_alchemy.types

Identifiers, Timestamps & JSON Types
------------------------------------

.. autoclass:: advanced_alchemy.types.GUID
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.DateTimeUTC
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. py:data:: BigIntIdentity
    :type: sqlalchemy.types.TypeEngine

    Dialect-aware 64-bit integer identity column type.

.. py:data:: JsonB
    :type: sqlalchemy.types.TypeEngine

    Dialect-aware JSONB column type with binary JSON support on PostgreSQL and Oracle.

.. autoclass:: advanced_alchemy.types.ORA_JSONB
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.Bool
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.Vector
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.MutableList
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. py:data:: UUID_UTILS_INSTALLED
    :type: bool

    Boolean flag indicating whether ``uuid-utils`` is installed.

.. py:data:: NANOID_INSTALLED
    :type: bool

    Boolean flag indicating whether ``fastnanoid`` is installed.

Object Storage Types & Registry
-------------------------------

.. autoclass:: advanced_alchemy.types.StoredObject
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.FileObject
    :members: save, save_async, get_content, get_content_async, delete, delete_async, sign, sign_async
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.FileObjectList
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.StorageBackend
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.StorageRegistry
    :members: register_backend, get_backend, set_default_backend, is_registered, unregister_backend, clear_backends
    :no-inherited-members:
    :show-inheritance:

.. py:data:: storages
    :type: StorageRegistry

    Default global :class:`~advanced_alchemy.types.StorageRegistry` singleton.

.. autodata:: advanced_alchemy.types.StorageBackendT
    :no-value:

Encryption & Password Hashing
-----------------------------

.. autoclass:: advanced_alchemy.types.EncryptedString
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.EncryptedText
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.EncryptionBackend
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.FernetBackend
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.PGCryptoBackend
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.PasswordHash
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.password_hash.base.HashingBackend
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.HashedPassword
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.password_hash.argon2.Argon2Hasher
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.password_hash.bcrypt.BcryptHasher
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.password_hash.passlib.PasslibHasher
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.password_hash.pwdlib.PwdlibHasher
    :no-members:
    :no-inherited-members:
    :show-inheritance:

One-Time Codes & TOTP
---------------------

.. autoclass:: advanced_alchemy.types.OneTimeCode
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.HashedOneTimeCode
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.types.generate_one_time_code

.. autoclass:: advanced_alchemy.types.TOTPSecret
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.types.TOTPProvider
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.types.generate_totp_secret

==============
Security Types
==============

SQLAlchemy types for handling sensitive data with encryption and password hashing.

EncryptedString
---------------

Type for storing encrypted string values with configurable encryption backends.

**Characteristics:**

- Python type: :class:`str`
- Storage: Encrypted VARCHAR/VARCHAR2
- Automatic encryption/decryption
- Configurable encryption backend
- Configurable maximum length

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import EncryptedString

    class User(UUIDBase):
        __tablename__ = "users"

        email: "Mapped[str]" = mapped_column(unique=True)
        api_key: "Mapped[str]" = mapped_column(
            EncryptedString(key="your-encryption-key")
        )
        ssn: "Mapped[str]" = mapped_column(
            EncryptedString(key="your-encryption-key", length=255)
        )

Storing Encrypted Data
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

    async def create_user(session: AsyncSession) -> User:
        user = User(
            email="user@example.com",
            api_key="sk_live_abc123xyz",  # Encrypted automatically
        )
        session.add(user)
        await session.commit()
        return user

Retrieving Decrypted Data
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    async def get_api_key(session: AsyncSession, user_id: UUID) -> str:
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one()
        return user.api_key  # Decrypted automatically

EncryptedText
-------------

Type for storing larger encrypted text content (CLOB/TEXT).

**Characteristics:**

- Python type: :class:`str`
- Storage: Encrypted TEXT/CLOB
- Automatic encryption/decryption
- No length limit (database-dependent)

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import EncryptedText

    class SecureDocument(UUIDBase):
        __tablename__ = "secure_documents"

        title: "Mapped[str]"
        content: "Mapped[str]" = mapped_column(
            EncryptedText(key="your-encryption-key")
        )

Storing Large Encrypted Content
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    async def create_document(session: AsyncSession, content: str) -> SecureDocument:
        document = SecureDocument(
            title="Confidential Report",
            content=content,  # Large text encrypted automatically
        )
        session.add(document)
        await session.commit()
        return document

Encryption Backends
-------------------

Two encryption backends are available for EncryptedString and EncryptedText.

FernetBackend (Default)
~~~~~~~~~~~~~~~~~~~~~~~

Uses Python's cryptography library with Fernet encryption.

**Characteristics:**

- Implementation: AES-128 in CBC mode with HMAC
- Key format: 32 URL-safe base64-encoded bytes
- Platform: Pure Python, works on all databases

.. code-block:: python

    from advanced_alchemy.types import EncryptedString
    from advanced_alchemy.types.encrypted_string import FernetBackend

    # Explicit backend (default)
    api_key: "Mapped[str]" = mapped_column(
        EncryptedString(
            key="your-encryption-key",
            backend=FernetBackend,
        )
    )

Generating Fernet Keys
""""""""""""""""""""""

.. code-block:: python

    from cryptography.fernet import Fernet

    # Generate a new key
    encryption_key = Fernet.generate_key()
    print(encryption_key)  # b'...' (32 bytes, base64-encoded)

    # Store securely (environment variable, key management service)
    import os
    os.environ["ENCRYPTION_KEY"] = encryption_key.decode()

PGCryptoBackend
~~~~~~~~~~~~~~~

Uses PostgreSQL's pgcrypto extension for database-side encryption.

**Characteristics:**

- Implementation: PostgreSQL pgcrypto extension
- Encryption: Server-side (within PostgreSQL)
- Platform: PostgreSQL only
- Requirement: pgcrypto extension enabled

.. code-block:: python

    from advanced_alchemy.types import EncryptedString
    from advanced_alchemy.types.encrypted_string import PGCryptoBackend

    # PostgreSQL pgcrypto backend
    api_key: "Mapped[str]" = mapped_column(
        EncryptedString(
            key="your-encryption-key",
            backend=PGCryptoBackend,
        )
    )

Enabling pgcrypto Extension
""""""""""""""""""""""""""""

.. code-block:: sql

    -- PostgreSQL setup
    CREATE EXTENSION IF NOT EXISTS pgcrypto;

PasswordHash
------------

Type for storing password hashes with automatic hashing and verification.

**Characteristics:**

- Python type: :class:`str` (plaintext) or :class:`~advanced_alchemy.types.password_hash.HashedPassword`
- Storage: Hashed string (VARCHAR/TEXT)
- Automatic hashing on assignment
- Verification support
- Configurable hashing backend

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import PasswordHash

    class User(UUIDBase):
        __tablename__ = "users"

        email: "Mapped[str]" = mapped_column(unique=True)
        password: "Mapped[str]" = mapped_column(PasswordHash)

Storing Passwords
~~~~~~~~~~~~~~~~~

.. code-block:: python

    async def create_user(session: AsyncSession, email: str, password: str) -> User:
        user = User(
            email=email,
            password=password,  # Hashed automatically
        )
        session.add(user)
        await session.commit()
        return user

    # Password is now hashed in database
    # user.password contains hash, not plaintext

Verifying Passwords
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.password_hash import HashedPassword

    async def verify_login(
        session: AsyncSession,
        email: str,
        password: str
    ) -> "Optional[User]":
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            return None

        # Verify password
        hashed = HashedPassword(user.password)
        if hashed.verify(password):
            return user

        return None

Password Hashing Backends
--------------------------

Three password hashing backends are available.

PwdlibHasher (Default)
~~~~~~~~~~~~~~~~~~~~~~

Uses pwdlib library with configurable hashers.

**Characteristics:**

- Implementation: pwdlib (modern password hashing)
- Default algorithm: Argon2id
- Platform: Pure Python
- Installation: ``pip install "advanced-alchemy[pwdlib]"``

.. code-block:: python

    from advanced_alchemy.types import PasswordHash
    from advanced_alchemy.types.password_hash.pwdlib import PwdlibHasher
    from pwdlib.hashers.argon2 import Argon2Hasher

    # Default (Argon2)
    password: "Mapped[str]" = mapped_column(PasswordHash)

    # Explicit configuration
    password: "Mapped[str]" = mapped_column(
        PasswordHash(
            backend=PwdlibHasher(hasher=Argon2Hasher())
        )
    )

Argon2Hasher
~~~~~~~~~~~~

Uses argon2-cffi for Argon2 password hashing.

**Characteristics:**

- Implementation: argon2-cffi (Argon2id)
- Algorithm: Argon2id (memory-hard)
- Platform: C extension with Python fallback
- Installation: ``pip install "advanced-alchemy[argon2]"``

.. code-block:: python

    from advanced_alchemy.types import PasswordHash
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    password: "Mapped[str]" = mapped_column(
        PasswordHash(backend=Argon2Hasher())
    )

PasslibHasher
~~~~~~~~~~~~~

Uses passlib for flexible password hashing.

**Characteristics:**

- Implementation: passlib (legacy support)
- Default algorithm: bcrypt
- Platform: Pure Python with optional C extensions
- Installation: ``pip install "advanced-alchemy[passlib]"``

.. code-block:: python

    from advanced_alchemy.types import PasswordHash
    from advanced_alchemy.types.password_hash.passlib import PasslibHasher

    password: "Mapped[str]" = mapped_column(
        PasswordHash(backend=PasslibHasher())
    )

Security Considerations
-----------------------

Key Management
~~~~~~~~~~~~~~

Encryption keys must be stored securely:

.. code-block:: python

    import os

    # Environment variable (recommended for deployment)
    encryption_key = os.environ["ENCRYPTION_KEY"]

    # Key management service (AWS KMS, Google Cloud KMS, Azure Key Vault)
    from your_kms import get_encryption_key
    encryption_key = get_encryption_key("user-data-encryption")

    class User(UUIDBase):
        __tablename__ = "users"
        api_key: "Mapped[str]" = mapped_column(
            EncryptedString(key=encryption_key)
        )

Key Rotation
~~~~~~~~~~~~

Rotating encryption keys requires re-encrypting data:

.. code-block:: python

    from advanced_alchemy.types.encrypted_string import FernetBackend

    async def rotate_encryption_key(
        session: AsyncSession,
        old_key: str,
        new_key: str
    ) -> None:
        # Define temporary model with old key
        old_backend = FernetBackend(key=old_key)
        new_backend = FernetBackend(key=new_key)

        # Fetch all users
        stmt = select(User)
        result = await session.execute(stmt)
        users = list(result.scalars())

        for user in users:
            # Decrypt with old key
            decrypted = old_backend.decrypt(user.api_key)
            # Encrypt with new key
            user.api_key = new_backend.encrypt(decrypted)

        await session.commit()

Password Policy
~~~~~~~~~~~~~~~

Enforce password requirements at application level:

.. code-block:: python

    import re

    def validate_password(password: str) -> bool:
        """Validate password meets security requirements."""
        if len(password) < 12:
            return False
        if not re.search(r"[A-Z]", password):
            return False
        if not re.search(r"[a-z]", password):
            return False
        if not re.search(r"[0-9]", password):
            return False
        if not re.search(r"[!@#$%^&*]", password):
            return False
        return True

    async def create_user(
        session: AsyncSession,
        email: str,
        password: str
    ) -> User:
        if not validate_password(password):
            raise ValueError("password does not meet security requirements")

        user = User(email=email, password=password)
        session.add(user)
        await session.commit()
        return user

Common Patterns
---------------

User Authentication
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from datetime import datetime, timezone

    class User(UUIDAuditBase):
        __tablename__ = "users"

        email: "Mapped[str]" = mapped_column(unique=True)
        password: "Mapped[str]" = mapped_column(PasswordHash)
        last_login: "Mapped[Optional[datetime]]" = mapped_column(DateTimeUTC)

    async def authenticate(
        session: AsyncSession,
        email: str,
        password: str
    ) -> "Optional[User]":
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            return None

        hashed = HashedPassword(user.password)
        if not hashed.verify(password):
            return None

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await session.commit()

        return user

API Key Management
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import secrets

    class APIKey(UUIDAuditBase):
        __tablename__ = "api_keys"

        user_id: "Mapped[UUID]" = mapped_column(GUID)
        name: "Mapped[str]"  # "Production API", "Development API"
        key: "Mapped[str]" = mapped_column(EncryptedString(key=ENCRYPTION_KEY))
        last_used: "Mapped[Optional[datetime]]" = mapped_column(DateTimeUTC)

    async def create_api_key(
        session: AsyncSession,
        user_id: UUID,
        name: str
    ) -> tuple[APIKey, str]:
        # Generate secure random key
        key_value = secrets.token_urlsafe(32)

        api_key = APIKey(
            user_id=user_id,
            name=name,
            key=key_value,
        )
        session.add(api_key)
        await session.commit()

        # Return key to user (only time they'll see it)
        return api_key, key_value

    async def verify_api_key(session: AsyncSession, key: str) -> "Optional[APIKey]":
        stmt = select(APIKey)
        result = await session.execute(stmt)
        api_keys = list(result.scalars())

        for api_key in api_keys:
            if api_key.key == key:
                # Update last used
                api_key.last_used = datetime.now(timezone.utc)
                await session.commit()
                return api_key

        return None

See Also
--------

- :doc:`basic-types` - Core SQLAlchemy types
- :doc:`../modeling/index` - Base class integration
- :doc:`/reference/types` - Complete API reference
- `Cryptography Documentation <https://cryptography.io/>`_ - Fernet encryption
- `pwdlib Documentation <https://frankie567.github.io/pwdlib/>`_ - Password hashing

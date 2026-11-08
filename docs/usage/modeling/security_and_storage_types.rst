================================
Security and File Storage Types
================================

Advanced Alchemy provides column types for field-level encryption, one-way password hashing, TOTP multi-factor enrollment, single-use verification codes, and backend-agnostic file storage.

EncryptedString and EncryptedText
---------------------------------

:class:`~advanced_alchemy.types.EncryptedString` and :class:`~advanced_alchemy.types.EncryptedText` encrypt column values at rest using :class:`~advanced_alchemy.types.FernetBackend` (via ``cryptography``) or PostgreSQL's server-side :class:`~advanced_alchemy.types.PGCryptoBackend`. Always pass an explicit ``key`` (string, ``bytes``, or callable):

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import EncryptedString, EncryptedText


    class SecretRecord(BigIntBase):
        __tablename__ = "secret_record"

        api_token: Mapped[str] = mapped_column(EncryptedString(key="my-secret-key"))
        private_notes: Mapped[str] = mapped_column(EncryptedText(key="my-secret-key"))

PasswordHash
------------

:class:`~advanced_alchemy.types.PasswordHash` stores one-way password hashes and hydrates a :class:`~advanced_alchemy.types.HashedPassword` wrapper on read with ``verify()`` and ``verify_and_update()`` methods. Supported backends include :class:`~advanced_alchemy.types.password_hash.argon2.Argon2Hasher`, :class:`~advanced_alchemy.types.password_hash.bcrypt.BcryptHasher`, :class:`~advanced_alchemy.types.password_hash.pwdlib.PwdlibHasher`, and :class:`~advanced_alchemy.types.password_hash.passlib.PasslibHasher`:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import HashedPassword, PasswordHash
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    hasher = Argon2Hasher()


    class AccountRecord(BigIntBase):
        __tablename__ = "account_record"

        password: Mapped[str] = mapped_column(PasswordHash(backend=hasher))


    stored = HashedPassword(hasher.hash("s3cret-passphrase"), hasher)
    verified, upgraded_hash = stored.verify_and_update("s3cret-passphrase")
    assert verified is True

TOTPSecret
----------

:class:`~advanced_alchemy.types.TOTPSecret` encrypts a Base32 TOTP shared secret at rest and returns a :class:`~advanced_alchemy.types.TOTPProvider` on read for generating provisioning URIs and verifying 6-digit authenticator codes:

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import TOTPProvider, TOTPSecret, generate_totp_secret


    class MfaEnrollment(BigIntBase):
        __tablename__ = "mfa_enrollment"

        seed: Mapped[str] = mapped_column(TOTPSecret(key="my-secret-key", issuer="ACME"))


    provider = TOTPProvider(generate_totp_secret(), issuer="ACME")
    uri = provider.provisioning_uri(name="alice@example.com")
    assert uri.startswith("otpauth://totp/")

OneTimeCode
-----------

:class:`~advanced_alchemy.types.OneTimeCode` stores a hashed email/SMS verification code alongside its expiration timestamp, redemption state, and failed attempt counter in a JSON column, returning :class:`~advanced_alchemy.types.HashedOneTimeCode` on read:

.. code-block:: python

    from typing import Any
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.types import HashedOneTimeCode, OneTimeCode, generate_one_time_code
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    otp_hasher = Argon2Hasher()


    class LoginCode(BigIntBase):
        __tablename__ = "login_code"

        code: Mapped[Any] = mapped_column(
            OneTimeCode(backend=otp_hasher, ttl_seconds=600, max_attempts=3),
        )


    raw_code = generate_one_time_code()
    otp = HashedOneTimeCode(otp_hasher.hash(raw_code), otp_hasher, max_attempts=3)
    ok, otp = otp.redeem(raw_code)
    assert ok is True and otp.is_used is True

StoredObject and FileObject
---------------------------

:class:`~advanced_alchemy.types.StoredObject` persists :class:`~advanced_alchemy.types.FileObject` metadata in JSONB while delegating object storage I/O and lifecycle cleanup to a named backend registered in :data:`~advanced_alchemy.types.storages`:

.. code-block:: python

    from pathlib import Path
    import tempfile
    from typing import Optional
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDBase
    from advanced_alchemy.types import FileObject, FileObjectList, StoredObject, storages

    tmp_storage = tempfile.mkdtemp()
    storages.register_backend(f"file://{Path(tmp_storage)}", key="documents")


    class DocumentRecord(UUIDBase):
        __tablename__ = "document_record"

        attachment: Mapped[Optional[FileObject]] = mapped_column(
            StoredObject(backend="documents"),
            nullable=True,
        )
        images: Mapped[Optional[FileObjectList]] = mapped_column(
            StoredObject(backend="documents", multiple=True),
            nullable=True,
        )


    file_obj = FileObject(
        backend="documents",
        filename="report.txt",
        metadata={"category": "report"},
    )
    file_obj.update_metadata({"priority": "high"})
    storages.clear_backends()

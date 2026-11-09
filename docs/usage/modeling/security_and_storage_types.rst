================================
Security and File Storage Types
================================

Most apps eventually need to store sensitive values—API keys, user passwords, two-factor login codes—or attach uploaded files like avatars and PDF reports to a database row.

Advanced Alchemy provides dedicated column types so sensitive values are never stored in plain text and uploaded files stay in sync with your database transactions.

Encrypted Text and Password Hashing
-----------------------------------

Use ``EncryptedString`` or ``EncryptedText`` when your app needs to decrypt a secret later (like an API token), and ``PasswordHash`` when storing one-way user passwords:

.. tab-set::

    .. tab-item:: Encrypted Columns

        .. code-block:: python

            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import BigIntBase
            from advanced_alchemy.types import EncryptedString, EncryptedText


            class SecretRecord(BigIntBase):
                __tablename__ = "secret_record"

                api_token: Mapped[str] = mapped_column(EncryptedString(key="my-secret-key"))
                private_notes: Mapped[str] = mapped_column(EncryptedText(key="my-secret-key"))

    .. tab-item:: Password Hashing

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
            verified, _ = stored.verify_and_update("s3cret-passphrase")
            assert verified is True

Two-Factor Secrets and One-Time Codes
-------------------------------------

For multi-factor login flows, ``TOTPSecret`` encrypts authenticator app seeds (Google Authenticator, 1Password), while ``OneTimeCode`` hashes short-lived email or SMS verification codes and tracks retry limits:

.. tab-set::

    .. tab-item:: Authenticator App (TOTP)

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

    .. tab-item:: Email / SMS One-Time Code

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

File and Object Storage
-----------------------

Instead of storing large binary blobs inside SQL tables, ``StoredObject`` saves lightweight file metadata in your table and writes the file bytes to local disk, S3, Google Cloud Storage, or Azure via ``storages``:

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


    file_obj = FileObject(backend="documents", filename="report.txt", metadata={"category": "report"})
    file_obj.update_metadata({"priority": "high"})
    storages.clear_backends()

See :doc:`/usage/frameworks/litestar_storage` and :doc:`/usage/frameworks/fastapi_storage` for complete file-upload web examples.

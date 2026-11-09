"""Litestar extension lazy re-exports for ``advanced_alchemy.types``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.types import (
        DEFAULT_ENCRYPTION_KEY_ENV,
        GUID,
        NANOID_INSTALLED,
        ORA_JSONB,
        UUID_UTILS_INSTALLED,
        BigIntIdentity,
        Bool,
        DateTimeUTC,
        EncryptedString,
        EncryptedText,
        EncryptionBackend,
        FernetBackend,
        FileObject,
        FileObjectList,
        HashedOneTimeCode,
        HashedPassword,
        JsonB,
        MutableList,
        OneTimeCode,
        PasswordHash,
        PGCryptoBackend,
        StorageBackend,
        StorageBackendT,
        StorageRegistry,
        StoredObject,
        TOTPProvider,
        TOTPSecret,
        Vector,
        encrypted_string,
        file_object,
        generate_one_time_code,
        generate_totp_secret,
        get_default_encryption_key,
        password_hash,
        set_default_encryption_key,
        storages,
        totp,
    )

__all__ = (
    "DEFAULT_ENCRYPTION_KEY_ENV",
    "GUID",
    "NANOID_INSTALLED",
    "ORA_JSONB",
    "UUID_UTILS_INSTALLED",
    "BigIntIdentity",
    "Bool",
    "DateTimeUTC",
    "EncryptedString",
    "EncryptedText",
    "EncryptionBackend",
    "FernetBackend",
    "FileObject",
    "FileObjectList",
    "HashedOneTimeCode",
    "HashedPassword",
    "JsonB",
    "MutableList",
    "OneTimeCode",
    "PGCryptoBackend",
    "PasswordHash",
    "StorageBackend",
    "StorageBackendT",
    "StorageRegistry",
    "StoredObject",
    "TOTPProvider",
    "TOTPSecret",
    "Vector",
    "encrypted_string",
    "file_object",
    "generate_one_time_code",
    "generate_totp_secret",
    "get_default_encryption_key",
    "password_hash",
    "set_default_encryption_key",
    "storages",
    "totp",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.types``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.types")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))

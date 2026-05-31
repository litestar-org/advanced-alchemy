"""SQLAlchemy custom types for use with the ORM."""

from advanced_alchemy.types import encrypted_string, file_object, password_hash, totp
from advanced_alchemy.types.boolean import Bool
from advanced_alchemy.types.datetime import DateTimeUTC
from advanced_alchemy.types.encrypted_string import (
    EncryptedString,
    EncryptedText,
    EncryptionBackend,
    FernetBackend,
)
from advanced_alchemy.types.file_object import (
    FileObject,
    FileObjectList,
    StorageBackend,
    StorageBackendT,
    StorageRegistry,
    StoredObject,
    storages,
)
from advanced_alchemy.types.guid import GUID, NANOID_INSTALLED, UUID_UTILS_INSTALLED
from advanced_alchemy.types.identity import BigIntIdentity
from advanced_alchemy.types.json import ORA_JSONB, JsonB
from advanced_alchemy.types.mutables import MutableList
from advanced_alchemy.types.password_hash.base import HashedPassword, PasswordHash
from advanced_alchemy.types.password_hash.one_time_code import HashedOneTimeCode, OneTimeCode
from advanced_alchemy.types.totp import TOTPProvider, TOTPSecret, generate_totp_secret
from advanced_alchemy.types.vector import Vector

__all__ = (
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
    "generate_totp_secret",
    "password_hash",
    "storages",
    "totp",
)

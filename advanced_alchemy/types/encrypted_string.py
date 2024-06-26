from __future__ import annotations

import abc
import base64
import contextlib
import os
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy import func as sql_func

cryptography = None
with contextlib.suppress(ImportError):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect


class EncryptionBackend(abc.ABC):
    def mount_vault(self, key: str | bytes) -> None:
        if isinstance(key, str):
            key = key.encode()

    @abc.abstractmethod
    def init_engine(self, key: bytes | str) -> None:  # pragma: nocover
        pass

    @abc.abstractmethod
    def encrypt(self, value: Any) -> str:  # pragma: nocover
        pass

    @abc.abstractmethod
    def decrypt(self, value: Any) -> str:  # pragma: nocover
        pass


class PGCryptoBackend(EncryptionBackend):
    """PG Crypto backend."""

    def init_engine(self, key: bytes | str) -> None:
        if isinstance(key, str):
            key = key.encode()
        self.passphrase = base64.urlsafe_b64encode(key)

    def encrypt(self, value: Any) -> str:
        if not isinstance(value, str):  # pragma: nocover
            value = repr(value)
        value = value.encode()
        return sql_func.pgp_sym_encrypt(value, self.passphrase)  # type: ignore[return-value]

    def decrypt(self, value: Any) -> str:
        if not isinstance(value, str):  # pragma: nocover
            value = str(value)
        return sql_func.pgp_sym_decrypt(value, self.passphrase)  # type: ignore[return-value]


class FernetBackend(EncryptionBackend):
    """Encryption Using a Fernet backend"""

    def mount_vault(self, key: str | bytes) -> None:
        if isinstance(key, str):
            key = key.encode()
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())  # pyright: ignore[reportPossiblyUnboundVariable]
        digest.update(key)
        engine_key = digest.finalize()
        self.init_engine(engine_key)

    def init_engine(self, key: bytes | str) -> None:
        if isinstance(key, str):
            key = key.encode()
        self.key = base64.urlsafe_b64encode(key)
        self.fernet = Fernet(self.key)  # pyright: ignore[reportPossiblyUnboundVariable]

    def encrypt(self, value: Any) -> str:
        if not isinstance(value, str):
            value = repr(value)
        value = value.encode()
        encrypted = self.fernet.encrypt(value)
        return encrypted.decode("utf-8")

    def decrypt(self, value: Any) -> str:
        if not isinstance(value, str):  # pragma: nocover
            value = str(value)
        decrypted: str | bytes = self.fernet.decrypt(value.encode())
        if not isinstance(decrypted, str):
            decrypted = decrypted.decode("utf-8")
        return decrypted


class EncryptedString(TypeDecorator[str]):
    """Used to store encrypted values in a database"""

    impl = String
    cache_ok = True

    def __init__(
        self,
        key: str | bytes | Callable[[], str | bytes] = os.urandom(32),
        backend: type[EncryptionBackend] = FernetBackend,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.key = key
        self.backend = backend()

    @property
    def python_type(self) -> type[str]:
        return str

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name in {"mysql", "mariadb"}:
            return dialect.type_descriptor(Text())
        if dialect.name == "oracle":
            return dialect.type_descriptor(String(length=4000))
        return dialect.type_descriptor(String())

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return value
        self.mount_vault()
        return self.backend.encrypt(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return value
        self.mount_vault()
        return self.backend.decrypt(value)

    def mount_vault(self) -> None:
        key = self.key() if callable(self.key) else self.key
        self.backend.mount_vault(key)


class EncryptedText(EncryptedString):
    """Encrypted Clob"""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        return dialect.type_descriptor(Text())

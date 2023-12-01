from __future__ import annotations

import abc
import base64
import contextlib
from typing import TYPE_CHECKING, Any

from sqlalchemy import String, TypeDecorator, type_coerce
from sqlalchemy import func as sql_func

cryptography = None
with contextlib.suppress(ImportError):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect


class EncryptionBackend(abc.ABC):
    def mount(self, key: str | bytes) -> None:
        if isinstance(key, str):
            key = key.encode()

    @abc.abstractmethod
    def init_engine(self, passphrase: bytes | str) -> None:  # pragma: nocover
        pass

    @abc.abstractmethod
    def encrypt(self, value: Any) -> str:  # pragma: nocover
        pass

    @abc.abstractmethod
    def decrypt(self, value: Any) -> str:  # pragma: nocover
        pass


class PGCryptoBackend(EncryptionBackend):
    """PG Crypto backend."""

    def init_engine(self, passphrase: bytes | str) -> None:
        if isinstance(passphrase, str):
            passphrase = passphrase.encode()
        self.passphrase = base64.urlsafe_b64encode(passphrase)

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

    def mount(self, key: str | bytes) -> None:
        if isinstance(key, str):
            key = key.encode()
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(key)
        engine_key = digest.finalize()
        self.init_engine(engine_key)

    def init_engine(self, passphrase: bytes | str) -> None:
        if isinstance(passphrase, str):
            passphrase = passphrase.encode()
        self.passphrase = base64.urlsafe_b64encode(passphrase)
        self.fernet = Fernet(self.passphrase)

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


class EncryptedString(TypeDecorator):
    """Used to store encrypted values in a database"""

    impl = String

    cache_ok = True

    def __init__(
        self,
        passphrase: str | bytes,
        backend: type[EncryptionBackend] = FernetBackend,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.passphrase = passphrase
        self.backend = backend()

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        return dialect.type_descriptor(String())

    def bind_expression(self, bindparam: Any) -> Any:
        # convert the bind's type from EncryptedString to
        # String, so that it's passed as is without
        # a dbapi.Binary wrapper
        bindparam = type_coerce(bindparam, String)
        return self._handle_encrypted_data(bindparam)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return value
        self.backend.mount(self.passphrase)
        return self.backend.encrypt(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return value
        self.backend.mount(self.passphrase)
        return self.backend.decrypt(value)

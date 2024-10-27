from __future__ import annotations

import abc
import base64
import contextlib
import os
from typing import TYPE_CHECKING, Any, Callable

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy import func as sql_func

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

cryptography = None  # type: ignore[var-annotated,unused-ignore]
with contextlib.suppress(ImportError):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes


__all__ = ("EncryptedString", "EncryptedText", "EncryptionBackend", "FernetBackend", "PGCryptoBackend")


class EncryptionBackend(abc.ABC):
    """Abstract base class for encryption backends.

    This class defines the interface that all encryption backends must implement.
    Concrete implementations should provide the actual encryption/decryption logic.

    Attributes:
        passphrase (bytes): The encryption passphrase used by the backend.
    """

    def mount_vault(self, key: str | bytes) -> None:
        """Mounts the vault with the provided encryption key.

        Args:
            key (str | bytes): The encryption key used to initialize the backend.
        """
        if isinstance(key, str):
            key = key.encode()

    @abc.abstractmethod
    def init_engine(self, key: bytes | str) -> None:  # pragma: nocover
        """Initializes the encryption engine with the provided key.

        Args:
            key (bytes | str): The encryption key.

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
        """

    @abc.abstractmethod
    def encrypt(self, value: Any) -> str:  # pragma: nocover
        """Encrypts the given value.

        Args:
            value (Any): The value to encrypt.

        Returns:
            str: The encrypted value.

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
        """

    @abc.abstractmethod
    def decrypt(self, value: Any) -> str:  # pragma: nocover
        """Decrypts the given value.

        Args:
            value (Any): The value to decrypt.

        Returns:
            str: The decrypted value.

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
        """


class PGCryptoBackend(EncryptionBackend):
    """PostgreSQL pgcrypto-based encryption backend.

    This backend uses PostgreSQL's pgcrypto extension for encryption/decryption operations.
    Requires the pgcrypto extension to be installed in the database.

    Attributes:
        passphrase (bytes): The base64-encoded passphrase used for encryption and decryption.
    """

    def init_engine(self, key: bytes | str) -> None:
        """Initializes the pgcrypto engine with the provided key.

        Args:
            key (bytes | str): The encryption key.
        """
        if isinstance(key, str):
            key = key.encode()
        self.passphrase = base64.urlsafe_b64encode(key)

    def encrypt(self, value: Any) -> str:
        """Encrypts the given value using pgcrypto.

        Args:
            value (Any): The value to encrypt.

        Returns:
            str: The encrypted value.

        Raises:
            TypeError: If the value is not a string.
        """
        if not isinstance(value, str):  # pragma: nocover
            value = repr(value)
        value = value.encode()
        return sql_func.pgp_sym_encrypt(value, self.passphrase)  # type: ignore[return-value]

    def decrypt(self, value: Any) -> str:
        """Decrypts the given value using pgcrypto.

        Args:
            value (Any): The value to decrypt.

        Returns:
            str: The decrypted value.

        Raises:
            TypeError: If the value is not a string.
        """
        if not isinstance(value, str):  # pragma: nocover
            value = str(value)
        return sql_func.pgp_sym_decrypt(value, self.passphrase)  # type: ignore[return-value]


class FernetBackend(EncryptionBackend):
    """Fernet-based encryption backend.

    This backend uses the Python cryptography library's Fernet implementation
    for encryption/decryption operations. Provides symmetric encryption with
    built-in rotation support.

    Attributes:
        key (bytes): The base64-encoded key used for encryption and decryption.
        fernet (cryptography.fernet.Fernet): The Fernet instance used for encryption/decryption.
    """

    def mount_vault(self, key: str | bytes) -> None:
        """Mounts the vault with the provided encryption key.

        This method hashes the key using SHA256 before initializing the engine.

        Args:
            key (str | bytes): The encryption key.
        """
        if isinstance(key, str):
            key = key.encode()
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())  # pyright: ignore[reportPossiblyUnboundVariable]
        digest.update(key)
        engine_key = digest.finalize()
        self.init_engine(engine_key)

    def init_engine(self, key: bytes | str) -> None:
        """Initializes the Fernet engine with the provided key.

        Args:
            key (bytes | str): The encryption key.
        """
        if isinstance(key, str):
            key = key.encode()
        self.key = base64.urlsafe_b64encode(key)
        self.fernet = Fernet(self.key)  # pyright: ignore[reportPossiblyUnboundVariable]

    def encrypt(self, value: Any) -> str:
        """Encrypts the given value using Fernet.

        Args:
            value (Any): The value to encrypt.

        Returns:
            str: The encrypted value.

        Raises:
            TypeError: If the value is not a string.
            cryptography.fernet.InvalidToken: If encryption fails.
        """
        if not isinstance(value, str):
            value = repr(value)
        value = value.encode()
        encrypted = self.fernet.encrypt(value)
        return encrypted.decode("utf-8")

    def decrypt(self, value: Any) -> str:
        """Decrypts the given value using Fernet.

        Args:
            value (Any): The value to decrypt.

        Returns:
            str: The decrypted value.

        Raises:
            TypeError: If the value is not a string.
            cryptography.fernet.InvalidToken: If decryption fails.
        """
        if not isinstance(value, str):  # pragma: nocover
            value = str(value)
        decrypted: str | bytes = self.fernet.decrypt(value.encode())
        if not isinstance(decrypted, str):
            decrypted = decrypted.decode("utf-8")  # pyright: ignore[reportAttributeAccessIssue]
        return decrypted


class EncryptedString(TypeDecorator[str]):
    """SQLAlchemy TypeDecorator for storing encrypted string values in a database.

    This type provides transparent encryption/decryption of string values using the specified backend.
    It extends :class:`sqlalchemy.types.TypeDecorator` and implements String as its underlying type.

    Args:
        key (str | bytes | Callable[[], str | bytes] | None): The encryption key. Can be a string, bytes, or callable returning either. Defaults to os.urandom(32).
        backend (Type[EncryptionBackend] | None): The encryption backend class to use. Defaults to FernetBackend.
        **kwargs (Any | None): Additional arguments passed to the underlying String type.

    Attributes:
        key (str | bytes | Callable[[], str | bytes]): The encryption key.
        backend (EncryptionBackend): The encryption backend instance.
    """

    impl = String
    cache_ok = True

    def __init__(
        self,
        key: str | bytes | Callable[[], str | bytes] = os.urandom(32),
        backend: type[EncryptionBackend] = FernetBackend,
        **kwargs: Any,
    ) -> None:
        """Initializes the EncryptedString TypeDecorator.

        Args:
            key (str | bytes | Callable[[], str | bytes] | None): The encryption key. Can be a string, bytes, or callable returning either. Defaults to os.urandom(32).
            backend (Type[EncryptionBackend] | None): The encryption backend class to use. Defaults to FernetBackend.
            **kwargs (Any | None): Additional arguments passed to the underlying String type.
        """
        super().__init__()
        self.key = key
        self.backend = backend()

    @property
    def python_type(self) -> type[str]:
        """Returns the Python type for this type decorator.

        Returns:
            Type[str]: The Python string type.
        """
        return str

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        """Loads the appropriate dialect implementation based on the database dialect.

        Args:
            dialect (Dialect): The SQLAlchemy dialect.

        Returns:
            Any: The dialect-specific type descriptor.
        """
        if dialect.name in {"mysql", "mariadb"}:
            return dialect.type_descriptor(Text())
        if dialect.name == "oracle":
            return dialect.type_descriptor(String(length=4000))
        return dialect.type_descriptor(String())

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Processes the value before binding it to the SQL statement.

        This method encrypts the value using the specified backend.

        Args:
            value (Any): The value to process.
            dialect (Dialect): The SQLAlchemy dialect.

        Returns:
            str | None: The encrypted value or None if the input is None.
        """
        if value is None:
            return value
        self.mount_vault()
        return self.backend.encrypt(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        """Processes the value after retrieving it from the database.

        This method decrypts the value using the specified backend.

        Args:
            value (Any): The value to process.
            dialect (Dialect): The SQLAlchemy dialect.

        Returns:
            str | None: The decrypted value or None if the input is None.
        """
        if value is None:
            return value
        self.mount_vault()
        return self.backend.decrypt(value)

    def mount_vault(self) -> None:
        """Mounts the vault with the encryption key.

        If the key is callable, it is called to retrieve the key. Otherwise, the key is used directly.
        """
        key = self.key() if callable(self.key) else self.key
        self.backend.mount_vault(key)


class EncryptedText(EncryptedString):
    """SQLAlchemy TypeDecorator for storing encrypted text/CLOB values in a database.

    This type provides transparent encryption/decryption of text values using the specified backend.
    It extends :class:`EncryptedString` and implements Text as its underlying type.
    This is suitable for storing larger encrypted text content compared to EncryptedString.

    Args:
        key (str | bytes | Callable[[], str | bytes] | None): The encryption key. Can be a string, bytes, or callable returning either. Defaults to os.urandom(32).
        backend (Type[EncryptionBackend] | None): The encryption backend class to use. Defaults to FernetBackend.
        **kwargs (Any | None): Additional arguments passed to the underlying String type.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        """Loads the appropriate dialect implementation for Text type.

        Args:
            dialect (Dialect): The SQLAlchemy dialect.

        Returns:
            Any: The dialect-specific Text type descriptor.
        """
        return dialect.type_descriptor(Text())

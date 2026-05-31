import abc
import base64
import os
from typing import TYPE_CHECKING, Any, Callable, Optional, Union

from sqlalchemy import String, Text, TypeDecorator
from sqlalchemy import func as sql_func

from advanced_alchemy.exceptions import IntegrityError, MissingDependencyError
from advanced_alchemy.typing import CRYPTOGRAPHY_INSTALLED
from advanced_alchemy.utils.deprecation import warn_deprecation

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect


__all__ = ("EncryptedString", "EncryptedText", "EncryptionBackend", "FernetBackend", "PGCryptoBackend")


class EncryptionBackend(abc.ABC):
    """Abstract base class for encryption backends.

    This class defines the interface that all encryption backends must implement.
    Concrete implementations should provide the actual encryption/decryption logic.

    Attributes:
        passphrase (bytes): The encryption passphrase used by the backend.
    """

    def mount_vault(self, key: "Union[str, bytes]") -> None:
        """Mounts the vault with the provided encryption key.

        Args:
            key (str | bytes): The encryption key used to initialize the backend.
        """
        if isinstance(key, str):
            key = key.encode()
        self.init_engine(key)

    @abc.abstractmethod
    def init_engine(self, key: "Union[bytes, str]") -> None:  # pragma: no cover
        """Initializes the encryption engine with the provided key.

        Args:
            key (bytes | str): The encryption key.

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
        """

    @abc.abstractmethod
    def encrypt(self, value: Any) -> str:  # pragma: no cover
        """Encrypts the given value.

        Args:
            value (Any): The value to encrypt.

        Returns:
            str: The encrypted value.

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
        """

    @abc.abstractmethod
    def decrypt(self, value: Any) -> str:  # pragma: no cover
        """Decrypts the given value.

        Args:
            value (Any): The value to decrypt.

        Returns:
            str: The decrypted value.

        Raises:
            NotImplementedError: If the method is not implemented by the subclass.
        """

    def bind_expression(self, bindvalue: Any) -> "Optional[Any]":
        """Returns a SQL expression that encrypts the bound parameter server-side.

        Client-side backends (which encrypt in :meth:`encrypt`) return ``None`` so the
        bound value is stored verbatim. Server-side backends override this to wrap the
        bind parameter in a database encryption function.

        Args:
            bindvalue (Any): The bound parameter element.

        Returns:
            Any | None: The wrapped SQL expression, or ``None`` for client-side backends.
        """
        return None

    def column_expression(self, column: Any) -> "Optional[Any]":
        """Returns a SQL expression that decrypts the column server-side.

        Client-side backends (which decrypt in :meth:`decrypt`) return ``None`` so the
        stored value is read verbatim. Server-side backends override this to wrap the
        column in a database decryption function.

        Args:
            column (Any): The column element being read.

        Returns:
            Any | None: The wrapped SQL expression, or ``None`` for client-side backends.
        """
        return None


class PGCryptoBackend(EncryptionBackend):
    """PostgreSQL pgcrypto-based encryption backend.

    This backend uses PostgreSQL's pgcrypto extension for encryption/decryption operations.
    Requires the pgcrypto extension to be installed in the database. Encryption and
    decryption run server-side via :meth:`bind_expression` and :meth:`column_expression`;
    the ASCII-armored ciphertext is stored as text so the column type is unchanged.

    Attributes:
        passphrase (str): The base64-encoded passphrase used for encryption and decryption.
    """

    def init_engine(self, key: "Union[bytes, str]") -> None:
        """Initializes the pgcrypto engine with the provided key.

        Args:
            key (bytes | str): The encryption key.
        """
        if isinstance(key, str):
            key = key.encode()
        self.passphrase = base64.urlsafe_b64encode(key).decode("ascii")

    def encrypt(self, value: Any) -> str:
        """Returns the plaintext value to bind; encryption happens server-side.

        Args:
            value (Any): The value to encrypt.

        Returns:
            str: The plaintext value passed to :meth:`bind_expression`.
        """
        if not isinstance(value, str):  # pragma: no cover
            return repr(value)
        return value

    def decrypt(self, value: Any) -> str:
        """Normalizes the server-decrypted value; decryption happens in SQL.

        Args:
            value (Any): The value already decrypted by :meth:`column_expression`.

        Returns:
            str: The decrypted value.
        """
        if isinstance(value, bytes):  # pragma: no cover
            return value.decode("utf-8")
        if not isinstance(value, str):  # pragma: no cover
            return str(value)
        return value

    def bind_expression(self, bindvalue: Any) -> "Optional[Any]":
        """Wraps the bound parameter in ``armor(pgp_sym_encrypt(...))``.

        Args:
            bindvalue (Any): The bound parameter element.

        Returns:
            Any: The SQL expression producing ASCII-armored ciphertext.
        """
        return sql_func.armor(sql_func.pgp_sym_encrypt(bindvalue, self.passphrase))

    def column_expression(self, column: Any) -> "Optional[Any]":
        """Wraps the column in ``pgp_sym_decrypt(dearmor(...))``.

        Args:
            column (Any): The column element being read.

        Returns:
            Any: The SQL expression producing the decrypted plaintext.
        """
        return sql_func.pgp_sym_decrypt(sql_func.dearmor(column), self.passphrase)


class FernetBackend(EncryptionBackend):
    """Fernet-based encryption backend.

    This backend uses the Python cryptography library's Fernet implementation
    for encryption/decryption operations. Provides authenticated symmetric
    encryption (AES-128-CBC + HMAC-SHA256). The key is derived from the
    provided passphrase with a single SHA256 digest.

    Attributes:
        key (bytes): The base64-encoded key used for encryption and decryption.
        fernet (cryptography.fernet.Fernet): The Fernet instance used for encryption/decryption.
    """

    def __init__(self) -> None:
        """Initializes the Fernet backend.

        Raises:
            MissingDependencyError: If the ``cryptography`` package is not installed.
        """
        if not CRYPTOGRAPHY_INSTALLED:
            raise MissingDependencyError(package="cryptography")

    def mount_vault(self, key: "Union[str, bytes]") -> None:
        """Mounts the vault with the provided encryption key.

        This method hashes the key using SHA256 before initializing the engine.

        Args:
            key (str | bytes): The encryption key.
        """
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes

        if isinstance(key, str):
            key = key.encode()
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(key)
        engine_key = digest.finalize()
        self.init_engine(engine_key)

    def init_engine(self, key: "Union[bytes, str]") -> None:
        """Initializes the Fernet engine with the provided key.

        Args:
            key (bytes | str): The encryption key.
        """
        from cryptography.fernet import Fernet

        if isinstance(key, str):
            key = key.encode()
        self.key = base64.urlsafe_b64encode(key)
        self.fernet = Fernet(self.key)

    def encrypt(self, value: Any) -> str:
        """Encrypts the given value using Fernet.

        Args:
            value (Any): The value to encrypt.

        Returns:
            str: The encrypted value.
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
        """
        if not isinstance(value, str):  # pragma: no cover
            value = str(value)
        decrypted: Union[str, bytes] = self.fernet.decrypt(value.encode())
        if not isinstance(decrypted, str):
            decrypted = decrypted.decode("utf-8")  # pyright: ignore[reportAttributeAccessIssue]
        return decrypted


DEFAULT_ENCRYPTION_KEY = os.urandom(32)


class EncryptedString(TypeDecorator[str]):
    """SQLAlchemy TypeDecorator for storing encrypted string values in a database.

    This type provides transparent encryption/decryption of string values using the specified backend.
    It extends :class:`sqlalchemy.types.TypeDecorator` and implements String as its underlying type.

    Args:
        key (str | bytes | Callable[[], str | bytes] | None): The encryption key. Can be a string, bytes, or callable returning either. Defaults to os.urandom(32).
        backend (Type[EncryptionBackend] | None): The encryption backend class to use. Defaults to FernetBackend.
        length (int | None): The length of the unencrypted string. This is used for documentation and validation purposes only, as encrypted strings will be longer.
        **kwargs (Any | None): Additional arguments passed to the underlying String type.

    Attributes:
        key (str | bytes | Callable[[], str | bytes]): The encryption key.
        backend (EncryptionBackend): The encryption backend instance.
        length (int | None): The unencrypted string length.
    """

    impl = String
    cache_ok = True

    def __init__(
        self,
        key: "Union[str, bytes, Callable[[], Union[str, bytes]]]" = DEFAULT_ENCRYPTION_KEY,
        backend: "type[EncryptionBackend]" = FernetBackend,
        length: "Optional[int]" = None,
        **kwargs: Any,
    ) -> None:
        """Initializes the EncryptedString TypeDecorator.

        Args:
            key (str | bytes | Callable[[], str | bytes] | None): The encryption key. Can be a string, bytes, or callable returning either. Defaults to os.urandom(32).
            backend (Type[EncryptionBackend] | None): The encryption backend class to use. Defaults to FernetBackend.
            length (int | None): The length of the unencrypted string. This is used for documentation and validation purposes only.
            **kwargs (Any | None): Additional arguments passed to the underlying String type.
        """
        super().__init__()
        if key is DEFAULT_ENCRYPTION_KEY:
            warn_deprecation(
                version="1.11.0",
                deprecated_name="EncryptedString(key=<default>)",
                kind="parameter",
                removal_in="2.0.0",
                alternative="an explicit key (str/bytes) or a callable returning one",
                info="The random default key changes on every process restart, making previously written rows undecryptable. Provide a stable key.",
            )
        self.key = key
        self.backend = backend()
        self.length = length
        self._vault_mounted = False

    def __repr__(self) -> str:
        """Return a reconstructable representation of the type.

        Uses ``type(self).__name__`` so subclasses (e.g. :class:`EncryptedText`) render their
        own name; this keeps Alembic autogenerate from reconstructing the wrong column type.
        """
        key_repr = self.key.__name__ if callable(self.key) else repr(self.key)
        return f"{type(self).__name__}(key={key_repr}, backend={self.backend.__class__.__name__}, length={self.length})"

    @property
    def python_type(self) -> type[str]:
        """Returns the Python type for this type decorator.

        Returns:
            Type[str]: The Python string type.
        """
        return str

    def load_dialect_impl(self, dialect: "Dialect") -> Any:
        """Loads the appropriate dialect implementation based on the database dialect.

        Note: The actual column length will be larger than the specified length due to encryption overhead.
        For most encryption methods, the encrypted string will be approximately 1.35x longer than the original.

        Args:
            dialect (Dialect): The SQLAlchemy dialect.

        Returns:
            Any: The dialect-specific type descriptor.
        """
        if dialect.name in {"mysql", "mariadb"}:
            # For MySQL/MariaDB, always use Text to avoid length limitations
            return dialect.type_descriptor(Text())
        if dialect.name == "oracle":
            # Oracle has a 4000-byte limit for VARCHAR2 (by default)
            return dialect.type_descriptor(String(length=4000))
        return dialect.type_descriptor(String())

    def process_bind_param(self, value: Any, dialect: "Dialect") -> "Union[str, None]":
        """Processes the value before binding it to the SQL statement.

        This method encrypts the value using the specified backend and validates length if specified.

        Args:
            value (Any): The value to process.
            dialect (Dialect): The SQLAlchemy dialect.

        Raises:
            IntegrityError: If the unencrypted value exceeds the maximum length.

        Returns:
            str | None: The encrypted value or None if the input is None.
        """
        if value is None:
            return value

        # Validate length if specified
        if self.length is not None and len(str(value)) > self.length:
            msg = f"Unencrypted value exceeds maximum unencrypted length of {self.length}"
            raise IntegrityError(msg)

        self.mount_vault()
        return self.backend.encrypt(value)

    def process_result_value(self, value: Any, dialect: "Dialect") -> "Union[str, None]":
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

        For a static key the cipher is derived once and reused. For a callable
        key it is re-resolved on every call so rotated keys take effect.
        """
        if self._vault_mounted and not callable(self.key):
            return
        key = self.key() if callable(self.key) else self.key
        self.backend.mount_vault(key)
        self._vault_mounted = True

    def bind_expression(self, bindparam: Any) -> "Optional[Any]":
        """Wraps the bound parameter with the backend's server-side encryption, if any.

        For client-side backends the parameter is returned unchanged so it compiles to a
        plain placeholder; server-side backends wrap it in a database encryption function.

        Args:
            bindparam (Any): The bound parameter element.

        Returns:
            Any: The wrapped SQL expression for server-side backends, otherwise the bound parameter.
        """
        self.mount_vault()
        wrapped = self.backend.bind_expression(bindparam)
        return wrapped if wrapped is not None else bindparam

    def column_expression(self, column: Any) -> "Optional[Any]":
        """Wraps the column read with the backend's server-side decryption, if any.

        For client-side backends the column is returned unchanged; server-side backends
        wrap it in a database decryption function.

        Args:
            column (Any): The column element being read.

        Returns:
            Any: The wrapped SQL expression for server-side backends, otherwise the column.
        """
        self.mount_vault()
        wrapped = self.backend.column_expression(column)
        return wrapped if wrapped is not None else column


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

    def load_dialect_impl(self, dialect: "Dialect") -> Any:
        """Loads the appropriate dialect implementation for Text type.

        Args:
            dialect (Dialect): The SQLAlchemy dialect.

        Returns:
            Any: The dialect-specific Text type descriptor.
        """
        return dialect.type_descriptor(Text())

"""Bcrypt Hashing Backend."""

from typing import TYPE_CHECKING, Any, Union

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.password_hash.base import HashingBackend
from advanced_alchemy.typing import BCRYPT_INSTALLED

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement

__all__ = ("BcryptHasher",)


class BcryptHasher(HashingBackend):
    """Hashing backend using bcrypt via the python bcrypt library
    written in rust.
    """

    def __init__(self, rounds: int = 12, prefix: bytes = b"2b") -> None:
        """Initialize BcryptBackend
        Args:
            rounds: number of rounds to utilize with each
                generated salt.
            prefix: the prefix to use for each salt being
                generated.
        """
        if not BCRYPT_INSTALLED:
            raise MissingDependencyError(package="bcrypt", install_package="bcrypt")
        import bcrypt

        self.__gensalt = bcrypt.gensalt
        self.__hashpw = bcrypt.hashpw
        self.__checkpw = bcrypt.checkpw

        self._rounds = rounds
        self._prefix = prefix

    def _gensalt(self) -> bytes:
        return self.__gensalt(self._rounds, self._prefix)

    def hash(self, value: Union[str, bytes]) -> str:
        """Hash the password using Bcrypt.

        Args:
            value: the plain text password (will be encoded to UTF-8 if string)

        Returns:
            The Bcrypt hash string.
        """
        return self.__hashpw(self._ensure_bytes(value), self._gensalt()).decode("utf-8")

    def verify(self, plain: Union[str, bytes], hashed: str) -> bool:
        """Verify a plain text value against a hash using the bcrypt checkpw function.

        Args:
            plain: The plain text value to verify. Will be converted to string.
            hashed: The hash to verify against.

        Returns:
            True if the plain text matches the hash, False otherwise.
        """
        try:
            return self.__checkpw(self._ensure_bytes(plain), self._ensure_bytes(hashed))
        except Exception:  # noqa: BLE001
            return False

    def needs_rehash(self, hashed: str) -> bool:
        """Return True if the stored hash uses an outdated scheme or cost.

        Args:
            hashed: The stored hash string.

        Returns:
            True if the hash should be regenerated; False for an unparsable or foreign hash.
        """
        return False

    def compare_expression(self, column: "ColumnElement[str]", plain: Any) -> "BinaryExpression[bool]":
        """Direct SQL comparison is not supported for Pwdlib.

        Raises:
            NotImplementedError: Always raised.
        """
        msg = "BcryptHasher does not support direct SQL comparison."
        raise NotImplementedError(msg)

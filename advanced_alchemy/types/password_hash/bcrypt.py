"""Bcrypt Hashing Backend."""

from typing import TYPE_CHECKING, Any, Union

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.password_hash.base import HashingBackend
from advanced_alchemy.typing import BCRYPT_INSTALLED

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement

__all__ = ("BcryptHasher",)

_VALID_BCRYPT_PREFIXES = frozenset({"2", "2a", "2b", "2x", "2y"})
_BCRYPT_HASH_PARTS = 4


class BcryptHasher(HashingBackend):
    """Hashing backend using bcrypt via the python bcrypt library."""

    def __init__(self, rounds: int = 12, prefix: bytes = b"2b") -> None:
        """Initialize BcryptHasher.

        Args:
            rounds: Number of rounds (cost factor) to utilize with each generated salt.
            prefix: The prefix to use for each salt being generated.

        Raises:
            MissingDependencyError: If the ``bcrypt`` package is not installed.
        """
        if not BCRYPT_INSTALLED:
            raise MissingDependencyError(package="bcrypt", install_package="bcrypt")
        import bcrypt

        self.__gensalt = bcrypt.gensalt
        self.__hashpw = bcrypt.hashpw
        self.__checkpw = bcrypt.checkpw

        self._rounds = rounds
        self._prefix = prefix

    @property
    def rounds(self) -> int:
        """Configured cost factor (log2 iterations)."""
        return self._rounds

    @property
    def prefix(self) -> bytes:
        """Configured bcrypt version prefix."""
        return self._prefix

    def hash(self, value: Union[str, bytes]) -> str:
        """Hash the password using Bcrypt.

        Args:
            value: The plain text password (will be encoded to UTF-8 if string).

        Returns:
            The Bcrypt hash string.
        """
        return self.__hashpw(self._ensure_bytes(value), self._gensalt()).decode("utf-8")

    def verify(self, plain: Any, hashed: str) -> bool:
        """Verify a plain text value against a hash using the bcrypt checkpw function.

        Args:
            plain: The plain text value to verify. Any non-string or non-bytes type returns ``False``.
            hashed: The hash to verify against.

        Returns:
            True if the plain text matches the hash, False otherwise.
        """
        if not isinstance(plain, (str, bytes)):
            return False
        try:
            return self.__checkpw(self._ensure_bytes(plain), self._ensure_bytes(hashed))
        except Exception:  # noqa: BLE001
            return False

    def needs_rehash(self, hashed: str) -> bool:
        """Return True if the stored hash uses an outdated prefix or cost factor.

        Args:
            hashed: The stored hash string.

        Returns:
            True if the hash should be regenerated; False for an unparsable or foreign hash.
        """
        parts = hashed.split("$")
        if len(parts) != _BCRYPT_HASH_PARTS or parts[0] != "" or parts[1] not in _VALID_BCRYPT_PREFIXES or not parts[3]:
            return False
        try:
            cost = int(parts[2])
        except ValueError:
            return False
        return parts[1].encode("ascii") != self._prefix or cost != self._rounds

    def compare_expression(self, column: "ColumnElement[str]", plain: Any) -> "BinaryExpression[bool]":
        """Direct SQL comparison is not supported for Bcrypt.

        Raises:
            NotImplementedError: Always raised.
        """
        msg = "BcryptHasher does not support direct SQL comparison."
        raise NotImplementedError(msg)

    def _gensalt(self) -> bytes:
        return self.__gensalt(self._rounds, self._prefix)

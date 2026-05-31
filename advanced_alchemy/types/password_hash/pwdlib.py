"""Pwdlib Hashing Backend."""

from typing import TYPE_CHECKING, Any, Union

from advanced_alchemy._typing import PWDLIB_INSTALLED
from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.password_hash.base import HashingBackend

if TYPE_CHECKING:
    from pwdlib.hashers.base import HasherProtocol
    from sqlalchemy import BinaryExpression, ColumnElement

__all__ = ("PwdlibHasher",)


class PwdlibHasher(HashingBackend):
    """Hashing backend using Pwdlib."""

    def __init__(self, hasher: "HasherProtocol") -> None:
        """Initialize PwdlibBackend.

        Args:
            hasher: The Pwdlib hasher to use for hashing and verification.

        Raises:
            MissingDependencyError: If the ``pwdlib`` package is not installed.
        """
        if not PWDLIB_INSTALLED:
            raise MissingDependencyError(package="pwdlib")
        self.hasher = hasher

    def hash(self, value: "Union[str, bytes]") -> str:
        """Hash the given value using the Pwdlib context.

        Args:
            value: The plain text value to hash. Will be converted to string.

        Returns:
            The hashed string.
        """
        return self.hasher.hash(self._ensure_bytes(value))

    def verify(self, plain: "Union[str, bytes]", hashed: str) -> bool:
        """Verify a plain text value against a hash using the Pwdlib context.

        Args:
            plain: The plain text value to verify. Will be converted to string.
            hashed: The hash to verify against.

        Returns:
            True if the plain text matches the hash, False otherwise.
        """
        try:
            return self.hasher.verify(self._ensure_bytes(plain), hashed)
        except Exception:  # noqa: BLE001
            return False

    def needs_rehash(self, hashed: str) -> bool:
        """Return True if the wrapped hasher reports the stored hash as stale.

        Args:
            hashed: The stored hash string.

        Returns:
            True if the hash should be regenerated; False for an unparsable or foreign hash.
        """
        try:
            return self.hasher.check_needs_rehash(hashed)
        except Exception:  # noqa: BLE001
            return False

    def compare_expression(self, column: "ColumnElement[str]", plain: Any) -> "BinaryExpression[bool]":
        """Direct SQL comparison is not supported for Pwdlib.

        Raises:
            NotImplementedError: Always raised.
        """
        msg = "PwdlibHasher does not support direct SQL comparison."
        raise NotImplementedError(msg)

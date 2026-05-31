"""Argon2 Hashing Backend using argon2-cffi."""

from typing import TYPE_CHECKING, Any, Union

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.password_hash.base import HashingBackend

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement

try:
    from argon2 import PasswordHasher as Argon2PasswordHasher
    from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
except ImportError as e:
    raise MissingDependencyError(package="argon2-cffi", install_package="argon2") from e

__all__ = ("Argon2Hasher",)


class Argon2Hasher(HashingBackend):
    """Hashing backend using Argon2 via the argon2-cffi library."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize Argon2Backend.

        Args:
            **kwargs: Optional keyword arguments to pass to the argon2.PasswordHasher constructor.
                      See argon2-cffi documentation for available parameters (e.g., time_cost,
                      memory_cost, parallelism, hash_len, salt_len, type).
        """
        self.hasher = Argon2PasswordHasher(**kwargs)  # pyright: ignore

    def hash(self, value: "Union[str, bytes]") -> str:
        """Hash the password using Argon2.

        Args:
            value: The plain text password (will be encoded to UTF-8 if string).

        Returns:
            The Argon2 hash string.
        """
        return self.hasher.hash(self._ensure_bytes(value))

    def verify(self, plain: Any, hashed: str) -> bool:
        """Verify a plain text password against an Argon2 hash.

        Args:
            plain: The plain text password (will be encoded to UTF-8 if string). Any other
                type returns ``False`` rather than raising.
            hashed: The Argon2 hash string to verify against.

        Returns:
            True if the password matches the hash, False otherwise.
        """
        if not isinstance(plain, (str, bytes)):
            return False
        try:
            self.hasher.verify(hashed, self._ensure_bytes(plain))
        except (VerifyMismatchError, InvalidHash, VerificationError):
            return False
        return True

    def needs_rehash(self, hashed: str) -> bool:
        """Return True if the hash was produced with weaker parameters than the current config.

        Args:
            hashed: The stored Argon2 hash string.

        Returns:
            True if the hash should be regenerated; False for an unparsable or foreign hash.
        """
        try:
            return self.hasher.check_needs_rehash(hashed)
        except Exception:  # noqa: BLE001
            return False

    def compare_expression(self, column: "ColumnElement[str]", plain: "Union[str, bytes]") -> "BinaryExpression[bool]":
        """Direct SQL comparison is not supported for Argon2.

        Raises:
            NotImplementedError: Always raised.
        """
        msg = "Argon2Hasher does not support direct SQL comparison."
        raise NotImplementedError(msg)

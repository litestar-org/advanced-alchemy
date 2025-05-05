"""Argon2 Hashing Backend using argon2-cffi."""

from typing import TYPE_CHECKING, Any, Union

from advanced_alchemy.types.password_hash.base import HashingBackend

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement

from argon2 import PasswordHasher as Argon2PasswordHasher  # pyright: ignore
from argon2.exceptions import InvalidHash, VerifyMismatchError  # pyright: ignore

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

    def verify(self, plain: "Union[str, bytes]", hashed: str) -> bool:
        """Verify a plain text password against an Argon2 hash.

        Args:
            plain: The plain text password (will be encoded to UTF-8 if string).
            hashed: The Argon2 hash string to verify against.

        Returns:
            True if the password matches the hash, False otherwise.
        """
        try:
            self.hasher.verify(hashed, self._ensure_bytes(plain))

        except (VerifyMismatchError, InvalidHash):
            return False
        except Exception:  # noqa: BLE001
            return False
        return True

    def compare_expression(self, column: "ColumnElement[str]", plain: "Union[str, bytes]") -> "BinaryExpression[bool]":
        """Direct SQL comparison is not supported for Argon2.

        Raises:
            NotImplementedError: Always raised.
        """
        msg = "Argon2Hasher does not support direct SQL comparison."
        raise NotImplementedError(msg)

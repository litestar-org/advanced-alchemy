"""Passlib Hashing Backend."""

from typing import TYPE_CHECKING, Any, Union

from passlib.context import CryptContext  # pyright: ignore

from advanced_alchemy.types.password_hash.base import HashingBackend

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement

__all__ = ("PasslibHasher",)


class PasslibHasher(HashingBackend):
    """Hashing backend using Passlib.

    Relies on the `passlib` package being installed.
    Install with `pip install passlib` or `uv pip install passlib`.
    """

    def __init__(self, context: CryptContext) -> None:
        """Initialize PasslibBackend.

        Args:
            context: The Passlib CryptContext to use for hashing and verification.
        """
        self.context = context

    def hash(self, value: "Union[str, bytes]") -> str:
        """Hash the given value using the Passlib context.

        Args:
            value: The plain text value to hash. Will be converted to string.

        Returns:
            The hashed string.
        """
        return self.context.hash(self._ensure_bytes(value))

    def verify(self, plain: "Union[str, bytes]", hashed: str) -> bool:
        """Verify a plain text value against a hash using the Passlib context.

        Args:
            plain: The plain text value to verify. Will be converted to string.
            hashed: The hash to verify against.

        Returns:
            True if the plain text matches the hash, False otherwise.
        """
        try:
            return self.context.verify(self._ensure_bytes(plain), hashed)
        except Exception:  # noqa: BLE001
            # Passlib can raise various errors for invalid hashes
            return False

    def compare_expression(self, column: "ColumnElement[str]", plain: Any) -> "BinaryExpression[bool]":
        """Direct SQL comparison is not supported for Passlib.

        Raises:
            NotImplementedError: Always raised.
        """
        msg = "PasslibHasher does not support direct SQL comparison."
        raise NotImplementedError(msg)

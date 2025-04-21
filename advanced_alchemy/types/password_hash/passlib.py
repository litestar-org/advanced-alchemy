from typing import TYPE_CHECKING, Union

from advanced_alchemy.types.password_hash.base import HashingBackend

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement


if TYPE_CHECKING:
    from passlib.context import CryptContext as CryptContextHint  # pyright: ignore

DEFAULT_SCHEMES = ["argon2"]


class PasslibHasher(HashingBackend):
    """Passlib-based password hashing backend.

    This backend uses the passlib library for hashing and verification.
    Requires the ``passlib`` package to be installed.

    Args:
        context: An optional pre-configured ``passlib.context.CryptContext`` instance.
            If not provided, a default context with ``argon2`` is created.
    """

    def __init__(self, context: "CryptContextHint") -> None:
        """Initialize the PasslibBackend."""

        self.context = context

    def hash(self, value: "Union[str, bytes]") -> str:
        """Hash the given value using the configured passlib context.

        Args:
            value: The plain text value to hash.

        Returns:
            The hashed value as a string.
        """
        return self.context.hash(value)

    def verify(self, plain: "Union[str, bytes]", hashed: str) -> bool:
        """Verify a plain text value against a hash using the configured passlib context.

        Args:
            plain: The plain text value to verify.
            hashed: The hash to verify against.

        Returns:
            True if the plain text matches the hash, False otherwise.
        """
        return self.context.verify(plain, hashed)

    def compare_expression(self, column: "ColumnElement[str]", plain: "Union[str, bytes]") -> "BinaryExpression[bool]":
        """Generate a SQLAlchemy expression for comparing a column with a plain text value.

        This backend does not support DB-side comparison, so it raises NotImplementedError.

        Args:
            column: The SQLAlchemy column to compare.
            plain: The plain text value to compare against.

        Returns:
            A SQLAlchemy binary expression for the comparison.

        Raises:
            NotImplementedError: This backend does not support DB-side comparison.
        """  # noqa: DOC202
        msg = "PasslibBackend does not support DB-side comparison."
        raise NotImplementedError(msg)

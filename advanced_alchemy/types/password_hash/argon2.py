"""Argon2 Hashing Backend using argon2-cffi."""

from typing import TYPE_CHECKING, Any, Union

from advanced_alchemy.types.password_hash.base import HashingBackend

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement

from argon2 import PasswordHasher  # pyright: ignore
from argon2.exceptions import InvalidHash, VerifyMismatchError  # pyright: ignore


class Argon2Hasher(HashingBackend):
    """Hashing backend using Argon2 via the argon2-cffi library.

    Relies on the `argon2-cffi` package being installed.
    Install with `pip install argon2-cffi` or `uv pip install argon2-cffi`.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize Argon2Backend.

        Args:
            **kwargs: Optional keyword arguments to pass to the argon2.PasswordHasher constructor.
                      See argon2-cffi documentation for available parameters (e.g., time_cost,
                      memory_cost, parallelism, hash_len, salt_len, type).
        """
        self.hasher = PasswordHasher(**kwargs)  # pyright: ignore

    def hash(self, value: "Union[str, bytes]") -> str:
        """Hash the password using Argon2.

        Args:
            value: The plain text password (will be encoded to UTF-8 if string).

        Returns:
            The Argon2 hash string.
        """
        if isinstance(value, str):
            value = value.encode("utf-8")
        return self.hasher.hash(value)

    def verify(self, plain: "Union[str, bytes]", hashed: str) -> bool:
        """Verify a plain text password against an Argon2 hash.

        Args:
            plain: The plain text password (will be encoded to UTF-8 if string).
            hashed: The Argon2 hash string to verify against.

        Returns:
            True if the password matches the hash, False otherwise.
        """
        if isinstance(plain, str):
            plain = plain.encode("utf-8")
        try:
            self.hasher.verify(hashed, plain)  # pyright: ignore
        except VerifyMismatchError:  # pyright: ignore
            return False
        except InvalidHash:  # pyright: ignore
            # Consider logging this case as it might indicate a corrupted hash
            return False
        return True

    @staticmethod
    def identify(hashed: "Union[str, bytes]") -> bool:
        """Identify if a hash string is potentially an Argon2 hash.

        Checks for the standard Argon2 prefixes ($argon2i$, $argon2d$, $argon2id$).

        Args:
            hashed: The potential hash string.

        Returns:
            True if the hash starts with a known Argon2 prefix, False otherwise.
        """
        return isinstance(hashed, str) and hashed.startswith(("$argon2i$", "$argon2d$", "$argon2id$"))

    def compare_expression(self, column: "ColumnElement[str]", plain: "Union[str, bytes]") -> "BinaryExpression[bool]":
        """Direct SQL comparison is not supported for Argon2.

        Raises:
            NotImplementedError: Always raised.
        """
        msg = "Argon2Backend does not support direct SQL comparison."
        raise NotImplementedError(msg)

"""Argon2 Hashing Backend using argon2-cffi."""

import contextlib
from typing import TYPE_CHECKING, Any, Union, cast

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.password_hash.base import HashingBackend

if TYPE_CHECKING:
    from sqlalchemy import BinaryExpression, ColumnElement

PasswordHasher = None  # type: ignore[var-annotated]
InvalidHash = None  # type: ignore[var-annotated]
VerifyMismatchError = None  # type: ignore[var-annotated]
with contextlib.suppress(ImportError):
    from argon2 import PasswordHasher  # type: ignore[assignment]
    from argon2.exceptions import InvalidHash, VerifyMismatchError  # type: ignore[assignment]


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

        Raises:
            MissingDependencyError: If the argon2-cffi package is not installed.
        """
        if PasswordHasher is None:
            raise MissingDependencyError(package="argon2-cffi", install_package="argon2")
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
        return cast("str", self.hasher.hash(value))  # pyright: ignore

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
        except VerifyMismatchError:  # type: ignore[misc]
            return False
        except InvalidHash:  # type: ignore[misc]
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

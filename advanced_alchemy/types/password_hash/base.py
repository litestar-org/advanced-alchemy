"""Base classes for password hashing backends."""

import abc
from typing import Any, Union, cast

from sqlalchemy import BinaryExpression, ColumnElement, FunctionElement, String, TypeDecorator


class HashingBackend(abc.ABC):
    """Abstract base class for password hashing backends.

    This class defines the interface that all password hashing backends must implement.
    Concrete implementations should provide the actual hashing and verification logic.
    """

    @staticmethod
    def _ensure_bytes(value: Union[str, bytes]) -> bytes:
        if isinstance(value, str):
            return value.encode("utf-8")
        return value

    @abc.abstractmethod
    def hash(self, value: "Union[str, bytes]") -> "Union[str, Any]":
        """Hash the given value.

        Args:
            value: The plain text value to hash.

        Returns:
            Either a string (the hash) or a SQLAlchemy SQL expression for DB-side hashing.
        """

    @abc.abstractmethod
    def verify(self, plain: "Union[str, bytes]", hashed: str) -> bool:
        """Verify a plain text value against a hash.

        Args:
            plain: The plain text value to verify.
            hashed: The hash to verify against.

        Returns:
            True if the plain text matches the hash, False otherwise.
        """

    @abc.abstractmethod
    def compare_expression(self, column: "ColumnElement[str]", plain: "Union[str, bytes]") -> "BinaryExpression[bool]":
        """Generate a SQLAlchemy expression for comparing a column with a plain text value.

        Args:
            column: The SQLAlchemy column to compare.
            plain: The plain text value to compare against.

        Returns:
            A SQLAlchemy binary expression for the comparison.
        """


class HashedPassword:
    """Wrapper class for a hashed password.

    This class holds the hash string and provides a method to verify a plain text password against it.
    """

    def __hash__(self) -> int:
        return hash(self.hash_string)

    def __init__(self, hash_string: str, backend: "HashingBackend") -> None:
        """Initialize a HashedPassword object.

        Args:
            hash_string: The hash string.
            backend: The hashing backend to use for verification.
        """
        self.hash_string = hash_string
        self.backend = backend

    def verify(self, plain_password: "Union[str, bytes]") -> bool:
        """Verify a plain text password against this hash.

        Args:
            plain_password: The plain text password to verify.

        Returns:
            True if the password matches the hash, False otherwise.
        """
        return self.backend.verify(plain_password, self.hash_string)


class PasswordHash(TypeDecorator[str]):
    """SQLAlchemy TypeDecorator for storing hashed passwords in a database.

    This type provides transparent hashing of password values using the specified backend.
    It extends :class:`sqlalchemy.types.TypeDecorator` and implements String as its underlying type.
    """

    impl = String
    cache_ok = True

    def __init__(self, backend: "HashingBackend", length: int = 128) -> None:
        """Initialize the PasswordHash TypeDecorator.

        Args:
            backend: The hashing backend class to use
            length: The maximum length of the hash string. Defaults to 128.
        """
        self.length = length
        super().__init__(length=length)
        self.backend = backend

    @property
    def python_type(self) -> "type[str]":
        """Returns the Python type for this type decorator.

        Returns:
            The Python string type.
        """
        return str

    def process_bind_param(self, value: Any, dialect: Any) -> "Union[str, FunctionElement[str], None]":
        """Process the value before binding it to the SQL statement.

        This method hashes the value using the specified backend.
        If the backend returns a SQLAlchemy FunctionElement (for DB-side hashing),
        it is returned directly. Otherwise, the hashed string is returned.

        Args:
            value: The value to process.
            dialect: The SQLAlchemy dialect.

        Returns:
            The hashed string, a SQLAlchemy FunctionElement, or None.
        """
        if value is None:
            return value

        hashed_value = self.backend.hash(value)

        # Check if the backend returned a SQL function for DB-side hashing
        if isinstance(hashed_value, FunctionElement):
            return cast("FunctionElement[str]", hashed_value)

        # Otherwise, assume it's a string or HashedPassword object (convert to string)
        return str(hashed_value)

    def process_result_value(self, value: Any, dialect: Any) -> "Union[HashedPassword, None]":  # type: ignore[override]
        """Process the value after retrieving it from the database.

        This method wraps the hash string in a HashedPassword object.

        Args:
            value: The value to process.
            dialect: The SQLAlchemy dialect.

        Returns:
            A HashedPassword object or None if the input is None.
        """
        if value is None:
            return value
        # Ensure the retrieved value is a string before passing to HashedPassword
        return HashedPassword(str(value), self.backend)

    def compare_value(
        self, column: "ColumnElement[str]", plain_password: "Union[str, bytes]"
    ) -> "BinaryExpression[bool]":
        """Generate a SQLAlchemy expression for comparing a column with a plain text password.

        Args:
            column: The SQLAlchemy column to compare.
            plain_password: The plain text password to compare against.

        Returns:
            A SQLAlchemy binary expression for the comparison.
        """
        return self.backend.compare_expression(column, plain_password)

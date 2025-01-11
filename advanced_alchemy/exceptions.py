# ruff: noqa: UP007
from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Callable, Generator, TypedDict, Union, cast

from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from sqlalchemy.exc import InvalidRequestError as SQLAlchemyInvalidRequestError
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError, StatementError

from advanced_alchemy.utils.deprecation import deprecated

__all__ = (
    "AdvancedAlchemyError",
    "ConflictError",
    "DuplicateKeyError",
    "ErrorMessages",
    "ForeignKeyError",
    "ImproperConfigurationError",
    "IntegrityError",
    "MissingDependencyError",
    "MultipleResultsFoundError",
    "NotFoundError",
    "RepositoryError",
    "SerializationError",
    "wrap_sqlalchemy_exception",
)


DUPLICATE_KEY_REGEXES = {
    "postgresql": [
        re.compile(
            r"^.*duplicate\s+key.*\"(?P<columns>[^\"]+)\"\s*\n.*Key\s+\((?P<key>.*)\)=\((?P<value>.*)\)\s+already\s+exists.*$",
        ),
        re.compile(r"^.*duplicate\s+key.*\"(?P<columns>[^\"]+)\"\s*\n.*$"),
    ],
    "sqlite": [
        re.compile(r"^.*columns?(?P<columns>[^)]+)(is|are)\s+not\s+unique$"),
        re.compile(r"^.*UNIQUE\s+constraint\s+failed:\s+(?P<columns>.+)$"),
        re.compile(r"^.*PRIMARY\s+KEY\s+must\s+be\s+unique.*$"),
    ],
    "mysql": [
        re.compile(r"^.*\b1062\b.*Duplicate entry '(?P<value>.*)' for key '(?P<columns>[^']+)'.*$"),
        re.compile(r"^.*\b1062\b.*Duplicate entry \\'(?P<value>.*)\\' for key \\'(?P<columns>.+)\\'.*$"),
    ],
    "oracle": [],
    "spanner+spanner": [],
    "duckdb": [],
    "mssql": [],
    "bigquery": [],
    "cockroach": [],
}

FOREIGN_KEY_REGEXES = {
    "postgresql": [
        re.compile(
            r".*on table \"(?P<table>[^\"]+)\" violates "
            r"foreign key constraint \"(?P<constraint>[^\"]+)\".*\n"
            r"DETAIL:  Key \((?P<key>.+)\)=\(.+\) "
            r"is (not present in|still referenced from) table "
            r"\"(?P<key_table>[^\"]+)\".",
        ),
    ],
    "sqlite": [
        re.compile(r"(?i).*foreign key constraint failed"),
    ],
    "mysql": [
        re.compile(
            r".*Cannot (add|delete) or update a (child|parent) row: "
            r'a foreign key constraint fails \([`"].+[`"]\.[`"](?P<table>.+)[`"], '
            r'CONSTRAINT [`"](?P<constraint>.+)[`"] FOREIGN KEY '
            r'\([`"](?P<key>.+)[`"]\) REFERENCES [`"](?P<key_table>.+)[`"] ',
        ),
    ],
    "oracle": [],
    "spanner+spanner": [],
    "duckdb": [],
    "mssql": [],
    "bigquery": [],
    "cockroach": [],
}

CHECK_CONSTRAINT_REGEXES = {
    "postgresql": [
        re.compile(r".*new row for relation \"(?P<table>.+)\" violates check constraint (?P<check_name>.+)"),
    ],
    "sqlite": [],
    "mysql": [],
    "oracle": [],
    "spanner+spanner": [],
    "duckdb": [],
    "mssql": [],
    "bigquery": [],
    "cockroach": [],
}


class AdvancedAlchemyError(Exception):
    """Base exception class from which all Advanced Alchemy exceptions inherit."""

    detail: str

    def __init__(self, *args: Any, detail: str = "") -> None:
        """Initialize ``AdvancedAlchemyException``.

        Args:
            *args: args are converted to :class:`str` before passing to :class:`Exception`
            detail: detail of the exception.
        """
        str_args = [str(arg) for arg in args if arg]
        if not detail:
            if str_args:
                detail, *str_args = str_args
            elif hasattr(self, "detail"):
                detail = self.detail
        self.detail = detail
        super().__init__(*str_args)

    def __repr__(self) -> str:
        if self.detail:
            return f"{self.__class__.__name__} - {self.detail}"
        return self.__class__.__name__

    def __str__(self) -> str:
        return " ".join((*self.args, self.detail)).strip()


class MissingDependencyError(AdvancedAlchemyError, ImportError):
    """Missing optional dependency.

    This exception is raised when a module depends on a dependency that has not been installed.

    Args:
        package: Name of the missing package.
        install_package: Optional alternative package name to install.
    """

    def __init__(self, package: str, install_package: str | None = None) -> None:
        super().__init__(
            f"Package {package!r} is not installed but required. You can install it by running "
            f"'pip install advanced_alchemy[{install_package or package}]' to install advanced_alchemy with the required extra "
            f"or 'pip install {install_package or package}' to install the package separately",
        )


class ImproperConfigurationError(AdvancedAlchemyError):
    """Improper Configuration error.

    This exception is raised when there is an issue with the configuration of a module.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class SerializationError(AdvancedAlchemyError):
    """Encoding or decoding error.

    This exception is raised when serialization or deserialization of an object fails.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class RepositoryError(AdvancedAlchemyError):
    """Base repository exception type.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class ConflictError(RepositoryError):
    """Data integrity error.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.

    Note:
        This class is deprecated in favor of :class:`advanced_alchemy.exceptions.IntegrityError`.
    """

    @deprecated(
        version="0.7.1",
        alternative="advanced_alchemy.exceptions.IntegrityError",
        kind="method",
        removal_in="1.0.0",
        info="`ConflictError` has been renamed to `IntegrityError`",
    )
    def __init__(self, *args: Any, detail: str = "") -> None:
        super().__init__(*args, detail=detail)


class IntegrityError(RepositoryError):
    """Data integrity error.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class DuplicateKeyError(IntegrityError):
    """Duplicate key error.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class ForeignKeyError(IntegrityError):
    """Foreign key error.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class NotFoundError(RepositoryError):
    """Not found error.

    This exception is raised when a requested resource is not found.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class MultipleResultsFoundError(RepositoryError):
    """Multiple results found error.

    This exception is raised when a single result was expected but multiple were found.

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class InvalidRequestError(RepositoryError):
    """Invalid request error.

    This exception is raised when SQLAlchemy is unable to complete the request due to a runtime error

    Args:
        *args: Variable length argument list passed to parent class.
        detail: Detailed error message.
    """


class ErrorMessages(TypedDict, total=False):
    duplicate_key: Union[str, Callable[[Exception], str]]
    integrity: Union[str, Callable[[Exception], str]]
    foreign_key: Union[str, Callable[[Exception], str]]
    multiple_rows: Union[str, Callable[[Exception], str]]
    check_constraint: Union[str, Callable[[Exception], str]]
    other: Union[str, Callable[[Exception], str]]


def _get_error_message(error_messages: ErrorMessages, key: str, exc: Exception) -> str:
    template: Union[str, Callable[[Exception], str]] = error_messages.get(key, f"{key} error: {exc}")  # type: ignore[assignment]
    if callable(template):  # pyright: ignore[reportUnknownArgumentType]
        template = template(exc)  # pyright: ignore[reportUnknownVariableType]
    return template  # pyright: ignore[reportUnknownVariableType]


@contextmanager
def wrap_sqlalchemy_exception(
    error_messages: ErrorMessages | None = None,
    dialect_name: str | None = None,
) -> Generator[None, None, None]:
    """Do something within context to raise a ``RepositoryError`` chained
    from an original ``SQLAlchemyError``.

        >>> try:
        ...     with wrap_sqlalchemy_exception():
        ...         raise SQLAlchemyError("Original Exception")
        ... except RepositoryError as exc:
        ...     print(
        ...         f"caught repository exception from {type(exc.__context__)}"
        ...     )
        caught repository exception from <class 'sqlalchemy.exc.SQLAlchemyError'>
    """
    try:
        yield

    except MultipleResultsFound as exc:
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="multiple_rows", exc=exc)
        else:
            msg = "Multiple rows matched the specified data"
        raise MultipleResultsFoundError(detail=msg) from exc
    except SQLAlchemyIntegrityError as exc:
        if error_messages is not None and dialect_name is not None:
            _keys_to_regex = {
                "duplicate_key": (DUPLICATE_KEY_REGEXES.get(dialect_name, []), DuplicateKeyError),
                "check_constraint": (CHECK_CONSTRAINT_REGEXES.get(dialect_name, []), IntegrityError),
                "foreign_key": (FOREIGN_KEY_REGEXES.get(dialect_name, []), ForeignKeyError),
            }
            detail = " - ".join(str(exc_arg) for exc_arg in exc.orig.args) if exc.orig.args else ""  # type: ignore[union-attr] # pyright: ignore[reportArgumentType,reportOptionalMemberAccess]
            for key, (regexes, exception) in _keys_to_regex.items():
                for regex in regexes:
                    if (match := regex.findall(detail)) and match[0]:
                        raise exception(
                            detail=_get_error_message(error_messages=error_messages, key=key, exc=exc),
                        ) from exc

            raise IntegrityError(
                detail=_get_error_message(error_messages=error_messages, key="integrity", exc=exc),
            ) from exc
        raise IntegrityError(detail=f"An integrity error occurred: {exc}") from exc
    except SQLAlchemyInvalidRequestError as exc:
        raise InvalidRequestError(detail="An invalid request was made.") from exc
    except StatementError as exc:
        raise IntegrityError(
            detail=cast(str, getattr(exc.orig, "detail", "There was an issue processing the statement."))
        ) from exc
    except SQLAlchemyError as exc:
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="other", exc=exc)
        else:
            msg = f"An exception occurred: {exc}"
        raise RepositoryError(detail=msg) from exc
    except AttributeError as exc:
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="other", exc=exc)
        else:
            msg = f"An attribute error occurred during processing: {exc}"
        raise RepositoryError(detail=msg) from exc

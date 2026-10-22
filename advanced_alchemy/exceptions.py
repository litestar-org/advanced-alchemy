import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, Final, TypedDict, cast

from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from sqlalchemy.exc import InvalidRequestError as SQLAlchemyInvalidRequestError
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError, StatementError

__all__ = (
    "AdvancedAlchemyError",
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


SQLSTATE_TO_ERROR_KEY: Final[dict[str, str]] = {
    "23505": "duplicate_key",
    "23503": "foreign_key",
    "23514": "check_constraint",
}

SQLITE_ERRORCODE_TO_ERROR_KEY: Final[dict[int, str]] = {
    2067: "duplicate_key",
    1555: "duplicate_key",
    787: "foreign_key",
    275: "check_constraint",
}

MYSQL_ERRNO_TO_ERROR_KEY: Final[dict[int, str]] = {
    1062: "duplicate_key",
    1169: "duplicate_key",
    1216: "foreign_key",
    1217: "foreign_key",
    1451: "foreign_key",
    1452: "foreign_key",
    3819: "check_constraint",
    4025: "check_constraint",
}

ORACLE_ERRNO_TO_ERROR_KEY: Final[dict[int, str]] = {
    1: "duplicate_key",
    2291: "foreign_key",
    2292: "foreign_key",
    2290: "check_constraint",
}

MSSQL_ERRNO_TO_ERROR_KEY: Final[dict[int, str]] = {
    2601: "duplicate_key",
    2627: "duplicate_key",
}


DUPLICATE_KEY_REGEXES: Final[dict[str, list[re.Pattern[str]]]] = {
    "postgresql": [
        re.compile(
            r"^.*duplicate\s+key.*\"(?P<columns>[^\"]+)\"\s*\n.*Key\s+\((?P<key>.*)\)=\((?P<value>.*)\)\s+already\s+exists.*$",
        ),
        re.compile(r"^.*duplicate\s+key.*\"(?P<columns>[^\"]+)\"\s*\n.*$"),
    ],
    "cockroachdb": [
        re.compile(
            r"^.*duplicate\s+key.*\"(?P<columns>[^\"]+)\"\s*\n.*Key\s+\((?P<key>.*)\)=\((?P<value>.*)\)\s+already\s+exists.*$",
        ),
        re.compile(r"^.*duplicate\s+key.*\"(?P<columns>[^\"]+)\"\s*\n.*$"),
        re.compile(r"(?i).*duplicate key value.*"),
        re.compile(r"(?i).*unique constraint.*failed.*"),
    ],
    "sqlite": [
        re.compile(r"^.*columns?(?P<columns>[^)]+)(is|are)\s+not\s+unique$"),
        re.compile(r"^.*UNIQUE\s+constraint\s+failed:\s+(?P<columns>.+)$"),
        re.compile(r"^.*PRIMARY\s+KEY\s+must\s+be\s+unique.*$"),
    ],
    "mysql": [
        re.compile(r"^.*\b1062\b.*Duplicate entry '(?P<value>.*)' for key '(?P<columns>[^']+)'.*$"),
        re.compile(r"^.*\b1062\b.*Duplicate entry \\'(?P<value>.*)\\' for key \\'(?P<columns>.+)\\'.*$"),
        re.compile(r"^.*\b(1062|1169)\b.*Duplicate entry.*$"),
    ],
    "mariadb": [
        re.compile(r"^.*\b1062\b.*Duplicate entry '(?P<value>.*)' for key '(?P<columns>[^']+)'.*$"),
        re.compile(r"^.*\b1062\b.*Duplicate entry \\'(?P<value>.*)\\' for key \\'(?P<columns>.+)\\'.*$"),
        re.compile(r"^.*\b(1062|1169)\b.*Duplicate entry.*$"),
    ],
    "oracle": [
        re.compile(r"(?i).*ORA-00001:\s*unique constraint.*violated.*"),
        re.compile(r"(?i).*ORA-00001.*"),
    ],
    "spanner": [
        re.compile(r"(?i).*ALREADY_EXISTS:.*(unique constraint|already exists).*"),
        re.compile(r"(?i).*already exists:\s*row.*"),
    ],
    "spanner+spanner": [
        re.compile(r"(?i).*ALREADY_EXISTS:.*(unique constraint|already exists).*"),
        re.compile(r"(?i).*already exists:\s*row.*"),
    ],
    "duckdb": [
        re.compile(r"(?i).*Constraint Error: Duplicate key.*"),
        re.compile(r"(?i).*PRIMARY KEY or UNIQUE constraint violation.*"),
    ],
    "mssql": [
        re.compile(r"(?i).*\b(2601|2627)\b.*Cannot insert duplicate key.*"),
        re.compile(r"(?i).*Cannot insert duplicate key.*"),
        re.compile(r"(?i).*Violation of (PRIMARY KEY|UNIQUE KEY) constraint.*"),
    ],
    "bigquery": [],
}

FOREIGN_KEY_REGEXES: Final[dict[str, list[re.Pattern[str]]]] = {
    "postgresql": [
        re.compile(
            r".*on table \"(?P<table>[^\"]+)\" violates "
            r"foreign key constraint \"(?P<constraint>[^\"]+)\".*\n"
            r"DETAIL:  Key \((?P<key>.+)\)=\(.+\) "
            r"is (not present in|still referenced from) table "
            r"\"(?P<key_table>[^\"]+)\".",
        ),
    ],
    "cockroachdb": [
        re.compile(
            r".*on table \"(?P<table>[^\"]+)\" violates "
            r"foreign key constraint \"(?P<constraint>[^\"]+)\".*\n"
            r"DETAIL:  Key \((?P<key>.+)\)=\(.+\) "
            r"is (not present in|still referenced from) table "
            r"\"(?P<key_table>[^\"]+)\".",
        ),
        re.compile(r"(?i).*foreign key constraint.*violated.*"),
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
        re.compile(r"(?i).*\b(1216|1217|1451|1452)\b.*foreign key constraint fails.*"),
    ],
    "mariadb": [
        re.compile(
            r".*Cannot (add|delete) or update a (child|parent) row: "
            r'a foreign key constraint fails \([`"].+[`"]\.[`"](?P<table>.+)[`"], '
            r'CONSTRAINT [`"](?P<constraint>.+)[`"] FOREIGN KEY '
            r'\([`"](?P<key>.+)[`"]\) REFERENCES [`"](?P<key_table>.+)[`"] ',
        ),
        re.compile(r"(?i).*\b(1216|1217|1451|1452)\b.*foreign key constraint fails.*"),
    ],
    "oracle": [
        re.compile(r"(?i).*ORA-0229[12]:\s*integrity constraint.*violated.*"),
        re.compile(r"(?i).*ORA-0229[12].*"),
    ],
    "spanner": [
        re.compile(r"(?i).*FAILED_PRECONDITION:.*Foreign key constraint.*"),
        re.compile(r"(?i).*Foreign key violation.*"),
    ],
    "spanner+spanner": [
        re.compile(r"(?i).*FAILED_PRECONDITION:.*Foreign key constraint.*"),
        re.compile(r"(?i).*Foreign key violation.*"),
    ],
    "duckdb": [
        re.compile(r"(?i).*Constraint Error: Foreign Key Constraint Violation.*"),
        re.compile(r"(?i).*violates foreign key constraint.*"),
    ],
    "mssql": [
        re.compile(r"(?i).*\b547\b.*conflicted with the (FOREIGN KEY|REFERENCE) constraint.*"),
        re.compile(r"(?i).*conflicted with the (FOREIGN KEY|REFERENCE) constraint.*"),
    ],
    "bigquery": [],
}

CHECK_CONSTRAINT_REGEXES: Final[dict[str, list[re.Pattern[str]]]] = {
    "postgresql": [
        re.compile(r".*new row for relation \"(?P<table>.+)\" violates check constraint \"?(?P<check_name>[^\"]+)\"?"),
    ],
    "cockroachdb": [
        re.compile(r".*new row for relation \"(?P<table>.+)\" violates check constraint \"?(?P<check_name>[^\"]+)\"?"),
        re.compile(r"(?i).*check constraint.*violated.*"),
    ],
    "sqlite": [
        re.compile(r"(?i).*CHECK constraint failed.*"),
    ],
    "mysql": [
        re.compile(r"(?i).*Check constraint '(?P<check_name>.+)' is violated.*"),
        re.compile(r"(?i).*\b3819\b.*Check constraint.*is violated.*"),
    ],
    "mariadb": [
        re.compile(r"(?i).*Constraint '(?P<check_name>.+)' failed.*"),
        re.compile(r"(?i).*\b4025\b.*Constraint.*failed.*"),
        re.compile(r"(?i).*Check constraint '(?P<check_name>.+)' is violated.*"),
    ],
    "oracle": [
        re.compile(r"(?i).*ORA-02290:\s*check constraint.*violated.*"),
        re.compile(r"(?i).*ORA-02290.*"),
    ],
    "spanner": [
        re.compile(r"(?i).*FAILED_PRECONDITION:.*Check constraint.*"),
    ],
    "spanner+spanner": [
        re.compile(r"(?i).*FAILED_PRECONDITION:.*Check constraint.*"),
    ],
    "duckdb": [
        re.compile(r"(?i).*Constraint Error: CHECK constraint.*"),
    ],
    "mssql": [
        re.compile(r"(?i).*\b547\b.*conflicted with the CHECK constraint.*"),
        re.compile(r"(?i).*conflicted with the CHECK constraint.*"),
    ],
    "bigquery": [],
}


_MSSQL_CONSTRAINT_VIOLATION_CODE: Final[int] = 547


def _get_driver_code(orig: BaseException, dialect_name: str | None) -> str | None:
    """Classify driver-specific integer or string error codes."""
    if not orig.args:
        return None
    first_arg = orig.args[0]
    if (
        isinstance(first_arg, int)
        and (dialect_name in {"mysql", "mariadb"} or dialect_name is None)
        and (key := MYSQL_ERRNO_TO_ERROR_KEY.get(first_arg))
    ):
        return key
    if dialect_name == "oracle" or dialect_name is None:
        ora_code = getattr(first_arg, "code", first_arg)
        if isinstance(ora_code, int) and (key := ORACLE_ERRNO_TO_ERROR_KEY.get(ora_code)):
            return key
    if dialect_name == "mssql" or dialect_name is None:
        number = getattr(orig, "number", first_arg if isinstance(first_arg, int) else None)
        if isinstance(number, int):
            if key := MSSQL_ERRNO_TO_ERROR_KEY.get(number):
                return key
            if number == _MSSQL_CONSTRAINT_VIOLATION_CODE:
                detail = " - ".join(str(arg) for arg in orig.args).upper()
                return "foreign_key" if ("FOREIGN KEY" in detail or "REFERENCE" in detail) else "check_constraint"
    return None


def _get_error_key_by_code(orig: BaseException | None, dialect_name: str | None = None) -> str | None:
    """Classify a DBAPI integrity error by driver error code.

    Args:
        orig: The DBAPI exception.
        dialect_name: The name of the dialect, or None if unknown.

    Returns:
        The error message key, or None when no known code is present.
    """
    if orig is None:
        return None
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if isinstance(sqlstate, str) and (key := SQLSTATE_TO_ERROR_KEY.get(sqlstate)):
        return key
    sqlite_errorcode = getattr(orig, "sqlite_errorcode", None)
    if isinstance(sqlite_errorcode, int) and (key := SQLITE_ERRORCODE_TO_ERROR_KEY.get(sqlite_errorcode)):
        return key
    return _get_driver_code(orig, dialect_name)


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
    duplicate_key: str | Callable[[Exception], str]
    integrity: str | Callable[[Exception], str]
    foreign_key: str | Callable[[Exception], str]
    multiple_rows: str | Callable[[Exception], str]
    check_constraint: str | Callable[[Exception], str]
    other: str | Callable[[Exception], str]
    not_found: str | Callable[[Exception], str]


def _get_error_message(error_messages: ErrorMessages | None, key: str, exc: Exception) -> str:
    if error_messages is None:
        return f"{key} error: {exc}"
    template: str | Callable[[Exception], str] = error_messages.get(key, f"{key} error: {exc}")  # type: ignore[assignment]
    if callable(template):  # pyright: ignore[reportUnknownArgumentType]
        template = template(exc)  # pyright: ignore[reportUnknownVariableType]
    return template  # pyright: ignore[reportUnknownVariableType]


@contextmanager
def wrap_sqlalchemy_exception(  # noqa: C901, PLR0915
    error_messages: ErrorMessages | None = None,
    dialect_name: str | None = None,
    wrap_exceptions: bool = True,
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

    Args:
        error_messages: Error messages to use for the exception.
        dialect_name: The name of the dialect to use for the exception.
        wrap_exceptions: Wrap SQLAlchemy exceptions in a ``RepositoryError``.  When set to ``False``, the original exception will be raised.

    Raises:
        NotFoundError: Raised when no rows matched the specified data.
        MultipleResultsFound: Raised when multiple rows matched the specified data.
        IntegrityError: Raised when an integrity error occurs.
        InvalidRequestError: Raised when an invalid request was made to SQLAlchemy.
        RepositoryError: Raised for other SQLAlchemy errors.
        AttributeError: Raised when an attribute error occurs during processing.
        SQLAlchemyError: Raised for general SQLAlchemy errors.
        StatementError: Raised when there is an issue processing the statement.
        MultipleResultsFoundError: Raised when multiple rows matched the specified data.

    """
    try:
        yield

    except NotFoundError as exc:
        if wrap_exceptions is False:
            raise
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="not_found", exc=exc)
        else:
            msg = "No rows matched the specified data"
        raise NotFoundError(detail=msg) from exc
    except MultipleResultsFound as exc:
        if wrap_exceptions is False:
            raise
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="multiple_rows", exc=exc)
        else:
            msg = "Multiple rows matched the specified data"
        raise MultipleResultsFoundError(detail=msg) from exc
    except SQLAlchemyIntegrityError as exc:
        if wrap_exceptions is False:
            raise
        if (key := _get_error_key_by_code(exc.orig, dialect_name)) is not None:
            exception_cls = {
                "duplicate_key": DuplicateKeyError,
                "foreign_key": ForeignKeyError,
                "check_constraint": IntegrityError,
            }.get(key, IntegrityError)
            raise exception_cls(
                detail=_get_error_message(error_messages=error_messages, key=key, exc=exc),
            ) from exc

        orig_args = getattr(exc.orig, "args", None)
        detail = " - ".join(str(exc_arg) for exc_arg in orig_args) if orig_args else ""
        if dialect_name is not None:
            keys_to_regex = {
                "duplicate_key": (DUPLICATE_KEY_REGEXES.get(dialect_name, []), DuplicateKeyError),
                "check_constraint": (CHECK_CONSTRAINT_REGEXES.get(dialect_name, []), IntegrityError),
                "foreign_key": (FOREIGN_KEY_REGEXES.get(dialect_name, []), ForeignKeyError),
            }
            for category_key, (regexes, exception) in keys_to_regex.items():
                for regex in regexes:
                    if regex.search(detail):
                        raise exception(
                            detail=_get_error_message(error_messages=error_messages, key=category_key, exc=exc),
                        ) from exc
        else:
            for category_key, mapping, exception in (
                ("duplicate_key", DUPLICATE_KEY_REGEXES, DuplicateKeyError),
                ("foreign_key", FOREIGN_KEY_REGEXES, ForeignKeyError),
                ("check_constraint", CHECK_CONSTRAINT_REGEXES, IntegrityError),
            ):
                for regex_list in mapping.values():
                    for regex in regex_list:
                        if regex.search(detail):
                            raise exception(
                                detail=_get_error_message(error_messages=error_messages, key=category_key, exc=exc),
                            ) from exc

        raise IntegrityError(
            detail=_get_error_message(error_messages=error_messages, key="integrity", exc=exc),
        ) from exc
    except SQLAlchemyInvalidRequestError as exc:
        if wrap_exceptions is False:
            raise
        raise InvalidRequestError(detail="An invalid request was made.") from exc
    except StatementError as exc:
        if wrap_exceptions is False:
            raise
        raise IntegrityError(
            detail=cast("str", getattr(exc.orig, "detail", "There was an issue processing the statement."))
        ) from exc
    except SQLAlchemyError as exc:
        if wrap_exceptions is False:
            raise
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="other", exc=exc)
        else:
            msg = f"An exception occurred: {exc}"
        raise RepositoryError(detail=msg) from exc
    except AttributeError as exc:
        if wrap_exceptions is False:
            raise
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="other", exc=exc)
        else:
            msg = f"An attribute error occurred during processing: {exc}"
        raise RepositoryError(detail=msg) from exc

import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, TypedDict, cast

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
    "mariadb": [
        re.compile(r"^.*\b1062\b.*Duplicate entry '(?P<value>.*)' for key '(?P<columns>[^']+)'.*$"),
        re.compile(r"^.*\b1062\b.*Duplicate entry \\'(?P<value>.*)\\' for key \\'(?P<columns>.+)\\'.*$"),
    ],
    "oracle": [
        re.compile(r"ORA-00001:\s*unique\s+constraint\s*\((?P<columns>[^)]+)\)\s*violated", re.IGNORECASE),
        re.compile(r"\bORA-00001:", re.IGNORECASE),
    ],
    "spanner+spanner": [],
    "duckdb": [
        re.compile(
            r"^.*Duplicate\s+key\s+\"(?P<columns>[^\"]+)\"\s+violates\s+(primary\s+key|unique)\s+constraint.*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^.*Duplicate\s+key.*violates\s+(primary\s+key|unique)\s+constraint.*$",
            re.IGNORECASE,
        ),
    ],
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
    "mariadb": [
        re.compile(
            r".*Cannot (add|delete) or update a (child|parent) row: "
            r'a foreign key constraint fails \([`"].+[`"]\.[`"](?P<table>.+)[`"], '
            r'CONSTRAINT [`"](?P<constraint>.+)[`"] FOREIGN KEY '
            r'\([`"](?P<key>.+)[`"]\) REFERENCES [`"](?P<key_table>.+)[`"] ',
        ),
    ],
    "oracle": [
        re.compile(r"ORA-0229[12]:\s*integrity\s+constraint\s*\((?P<constraint>[^)]+)\)\s*violated", re.IGNORECASE),
        re.compile(r"\bORA-0229[12]:", re.IGNORECASE),
    ],
    "spanner+spanner": [],
    "duckdb": [
        re.compile(r".*Violates\s+foreign\s+key\s+constraint.*", re.IGNORECASE),
    ],
    "mssql": [],
    "bigquery": [],
    "cockroach": [],
}

CHECK_CONSTRAINT_REGEXES = {
    "postgresql": [
        re.compile(r".*new row for relation \"(?P<table>.+)\" violates check constraint (?P<check_name>.+)"),
    ],
    "sqlite": [
        re.compile(r"(?i).*CHECK constraint failed.*"),
    ],
    "mysql": [
        re.compile(r"(?i).*check constraint .* is violated.*"),
        re.compile(r"(?i).*CONSTRAINT .* failed.*"),
    ],
    "mariadb": [
        re.compile(r"(?i).*CONSTRAINT .* failed.*"),
        re.compile(r"(?i).*check constraint .* is violated.*"),
    ],
    "oracle": [
        re.compile(r"ORA-02290:\s*check\s+constraint\s*\((?P<check_name>[^)]+)\)\s*violated", re.IGNORECASE),
        re.compile(r"\bORA-02290:", re.IGNORECASE),
    ],
    "spanner+spanner": [],
    "duckdb": [
        re.compile(r".*CHECK\s+constraint\s+failed.*", re.IGNORECASE),
    ],
    "mssql": [],
    "bigquery": [],
    "cockroach": [],
}

SQLSTATE_TO_ERROR_KEY = {
    "23505": "duplicate_key",
    "23503": "foreign_key",
    "23514": "check_constraint",
}

ORACLE_ERROR_CODE_TO_ERROR_KEY = {
    1: "duplicate_key",
    2291: "foreign_key",
    2292: "foreign_key",
    2290: "check_constraint",
}

DUCKDB_ERROR_TYPE_TO_KEY = {
    "duplicate_key": "duplicate_key",
    "primary_key": "duplicate_key",
    "unique": "duplicate_key",
    "foreign_key": "foreign_key",
    "check_constraint": "check_constraint",
    "check": "check_constraint",
}

SQLITE_ERRORCODE_TO_ERROR_KEY = {
    2067: "duplicate_key",
    1555: "duplicate_key",
    787: "foreign_key",
    275: "check_constraint",
}

MYSQL_ERRNO_TO_ERROR_KEY = {
    1062: "duplicate_key",
    1169: "duplicate_key",
    1586: "duplicate_key",
    1216: "foreign_key",
    1217: "foreign_key",
    1451: "foreign_key",
    1452: "foreign_key",
    3819: "check_constraint",
    4025: "check_constraint",
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
    """Custom error message templates or callables keyed by error category."""

    duplicate_key: str | Callable[[Exception], str]
    """Error message or callable for duplicate key constraint violations."""
    integrity: str | Callable[[Exception], str]
    """Error message or callable for general integrity constraint violations."""
    foreign_key: str | Callable[[Exception], str]
    """Error message or callable for foreign key constraint violations."""
    multiple_rows: str | Callable[[Exception], str]
    """Error message or callable for queries returning multiple rows when one was expected."""
    check_constraint: str | Callable[[Exception], str]
    """Error message or callable for check constraint violations."""
    other: str | Callable[[Exception], str]
    """Error message or callable for unclassified repository exceptions."""
    not_found: str | Callable[[Exception], str]
    """Error message or callable when no matching row is found."""


def _get_error_message(error_messages: ErrorMessages | None, key: str, exc: Exception) -> str:
    if error_messages is None:
        return f"{key} error: {exc}"
    template: str | Callable[[Exception], str] = error_messages.get(key, f"{key} error: {exc}")  # type: ignore[assignment]
    if callable(template):  # pyright: ignore[reportUnknownArgumentType]
        template = template(exc)  # pyright: ignore[reportUnknownVariableType]
    return template  # pyright: ignore[reportUnknownVariableType]


def _get_error_key_by_code(orig: BaseException | None, dialect_name: str) -> str | None:
    """Classify a DBAPI integrity error by the native error code exposed by the driver.

    Checks ``error_type`` for DuckDB, ``sqlstate`` / ``pgcode`` for PostgreSQL and
    CockroachDB, ``sqlite_errorcode`` for SQLite on Python 3.11+, ``errno`` or
    ``args[0]`` for MySQL and MariaDB drivers, and ``args[0].code`` for Oracle
    ``oracledb``.

    Args:
        orig: The underlying DBAPI exception, if present.
        dialect_name: The normalized SQLAlchemy dialect name.

    Returns:
        The matching ``ErrorMessages`` key, or ``None`` when no mapped code is present.
    """
    if orig is None:
        return None
    error_type = getattr(orig, "error_type", None)
    if (
        isinstance(error_type, str)
        and (key := DUCKDB_ERROR_TYPE_TO_KEY.get("_".join(error_type.strip().lower().split()))) is not None
    ):
        return key
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if isinstance(sqlstate, str) and (key := SQLSTATE_TO_ERROR_KEY.get(sqlstate)) is not None:
        return key
    sqlite_errorcode = getattr(orig, "sqlite_errorcode", None)
    if isinstance(sqlite_errorcode, int) and not isinstance(sqlite_errorcode, bool):
        return SQLITE_ERRORCODE_TO_ERROR_KEY.get(sqlite_errorcode)
    driver_args: tuple[Any, ...] = getattr(orig, "args", ())
    dialect_key: str | None = None
    if dialect_name in {"mysql", "mariadb"}:
        mysql_errno = getattr(orig, "errno", None)
        if not (isinstance(mysql_errno, int) and not isinstance(mysql_errno, bool)) and driver_args:
            mysql_errno = driver_args[0]
        if isinstance(mysql_errno, int) and not isinstance(mysql_errno, bool):
            dialect_key = MYSQL_ERRNO_TO_ERROR_KEY.get(mysql_errno)
    elif dialect_name == "oracle" and driver_args:
        oracle_code = getattr(driver_args[0], "code", None)
        if isinstance(oracle_code, int) and not isinstance(oracle_code, bool):
            dialect_key = ORACLE_ERROR_CODE_TO_ERROR_KEY.get(oracle_code)
    return dialect_key


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
        if error_messages is not None and dialect_name is not None:
            base_dialect = dialect_name.split("+", 1)[0]
            keys_to_regex = {
                "duplicate_key": (
                    DUPLICATE_KEY_REGEXES.get(dialect_name) or DUPLICATE_KEY_REGEXES.get(base_dialect, []),
                    DuplicateKeyError,
                ),
                "check_constraint": (
                    CHECK_CONSTRAINT_REGEXES.get(dialect_name) or CHECK_CONSTRAINT_REGEXES.get(base_dialect, []),
                    IntegrityError,
                ),
                "foreign_key": (
                    FOREIGN_KEY_REGEXES.get(dialect_name) or FOREIGN_KEY_REGEXES.get(base_dialect, []),
                    ForeignKeyError,
                ),
            }
            if (key := _get_error_key_by_code(exc.orig, base_dialect)) is not None:
                raise keys_to_regex[key][1](
                    detail=_get_error_message(error_messages=error_messages, key=key, exc=exc),
                ) from exc
            driver_args: tuple[Any, ...] = getattr(exc.orig, "args", ())
            detail = " - ".join(str(exc_arg) for exc_arg in driver_args) if driver_args else ""
            for key, (regexes, exception) in keys_to_regex.items():
                for regex in regexes:
                    if regex.search(detail):
                        raise exception(
                            detail=_get_error_message(error_messages=error_messages, key=key, exc=exc),
                        ) from exc

            raise IntegrityError(
                detail=_get_error_message(error_messages=error_messages, key="integrity", exc=exc),
            ) from exc
        raise IntegrityError(detail=f"An integrity error occurred: {exc}") from exc
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

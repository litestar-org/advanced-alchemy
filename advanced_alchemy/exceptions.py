from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Callable, Generator, TypedDict, Union

from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from sqlalchemy.exc import MultipleResultsFound, SQLAlchemyError

from advanced_alchemy.utils.deprecation import deprecated

KEY_PATTERN = r"(?P<type_key>uq|ck|fk|pk)_(?P<table>[a-z][a-z0-9]+)_[a-z_]+"
regex = re.compile(KEY_PATTERN)


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

    This exception is raised only when a module depends on a dependency that has not been installed.
    """

    def __init__(self, package: str, install_package: str | None = None) -> None:
        super().__init__(
            f"Package {package!r} is not installed but required. You can install it by running "
            f"'pip install advanced_alchemy[{install_package or package}]' to install advanced_alchemy with the required extra "
            f"or 'pip install {install_package or package}' to install the package separately",
        )


class ImproperConfigurationError(AdvancedAlchemyError):
    """Improper Configuration error.

    This exception is raised only when a module depends on a dependency that has not been installed.
    """


class SerializationError(AdvancedAlchemyError):
    """Encoding or decoding of an object failed."""


class RepositoryError(AdvancedAlchemyError):
    """Base repository exception type."""


class ConflictError(RepositoryError):
    """Data integrity error."""

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
    """Data integrity error."""


class NotFoundError(RepositoryError):
    """An identity does not exist."""


class MultipleResultsFoundError(AdvancedAlchemyError):
    """A single database result was required but more than one were found."""


class ErrorMessages(TypedDict):
    unique_constraint: Union[str, Callable[[Exception], str]]  # noqa: UP007
    check_constraint: Union[str, Callable[[Exception], str]]  # noqa: UP007
    integrity: Union[str, Callable[[Exception], str]]  # noqa: UP007
    foreign_key: Union[str, Callable[[Exception], str]]  # noqa: UP007
    multiple_rows: Union[str, Callable[[Exception], str]]  # noqa: UP007
    other: Union[str, Callable[[Exception], str]]  # noqa: UP007


def _get_error_message(error_messages: ErrorMessages, key: str, exc: Exception) -> str:
    template: Union[str, Callable[[Exception], str]] = error_messages[key]  # type: ignore[literal-required] # noqa: UP007
    if callable(template):  # pyright: ignore[reportUnknownArgumentType]
        template = template(exc)  # pyright: ignore[reportUnknownVariableType]
    return template  # pyright: ignore[reportUnknownVariableType]


@contextmanager
def wrap_sqlalchemy_exception(
    error_messages: ErrorMessages | None = None,
    constraint_pattern: str | None = None,
) -> Generator[None, None, None]:
    """Do something within context to raise a ``RepositoryError`` chained
    from an original ``SQLAlchemyError``.

        >>> try:
        ...     with wrap_sqlalchemy_exception():
        ...         raise SQLAlchemyError("Original Exception")
        ... except RepositoryError as exc:
        ...     print(f"caught repository exception from {type(exc.__context__)}")
        ...
        caught repository exception from <class 'sqlalchemy.exc.SQLAlchemyError'>
    """
    try:
        constraint_pattern = KEY_PATTERN if constraint_pattern is None else constraint_pattern
        yield
    except MultipleResultsFound as exc:
        if error_messages is not None:
            msg = _get_error_message(error_messages=error_messages, key="multiple_rows", exc=exc)
        else:
            msg = "Multiple rows matched the specified data"
        raise MultipleResultsFoundError(detail=msg) from exc
    except SQLAlchemyIntegrityError as exc:
        if error_messages is not None:
            m = regex.search(str(exc.orig))
            constraint_type = "integrity" if m is None else m.groupdict()["type_key"]
            if constraint_type == "uk":
                msg = _get_error_message(error_messages=error_messages, key="unique_constraint", exc=exc)
            if constraint_type == "ck":
                msg = _get_error_message(error_messages=error_messages, key="check_constraint", exc=exc)
            if constraint_type == "fk":
                msg = _get_error_message(error_messages=error_messages, key="foreign_key", exc=exc)
            else:
                msg = _get_error_message(error_messages=error_messages, key="integrity", exc=exc)
        else:
            msg = f"An integrity error occurred: {exc}"
        raise IntegrityError(detail=msg) from exc
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
            msg = f"An attribute error ocurred during processing: {exc}"
        raise RepositoryError(detail=msg) from exc

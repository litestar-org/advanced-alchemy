import contextlib

import pytest
from sqlalchemy.exc import (
    IntegrityError as SQLAlchemyIntegrityError,
)
from sqlalchemy.exc import (
    InvalidRequestError as SQLAlchemyInvalidRequestError,
)
from sqlalchemy.exc import (
    MultipleResultsFound,
    SQLAlchemyError,
    StatementError,
)

from advanced_alchemy.exceptions import (
    DuplicateKeyError,
    IntegrityError,
    InvalidRequestError,
    MultipleResultsFoundError,
    RepositoryError,
    wrap_sqlalchemy_exception,
)


async def test_repo_get_or_create_deprecation() -> None:
    with pytest.warns(DeprecationWarning):
        from advanced_alchemy.exceptions import ConflictError

        with contextlib.suppress(Exception):
            raise ConflictError


def test_wrap_sqlalchemy_exception_multiple_results_found() -> None:
    with pytest.raises(MultipleResultsFoundError), wrap_sqlalchemy_exception():
        raise MultipleResultsFound()


@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql"])
def test_wrap_sqlalchemy_exception_integrity_error_duplicate_key(dialect_name: str) -> None:
    error_message = {
        "postgresql": 'duplicate key value violates unique constraint "uq_%(table_name)s_%(column_0_name)s"',
        "sqlite": "UNIQUE constraint failed: %(table_name)s.%(column_0_name)s",
        "mysql": "1062 (23000): Duplicate entry '%(value)s' for key '%(table_name)s.%(column_0_name)s'",
    }
    with (
        pytest.raises(DuplicateKeyError),
        wrap_sqlalchemy_exception(
            dialect_name=dialect_name,
            error_messages={"duplicate_key": error_message[dialect_name]},
        ),
    ):
        if dialect_name == "postgresql":
            exception = SQLAlchemyIntegrityError(
                "INSERT INTO table (id) VALUES (1)",
                {"table_name": "table", "column_0_name": "id"},
                Exception(
                    'duplicate key value violates unique constraint "uq_table_id"\nDETAIL:  Key (id)=(1) already exists.',
                ),
            )
        elif dialect_name == "sqlite":
            exception = SQLAlchemyIntegrityError(
                "INSERT INTO table (id) VALUES (1)",
                {"table_name": "table", "column_0_name": "id"},
                Exception("UNIQUE constraint failed: table.id"),
            )
        else:
            exception = SQLAlchemyIntegrityError(
                "INSERT INTO table (id) VALUES (1)",
                {"table_name": "table", "column_0_name": "id", "value": "1"},
                Exception("1062 (23000): Duplicate entry '1' for key 'table.id'"),
            )

        raise exception


def test_wrap_sqlalchemy_exception_integrity_error_other() -> None:
    with pytest.raises(IntegrityError), wrap_sqlalchemy_exception():
        raise SQLAlchemyIntegrityError("original", {}, Exception("original"))


def test_wrap_sqlalchemy_exception_invalid_request_error() -> None:
    with pytest.raises(InvalidRequestError), wrap_sqlalchemy_exception():
        raise SQLAlchemyInvalidRequestError("original", {}, Exception("original"))


def test_wrap_sqlalchemy_exception_statement_error() -> None:
    with pytest.raises(IntegrityError), wrap_sqlalchemy_exception():
        raise StatementError("original", None, {}, Exception("original"))  # pyright: ignore[reportArgumentType]


def test_wrap_sqlalchemy_exception_sqlalchemy_error() -> None:
    with pytest.raises(RepositoryError), wrap_sqlalchemy_exception():
        raise SQLAlchemyError("original")


def test_wrap_sqlalchemy_exception_attribute_error() -> None:
    with pytest.raises(RepositoryError), wrap_sqlalchemy_exception():
        raise AttributeError("original")


def test_wrap_sqlalchemy_exception_no_wrap() -> None:
    with pytest.raises(SQLAlchemyError), wrap_sqlalchemy_exception(wrap_exceptions=False):
        raise SQLAlchemyError("original")
    with pytest.raises(SQLAlchemyIntegrityError), wrap_sqlalchemy_exception(wrap_exceptions=False):
        raise SQLAlchemyIntegrityError(statement="select 1", params=None, orig=BaseException())
    with pytest.raises(MultipleResultsFound), wrap_sqlalchemy_exception(wrap_exceptions=False):
        raise MultipleResultsFound()
    with pytest.raises(SQLAlchemyInvalidRequestError), wrap_sqlalchemy_exception(wrap_exceptions=False):
        raise SQLAlchemyInvalidRequestError()
    with pytest.raises(AttributeError), wrap_sqlalchemy_exception(wrap_exceptions=False):
        raise AttributeError()


def test_wrap_sqlalchemy_exception_custom_error_message() -> None:
    def custom_message(exc: Exception) -> str:
        return f"Custom: {exc}"

    with (
        pytest.raises(RepositoryError) as excinfo,
        wrap_sqlalchemy_exception(
            error_messages={"other": custom_message},
        ),
    ):
        raise SQLAlchemyError("original")

    assert str(excinfo.value) == "Custom: original"


def test_wrap_sqlalchemy_exception_no_error_messages() -> None:
    with pytest.raises(RepositoryError) as excinfo, wrap_sqlalchemy_exception():
        raise SQLAlchemyError("original")

    assert str(excinfo.value) == "An exception occurred: original"


def test_wrap_sqlalchemy_exception_no_match() -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name="postgresql",
            error_messages={"integrity": "Integrity error"},
        ),
    ):
        raise SQLAlchemyIntegrityError("original", {}, Exception("original"))

    assert str(excinfo.value) == "Integrity error"

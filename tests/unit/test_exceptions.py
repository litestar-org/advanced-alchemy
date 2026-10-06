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
    ForeignKeyError,
    IntegrityError,
    InvalidRequestError,
    MultipleResultsFoundError,
    NotFoundError,
    RepositoryError,
    wrap_sqlalchemy_exception,
)


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


def test_wrap_sqlalchemy_exception_not_found_error() -> None:
    with pytest.raises(NotFoundError, match="No rows matched the specified data"), wrap_sqlalchemy_exception():
        raise NotFoundError("No item found when one was expected")


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
    with (
        pytest.raises(NotFoundError, match="No item found when one was expected"),
        wrap_sqlalchemy_exception(wrap_exceptions=False),
    ):
        raise NotFoundError("No item found when one was expected")


def test_custom_not_found_error_message() -> None:
    with (
        pytest.raises(NotFoundError, match="Custom Error"),
        wrap_sqlalchemy_exception(error_messages={"not_found": "Custom Error"}),
    ):
        raise NotFoundError("original")


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


class _DriverError(Exception):
    def __init__(self, *args: object, **attrs: object) -> None:
        super().__init__(*args)
        for name, value in attrs.items():
            setattr(self, name, value)


@pytest.mark.parametrize("dialect_name", ["postgresql", "cockroachdb"])
@pytest.mark.parametrize("code_attr", ["sqlstate", "pgcode"])
@pytest.mark.parametrize(
    ("sqlstate", "message", "detail", "expected"),
    [
        (
            "23505",
            'duplicate key value violates unique constraint "uq_table_id"',
            "Key (id)=(1) already exists.",
            DuplicateKeyError,
        ),
        (
            "23503",
            'insert or update on table "child" violates foreign key constraint "fk_parent"',
            'Key (parent_id)=(999) is not present in table "parent".',
            ForeignKeyError,
        ),
        (
            "23514",
            'new row for relation "table" violates check constraint "ck_positive"',
            "Failing row contains (1, -1).",
            IntegrityError,
        ),
    ],
)
def test_wrap_sqlalchemy_exception_integrity_error_by_sqlstate(
    dialect_name: str, code_attr: str, sqlstate: str, message: str, detail: str, expected: type[IntegrityError]
) -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name=dialect_name,
            error_messages={"duplicate_key": "duplicate", "foreign_key": "foreign", "check_constraint": "check"},
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError(message, detail=detail, **{code_attr: sqlstate}))

    assert excinfo.type is expected
    assert str(excinfo.value) == {"23505": "duplicate", "23503": "foreign", "23514": "check"}[sqlstate]


def test_wrap_sqlalchemy_exception_ignores_non_string_sqlstate() -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(dialect_name="postgresql", error_messages={"integrity": "integrity"}),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError("whatever", sqlstate=["23505"]))

    assert excinfo.type is IntegrityError
    assert str(excinfo.value) == "integrity"


@pytest.mark.parametrize(
    ("errno", "message", "expected"),
    [
        (1062, "Duplicate entry '1' for key 'uq_table_id'", DuplicateKeyError),
        (
            1452,
            "Cannot add or update a child row: a foreign key constraint fails "
            "(`db`.`child`, CONSTRAINT `fk_parent` FOREIGN KEY (`parent_id`) REFERENCES `parent` (`id`))",
            ForeignKeyError,
        ),
    ],
)
def test_wrap_sqlalchemy_exception_mysql_generic_sqlstate_uses_regexes(
    errno: int, message: str, expected: type[IntegrityError]
) -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name="mysql", error_messages={"duplicate_key": "duplicate", "foreign_key": "foreign"}
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError(errno, message, sqlstate="23000"))

    assert excinfo.type is expected
    assert str(excinfo.value) == {1062: "duplicate", 1452: "foreign"}[errno]

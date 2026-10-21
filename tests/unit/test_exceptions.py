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
    ErrorMessages,
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
    """Synthetic DBAPI exception exposing arbitrary attributes for unit testing."""

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
    ("dialect_name", "orig", "expected"),
    [
        ("sqlite", _DriverError("whatever", sqlite_errorcode=2067), DuplicateKeyError),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=1555), DuplicateKeyError),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=787), ForeignKeyError),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=275), IntegrityError),
        ("mysql", _DriverError(1062, "whatever"), DuplicateKeyError),
        ("mysql", _DriverError(1169, "whatever"), DuplicateKeyError),
        ("mysql", _DriverError(1216, "whatever"), ForeignKeyError),
        ("mysql", _DriverError(1451, "whatever"), ForeignKeyError),
        ("mariadb", _DriverError(1452, "whatever"), ForeignKeyError),
        ("mysql", _DriverError(3819, "whatever"), IntegrityError),
        ("mariadb", _DriverError(4025, "whatever"), IntegrityError),
        ("oracle", _DriverError(1, "ORA-00001: unique constraint"), DuplicateKeyError),
        ("oracle", _DriverError(2291, "ORA-02291: integrity constraint"), ForeignKeyError),
        ("oracle", _DriverError(2292, "ORA-02292: integrity constraint"), ForeignKeyError),
        ("oracle", _DriverError(2290, "ORA-02290: check constraint"), IntegrityError),
        ("mssql", _DriverError(2601, "duplicate key"), DuplicateKeyError),
        ("mssql", _DriverError(2627, "duplicate key"), DuplicateKeyError),
        ("mssql", _DriverError(547, "conflicted with the FOREIGN KEY constraint"), ForeignKeyError),
        ("mssql", _DriverError(547, "conflicted with the CHECK constraint"), IntegrityError),
    ],
)
def test_wrap_sqlalchemy_exception_integrity_error_by_native_code(
    dialect_name: str, orig: Exception, expected: type[IntegrityError]
) -> None:
    error_messages: ErrorMessages = {
        "duplicate_key": "duplicate",
        "foreign_key": "foreign",
        "check_constraint": "check",
        "integrity": "integrity",
    }
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(dialect_name=dialect_name, error_messages=error_messages),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, orig)

    assert excinfo.type is expected
    assert (
        str(excinfo.value)
        == {DuplicateKeyError: "duplicate", ForeignKeyError: "foreign", IntegrityError: "check"}[expected]
    )


@pytest.mark.parametrize(
    ("dialect_name", "message", "expected"),
    [
        ("oracle", "ORA-00001: unique constraint (APP.USERS_EMAIL_UNQ) violated", DuplicateKeyError),
        ("oracle", "ORA-02291: integrity constraint (APP.FK_CHILD) violated - parent key not found", ForeignKeyError),
        ("oracle", "ORA-02292: integrity constraint (APP.FK_CHILD) violated - child record found", ForeignKeyError),
        ("oracle", "ORA-02290: check constraint (APP.CK_AGE) violated", IntegrityError),
        (
            "mssql",
            "Cannot insert duplicate key row in object 'dbo.users' with unique index 'UQ_email'.",
            DuplicateKeyError,
        ),
        (
            "mssql",
            "The INSERT statement conflicted with the FOREIGN KEY constraint 'FK_orders_users'.",
            ForeignKeyError,
        ),
        ("mssql", "The INSERT statement conflicted with the CHECK constraint 'CK_positive'.", IntegrityError),
        ("duckdb", "Constraint Error: Duplicate key 'id: 1' violates primary key constraint", DuplicateKeyError),
        ("duckdb", "Constraint Error: Foreign Key Constraint Violation", ForeignKeyError),
        ("duckdb", "Constraint Error: CHECK constraint failed", IntegrityError),
        ("spanner", "ALREADY_EXISTS: Unique constraint UsersByEmail violated", DuplicateKeyError),
        ("spanner", "FAILED_PRECONDITION: Foreign key constraint OrdersUsers violated", ForeignKeyError),
        ("spanner", "FAILED_PRECONDITION: Check constraint check_age violated", IntegrityError),
        ("spanner+spanner", "ALREADY_EXISTS: Unique constraint UsersByEmail violated", DuplicateKeyError),
        ("spanner+spanner", "FAILED_PRECONDITION: Foreign key constraint OrdersUsers violated", ForeignKeyError),
        ("spanner+spanner", "FAILED_PRECONDITION: Check constraint check_age violated", IntegrityError),
        ("mariadb", "Constraint 'check_status' failed for `app`.`users`", IntegrityError),
        ("sqlite", "CHECK constraint failed: users", IntegrityError),
    ],
)
def test_wrap_sqlalchemy_exception_integrity_error_by_regex(
    dialect_name: str, message: str, expected: type[IntegrityError]
) -> None:
    error_messages: ErrorMessages = {
        "duplicate_key": "duplicate",
        "foreign_key": "foreign",
        "check_constraint": "check",
        "integrity": "integrity",
    }
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(dialect_name=dialect_name, error_messages=error_messages),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, Exception(message))

    assert excinfo.type is expected
    assert (
        str(excinfo.value)
        == {DuplicateKeyError: "duplicate", ForeignKeyError: "foreign", IntegrityError: "check"}[expected]
    )


def test_wrap_sqlalchemy_exception_without_dialect_name() -> None:
    with (
        pytest.raises(DuplicateKeyError),
        wrap_sqlalchemy_exception(),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError("duplicate", sqlite_errorcode=2067))

    with (
        pytest.raises(DuplicateKeyError),
        wrap_sqlalchemy_exception(),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, Exception("ORA-00001: unique constraint violated"))


def test_wrap_sqlalchemy_exception_without_error_messages() -> None:
    with (
        pytest.raises(DuplicateKeyError) as excinfo,
        wrap_sqlalchemy_exception(dialect_name="sqlite"),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError("duplicate", sqlite_errorcode=2067))

    assert "duplicate_key error" in str(excinfo.value)


@pytest.mark.parametrize(
    ("dialect_name", "orig"),
    [
        ("sqlite", _DriverError("whatever", sqlite_errorcode=1299)),
        ("mysql", _DriverError(1048, "whatever")),
    ],
)
def test_wrap_sqlalchemy_exception_unknown_native_code(dialect_name: str, orig: Exception) -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(dialect_name=dialect_name, error_messages={"integrity": "integrity"}),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, orig)

    assert excinfo.type is IntegrityError
    assert str(excinfo.value) == "integrity"

from typing import Optional

import pytest
import sqlalchemy as sa
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


@pytest.mark.parametrize("dialect_name", ["postgresql", "sqlite", "mysql", "oracle", "duckdb"])
def test_wrap_sqlalchemy_exception_integrity_error_duplicate_key(dialect_name: str) -> None:
    error_message = {
        "postgresql": 'duplicate key value violates unique constraint "uq_%(table_name)s_%(column_0_name)s"',
        "sqlite": "UNIQUE constraint failed: %(table_name)s.%(column_0_name)s",
        "mysql": "1062 (23000): Duplicate entry '%(value)s' for key '%(table_name)s.%(column_0_name)s'",
        "oracle": "ORA-00001: unique constraint (APP.UQ_%(table_name)s_%(column_0_name)s) violated",
        "duckdb": 'Duplicate key "%(column_0_name)s: %(value)s" violates primary key constraint.',
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
        elif dialect_name == "mysql":
            exception = SQLAlchemyIntegrityError(
                "INSERT INTO table (id) VALUES (1)",
                {"table_name": "table", "column_0_name": "id", "value": "1"},
                Exception("1062 (23000): Duplicate entry '1' for key 'table.id'"),
            )
        elif dialect_name == "oracle":
            exception = SQLAlchemyIntegrityError(
                "INSERT INTO table (id) VALUES (1)",
                {"table_name": "table", "column_0_name": "id"},
                Exception("ORA-00001: unique constraint (APP.UQ_TABLE_ID) violated"),
            )
        else:
            exception = SQLAlchemyIntegrityError(
                "INSERT INTO table (id) VALUES (1)",
                {"table_name": "table", "column_0_name": "id", "value": "1"},
                Exception('Constraint Error: Duplicate key "id: 1" violates primary key constraint.'),
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
def test_wrap_sqlalchemy_exception_mysql_generic_sqlstate(
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


class _OracleErrorDetail:
    """Stand-in for ``oracledb``'s ``_Error`` object stored at ``exc.orig.args[0]``."""

    __slots__ = ("code", "full_code", "message")

    def __init__(self, code: object, message: str) -> None:
        self.code = code
        self.full_code = f"ORA-{code:05d}" if isinstance(code, int) and not isinstance(code, bool) else "ORA-00000"
        self.message = message

    def __str__(self) -> str:
        return f"{self.full_code}: {self.message}"


@pytest.mark.parametrize("dialect_name", ["oracle", "oracle+oracledb"])
@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        (1, "unique constraint (APP.UQ_PARENT_NAME) violated", DuplicateKeyError),
        (2291, "integrity constraint (APP.FK_CHILD_PARENT) violated - parent key not found", ForeignKeyError),
        (2292, "integrity constraint (APP.FK_CHILD_PARENT) violated - child record found", ForeignKeyError),
        (2290, "check constraint (APP.CK_CHILD_QUANTITY) violated", IntegrityError),
    ],
)
def test_wrap_sqlalchemy_exception_integrity_error_by_oracle_code(
    dialect_name: str, code: int, message: str, expected: type[IntegrityError]
) -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name=dialect_name,
            error_messages={"duplicate_key": "duplicate", "foreign_key": "foreign", "check_constraint": "check"},
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError(_OracleErrorDetail(code, message)))

    assert excinfo.type is expected
    assert str(excinfo.value) == {1: "duplicate", 2291: "foreign", 2292: "foreign", 2290: "check"}[code]


@pytest.mark.parametrize("dialect_name", ["oracle", "oracle+oracledb"])
@pytest.mark.parametrize(
    ("message", "expected", "expected_detail"),
    [
        (
            "ORA-00001: unique constraint (APP.UQ_PARENT_NAME) violated\n"
            "Help: https://docs.oracle.com/error-help/db/ora-00001/",
            DuplicateKeyError,
            "duplicate",
        ),
        (
            "ORA-00001: unique constraint (HR.EMP_EMAIL_UK) violated on table HR.EMPLOYEES columns (EMAIL)",
            DuplicateKeyError,
            "duplicate",
        ),
        (
            "ORA-00001: violation de contrainte unique (HR.EMP_EMAIL_UK)",
            DuplicateKeyError,
            "duplicate",
        ),
        (
            "ORA-02291: integrity constraint (APP.FK_CHILD_PARENT) violated - parent key not found",
            ForeignKeyError,
            "foreign",
        ),
        (
            "ORA-02292: integrity constraint (APP.FK_CHILD_PARENT) violated - child record found",
            ForeignKeyError,
            "foreign",
        ),
        (
            "ORA-02290: check constraint (APP.CK_CHILD_QUANTITY) violated",
            IntegrityError,
            "check",
        ),
    ],
)
def test_wrap_sqlalchemy_exception_oracle_regex_fallback(
    dialect_name: str, message: str, expected: type[IntegrityError], expected_detail: str
) -> None:
    """Verify string-only Oracle integrity errors fall back to regex classification across 19c, 23ai, and localized formats."""
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name=dialect_name,
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
                "integrity": "integrity",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError(message))

    assert excinfo.type is expected
    assert str(excinfo.value) == expected_detail


@pytest.mark.parametrize(
    ("dialect_name", "orig", "expected"),
    [
        ("sqlite", _DriverError("whatever", sqlite_errorcode=2067), DuplicateKeyError),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=1555), DuplicateKeyError),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=787), ForeignKeyError),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=275), IntegrityError),
        ("sqlite+aiosqlite", _DriverError("whatever", sqlite_errorcode=2067), DuplicateKeyError),
        ("mysql", _DriverError(1062, "whatever"), DuplicateKeyError),
        ("mysql", _DriverError(1169, "whatever"), DuplicateKeyError),
        ("mysql", _DriverError(1586, "whatever"), DuplicateKeyError),
        ("mysql", _DriverError("whatever", errno=1062), DuplicateKeyError),
        ("mysql", _DriverError(1216, "whatever"), ForeignKeyError),
        ("mysql", _DriverError(1217, "whatever"), ForeignKeyError),
        ("mysql", _DriverError(1451, "whatever"), ForeignKeyError),
        ("mariadb", _DriverError(1452, "whatever"), ForeignKeyError),
        ("mariadb+asyncmy", _DriverError("whatever", errno=1452), ForeignKeyError),
        ("mysql", _DriverError(3819, "whatever"), IntegrityError),
        ("mariadb", _DriverError(4025, "whatever"), IntegrityError),
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
    ("dialect_name", "message", "expected", "expected_detail"),
    [
        ("sqlite", "CHECK constraint failed: quantity > 0", IntegrityError, "check"),
        ("mysql", "Check constraint 'ck_quantity' is violated.", IntegrityError, "check"),
        ("mariadb", "CONSTRAINT `ck_quantity` failed for `db`.`items`", IntegrityError, "check"),
        ("mariadb", "1062 (23000): Duplicate entry '1' for key 'items.PRIMARY'", DuplicateKeyError, "duplicate"),
    ],
)
def test_wrap_sqlalchemy_exception_sqlite_mysql_mariadb_regex_fallback(
    dialect_name: str, message: str, expected: type[IntegrityError], expected_detail: str
) -> None:
    """Verify SQLite, MySQL, and MariaDB regex fallback when native error codes are absent."""
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name=dialect_name,
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
                "integrity": "integrity",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError(message))

    assert excinfo.type is expected
    assert str(excinfo.value) == expected_detail


@pytest.mark.parametrize(
    ("dialect_name", "orig"),
    [
        ("oracle", _DriverError(_OracleErrorDetail(1400, 'cannot insert NULL into ("APP"."CHILD"."LABEL")'))),
        ("oracle", _DriverError("constraint violated")),
        ("oracle", _DriverError(_OracleErrorDetail(True, "constraint violated"))),
        ("oracle", None),
        ("mssql", _DriverError(_OracleErrorDetail(1, "constraint violated"))),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=1299)),
        ("sqlite", _DriverError("whatever", sqlite_errorcode=True)),
        ("mysql", _DriverError(1048, "whatever")),
        ("mysql", _DriverError(True, "whatever")),
        ("postgresql", _DriverError(1062, "whatever")),
    ],
)
def test_wrap_sqlalchemy_exception_oracle_unmapped_or_non_oracle_is_generic(
    dialect_name: str, orig: Optional[BaseException]
) -> None:
    """Verify unmapped native codes, boolean codes, None orig, and mismatched dialects fall back to generic IntegrityError."""
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name=dialect_name,
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
                "integrity": "integrity",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, orig)  # type: ignore[arg-type]

    assert excinfo.type is IntegrityError
    assert str(excinfo.value) == "integrity"


_MSSQL_PREFIX = "[23000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]"


@pytest.mark.parametrize(
    "message",
    [
        "some error (2627) (SQLExecDirectW)",
        "some error (2601) (SQLExecute)",
        "some error (2627) (SQLExecDirectW); [01000] some other error (3621)",
    ],
    ids=["2627", "2601-sqlexecute", "2627-multiple-records"],
)
def test_wrap_sqlalchemy_exception_integrity_error_by_mssql_number(message: str) -> None:
    """Verify mapped native error numbers are classified without relying on the regex fallback."""
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name="mssql",
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
                "integrity": "integrity",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError("23000", message))

    assert excinfo.type is DuplicateKeyError
    assert str(excinfo.value) == "duplicate"


@pytest.mark.parametrize(
    ("message", "expected", "expected_detail"),
    [
        (
            f"{_MSSQL_PREFIX}Violation of PRIMARY KEY constraint 'PK__parent__3213E83F6F227CE8'. "
            "Cannot insert duplicate key in object 'dbo.parent'. The duplicate key value is (1).",
            DuplicateKeyError,
            "duplicate",
        ),
        (
            f"{_MSSQL_PREFIX}Violation of UNIQUE KEY constraint 'uq_parent_code'. "
            "Cannot insert duplicate key in object 'dbo.parent'. The duplicate key value is (a).",
            DuplicateKeyError,
            "duplicate",
        ),
        (
            f"{_MSSQL_PREFIX}Cannot insert duplicate key row in object 'dbo.plain' with unique index 'ix_plain_v'. "
            "The duplicate key value is (1).",
            DuplicateKeyError,
            "duplicate",
        ),
        (
            f'{_MSSQL_PREFIX}The INSERT statement conflicted with the FOREIGN KEY constraint "fk_child_parent". '
            'The conflict occurred in database "master", table "dbo.parent", column \'id\'. (547) (SQLExecDirectW)',
            ForeignKeyError,
            "foreign",
        ),
        (
            f'{_MSSQL_PREFIX}The DELETE statement conflicted with the REFERENCE constraint "fk_child_parent". '
            'The conflict occurred in database "master", table "dbo.child", column \'parent_id\'. '
            "(547) (SQLExecDirectW)",
            ForeignKeyError,
            "foreign",
        ),
        (
            f'{_MSSQL_PREFIX}The INSERT statement conflicted with the CHECK constraint "ck_child_qty". '
            'The conflict occurred in database "master", table "dbo.child", column \'qty\'. (547) (SQLExecDirectW)',
            IntegrityError,
            "check",
        ),
    ],
    ids=["primary-key", "unique-constraint", "unique-index", "fk-insert-547", "fk-delete-547", "check-547"],
)
def test_wrap_sqlalchemy_exception_mssql_regex_fallback(
    message: str, expected: type[IntegrityError], expected_detail: str
) -> None:
    """Verify SQL Server 2022 messages without a mapped error number fall back to regex, including 547 FK vs CHECK."""
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name="mssql",
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
                "integrity": "integrity",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError("23000", message))

    assert excinfo.type is expected
    assert str(excinfo.value) == expected_detail


@pytest.mark.parametrize(
    ("dialect_name", "orig"),
    [
        (
            "mssql",
            _DriverError(
                "23000",
                f"{_MSSQL_PREFIX}Cannot insert the value NULL into column 'label', table 'master.dbo.child'; "
                "column does not allow nulls. INSERT fails. (515) (SQLExecDirectW)",
            ),
        ),
        (
            "mssql",
            _DriverError(
                "23000",
                f"{_MSSQL_PREFIX}Cannot insert the value NULL into column '(2627) (SQLExecDirectW)', table "
                "'master.dbo.child'; column does not allow nulls. INSERT fails. (515) (SQLExecDirectW)",
            ),
        ),
        ("mssql", _DriverError("23000", "some error (2627)")),
        ("mssql", _DriverError("23000")),
        ("postgresql", _DriverError("23000", "some error (2627) (SQLExecDirectW)")),
    ],
    ids=["unmapped-515", "unanchored-number", "no-marker", "no-message", "non-mssql-dialect"],
)
def test_wrap_sqlalchemy_exception_mssql_unmapped_or_non_mssql_is_generic(
    dialect_name: str, orig: BaseException
) -> None:
    """Verify unmapped or unanchored MSSQL numbers, missing messages, and mismatched dialects stay generic."""
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name=dialect_name,
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
                "integrity": "integrity",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, orig)

    assert excinfo.type is IntegrityError
    assert str(excinfo.value) == "integrity"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('Constraint Error: Duplicate key "id: 1" violates primary key constraint.', DuplicateKeyError),
        ('Constraint Error: Duplicate key "email: a@b.com" violates unique constraint.', DuplicateKeyError),
        (
            'Constraint Error: Violates foreign key constraint because key "id: 999" does not exist in the referenced table',
            ForeignKeyError,
        ),
        (
            'Constraint Error: Violates foreign key constraint because key "parent_id: 1" is still referenced by a foreign key in a different table.',
            ForeignKeyError,
        ),
        ("Constraint Error: CHECK constraint failed on table t with expression CHECK((id > 0))", IntegrityError),
    ],
)
def test_wrap_sqlalchemy_exception_duckdb_constraint_regexes(message: str, expected: type[IntegrityError]) -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name="duckdb",
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
                "integrity": "integrity",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, Exception(message))

    assert excinfo.type is expected


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        ("duplicate_key", DuplicateKeyError),
        (" duplicate key ", DuplicateKeyError),
        ("primary_key", DuplicateKeyError),
        ("unique", DuplicateKeyError),
        ("foreign_key", ForeignKeyError),
        ("FOREIGN KEY", ForeignKeyError),
        ("check_constraint", IntegrityError),
        ("check", IntegrityError),
    ],
)
def test_wrap_sqlalchemy_exception_duckdb_native_error_type(error_type: str, expected: type[IntegrityError]) -> None:
    with (
        pytest.raises(IntegrityError) as excinfo,
        wrap_sqlalchemy_exception(
            dialect_name="duckdb",
            error_messages={
                "duplicate_key": "duplicate",
                "foreign_key": "foreign",
                "check_constraint": "check",
            },
        ),
    ):
        raise SQLAlchemyIntegrityError("INSERT", {}, _DriverError("some error", error_type=error_type))

    assert excinfo.type is expected


def test_wrap_sqlalchemy_exception_duckdb_real_engine() -> None:
    engine = sa.create_engine("duckdb:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE parent (id INT PRIMARY KEY);"))
        conn.execute(
            sa.text(
                "CREATE TABLE child (id INT PRIMARY KEY, parent_id INT REFERENCES parent(id), CONSTRAINT chk CHECK (id > 0));"
            )
        )
        conn.execute(sa.text("INSERT INTO parent VALUES (1);"))
        conn.execute(sa.text("INSERT INTO child VALUES (1, 1);"))

    with pytest.raises(DuplicateKeyError), engine.begin() as conn:
        with wrap_sqlalchemy_exception(dialect_name=engine.dialect.name, error_messages={}):
            conn.execute(sa.text("INSERT INTO parent VALUES (1);"))

    with pytest.raises(ForeignKeyError), engine.begin() as conn:
        with wrap_sqlalchemy_exception(dialect_name=engine.dialect.name, error_messages={}):
            conn.execute(sa.text("INSERT INTO child VALUES (2, 999);"))

    with pytest.raises(IntegrityError), engine.begin() as conn:
        with wrap_sqlalchemy_exception(dialect_name=engine.dialect.name, error_messages={}):
            conn.execute(sa.text("INSERT INTO child VALUES (-1, 1);"))

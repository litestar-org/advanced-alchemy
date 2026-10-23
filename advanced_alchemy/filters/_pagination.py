"""Pagination and ordering filters."""

from dataclasses import dataclass
from typing import (
    Any,
    Literal,
    Optional,
    cast,
)

from sqlalchemy import ColumnElement, Integer, Select, case, literal_column
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import operators as op
from sqlalchemy.sql.elements import UnaryExpression

from advanced_alchemy.filters._base import (
    FilterFieldName,
    ModelT,
    PaginationFilter,
    StatementFilter,
    StatementTypeT,
)

__all__ = ("LimitOffset", "OrderBy")


@dataclass
class LimitOffset(PaginationFilter):
    """Limit and offset pagination filter.

    Implements traditional pagination using SQL LIMIT and OFFSET clauses.
    Only applies to SELECT statements; other statement types are returned unmodified.

    Note:
        This filter only modifies SELECT statements. For other statement types
        (UPDATE, DELETE), the statement is returned unchanged.

    See Also:
        - :meth:`sqlalchemy.sql.expression.Select.limit`: SQLAlchemy LIMIT clause
        - :meth:`sqlalchemy.sql.expression.Select.offset`: SQLAlchemy OFFSET clause
    """

    __slots__ = ("limit", "offset")

    limit: int
    """Maximum number of rows to return."""
    offset: int
    """Number of rows to skip before returning results."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply LIMIT/OFFSET pagination to the statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with limit and offset applied

        Note:
            Only modifies SELECT statements. Other statement types are returned as-is.

        See Also:
            :class:`sqlalchemy.sql.expression.Select`: SQLAlchemy SELECT statement
        """
        if isinstance(statement, Select):
            statement = cast("StatementTypeT", statement.limit(self.limit).offset(self.offset))
        return statement


@dataclass(init=False)
class OrderBy(StatementFilter):
    """Order by a specific field.

    Appends an ORDER BY clause to SELECT statements, sorting records by the
    specified field in ascending or descending order.

    Note:
        This filter only modifies SELECT statements. For other statement types,
        the statement is returned unchanged.

    Note:
        ``nulls`` controls where NULLs land. Left as ``None`` the database decides, and the
        databases disagree: PostgreSQL and Oracle sort NULLs last ascending and first descending,
        while MySQL and SQLite do the opposite. Set it explicitly for a stable order across
        backends — ``nulls="last"`` is usually what a user reading a descending list expects, since
        rows with no value otherwise fill the first page.

        MySQL, MariaDB and SQL Server have no ``NULLS FIRST``/``NULLS LAST`` syntax. They sort
        NULL as the lowest value, so ``asc`` with ``nulls="first"`` and ``desc`` with
        ``nulls="last"`` compile to the plain ordering term. The other two placements are emulated
        with a leading ``CASE WHEN ... IS NULL`` sort key. SQL Server requires every ORDER BY term
        to appear in the select list under ``SELECT DISTINCT``, so combine ``nulls`` with a
        ``DISTINCT`` statement there only for those two native placements.

    See Also:
        - :meth:`sqlalchemy.sql.expression.Select.order_by`: SQLAlchemy ORDER BY clause
        - :meth:`sqlalchemy.sql.expression.ColumnElement.asc`: Ascending order
        - :meth:`sqlalchemy.sql.expression.ColumnElement.desc`: Descending order
        - :func:`sqlalchemy.sql.expression.nulls_first`: NULLS FIRST
        - :func:`sqlalchemy.sql.expression.nulls_last`: NULLS LAST
    """

    __slots__ = ("field_name", "nulls", "sort_order")

    field_name: FilterFieldName
    """Field name, model attribute, or func expression (e.g., ``func.random()``)."""
    sort_order: Literal["asc", "desc"]
    """Sort direction ("asc" or "desc")."""
    nulls: Optional[Literal["first", "last"]]
    """Where NULLs sort. ``None`` leaves the placement to the database."""

    def __init__(
        self,
        field_name: FilterFieldName,
        sort_order: Literal["asc", "desc"] = "asc",
        nulls: Optional[Literal["first", "last"]] = None,
    ) -> None:
        self.field_name = field_name
        self.sort_order = sort_order
        self.nulls = nulls

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Append an ORDER BY clause to the statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with an ORDER BY clause

        Note:
            Only modifies SELECT statements. Other statement types are returned as-is.

        See Also:
            :meth:`sqlalchemy.sql.expression.Select.order_by`: SQLAlchemy ORDER BY
        """
        if isinstance(statement, Select):
            field = self._get_instrumented_attr(model, self.field_name)
            ordering: ColumnElement[Any] = field.desc() if self.sort_order == "desc" else field.asc()
            if self.nulls is not None:
                ordering = _NullsPlacement(
                    ordering, modifier=op.nulls_first_op if self.nulls == "first" else op.nulls_last_op
                )
            statement = cast("StatementTypeT", statement.order_by(ordering))
        return statement


class _NullsPlacement(UnaryExpression[Any]):
    """An ORDER BY term that pins where NULLs sort.

    MySQL, MariaDB and SQL Server have no ``NULLS FIRST``/``NULLS LAST`` syntax. Those backends
    sort NULL as the lowest value, so ascending-first and descending-last are already native
    and compile to the plain ordering term; the other two placements are emulated with a leading
    nullity key. Every other backend gets the native clause, which an index on the column can
    still satisfy.

    UnaryExpression preserves ordering traversal for ORM eager loading and includes
    the column, direction and NULL placement in SQL compilation cache keys.
    """

    __slots__ = ()

    inherit_cache = True


@compiles(_NullsPlacement, "mysql")
@compiles(_NullsPlacement, "mariadb")
@compiles(_NullsPlacement, "mssql")
def _compile_nulls_placement_emulated(  # pyright: ignore[reportUnusedFunction]
    element: _NullsPlacement, compiler: Any, **kw: Any
) -> str:
    """Compile emulated NULLS placement for MySQL, MariaDB, and SQL Server.

    Uses literal integer columns instead of bound parameters because parameter placeholders inside
    ``ORDER BY`` are ambiguous on these dialects, and disables label rendering inside ``CASE``
    because SQL Server rejects ``SELECT`` aliases inside ``CASE`` expressions.
    """
    ordering = cast("UnaryExpression[Any]", element.element)
    nulls_go_last = element.modifier is op.nulls_last_op
    if nulls_go_last is (ordering.modifier is op.desc_op):
        return cast("str", compiler.process(ordering, **kw))
    key = case(
        (ordering.element.is_(None), literal_column("1" if nulls_go_last else "0", Integer)),
        else_=literal_column("0" if nulls_go_last else "1", Integer),
    )
    key_kw = {**kw, "render_label_as_label": None}
    return f"{compiler.process(key, **key_kw)}, {compiler.process(ordering, **kw)}"

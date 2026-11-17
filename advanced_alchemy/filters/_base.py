"""Statement filter base class, shared type variables, and ORDER BY NULL placement."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Literal, Optional, Union, cast

from sqlalchemy import ColumnElement, Delete, Integer, Select, Update, case, inspect, literal_column
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import operators as op
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from sqlalchemy.sql.elements import UnaryExpression
from typing_extensions import TypeAlias, TypeVar

from advanced_alchemy.base import ModelProtocol

if TYPE_CHECKING:
    FilterFieldName: TypeAlias = Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]
    InstrumentedField: TypeAlias = Union[ColumnElement[Any], InstrumentedAttribute[Any]]
else:
    FilterFieldName: TypeAlias = Any
    InstrumentedField: TypeAlias = Any

__all__ = (
    "FilterFieldName",
    "InstrumentedField",
    "ModelT",
    "NullsPlacement",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
    "ordering_term",
)

ModelT = TypeVar("ModelT", bound=ModelProtocol)
StatementFilterT = TypeVar("StatementFilterT", bound="StatementFilter")
StatementTypeT = TypeVar(
    "StatementTypeT",
    bound=Union[
        ReturningDelete[tuple[Any]], ReturningUpdate[tuple[Any]], Select[tuple[Any]], Select[Any], Update, Delete
    ],
)


class StatementFilter(ABC):
    """Abstract base class for SQLAlchemy statement filters.

    This class defines the interface for all filter types in the system. Each filter
    implementation must provide a method to append its filtering logic to an existing
    SQLAlchemy statement.
    """

    @abstractmethod
    def append_to_statement(
        self, statement: StatementTypeT, model: type[ModelT], *args: Any, **kwargs: Any
    ) -> StatementTypeT:
        """Append filter conditions to a SQLAlchemy statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            StatementTypeT: Modified SQLAlchemy statement with filter conditions applied

        Raises:
            NotImplementedError: If the concrete class doesn't implement this method

        Note:
            This method must be implemented by all concrete filter classes.

        See Also:
            :meth:`sqlalchemy.sql.expression.Select.where`: SQLAlchemy where clause
        """
        return statement

    @staticmethod
    def _get_instrumented_attr(model: Any, key: FilterFieldName) -> InstrumentedField:
        """Get SQLAlchemy instrumented attribute from model or aliased entity.

        Args:
            model: SQLAlchemy model class, aliased class, or instance.
            key: Attribute name or instrumented attribute.

        Returns:
            InstrumentedField: SQLAlchemy attribute or column expression bound to ``model``.

        See Also:
            :class:`sqlalchemy.orm.attributes.InstrumentedAttribute`: SQLAlchemy attribute
        """
        if isinstance(key, str):
            return cast("InstrumentedAttribute[Any]", getattr(model, key))
        if not isinstance(model, type):
            model_inspector = inspect(model, raiseerr=False)
            if model_inspector is not None and model_inspector.is_aliased_class:
                if isinstance(key, InstrumentedAttribute) and issubclass(
                    model_inspector.mapper.class_, key.parent.class_
                ):
                    return cast("InstrumentedField", getattr(model, key.key))
                if isinstance(key, ColumnElement):
                    return cast(
                        "InstrumentedField",
                        model_inspector._adapter.traverse(key),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                    )
        return key


def ordering_term(column: Any, *, descending: bool, nulls: Optional[Literal["first", "last"]]) -> "ColumnElement[Any]":
    """Build an ORDER BY term with an optional cross-dialect NULL placement."""
    ordering: ColumnElement[Any] = column.desc() if descending else column.asc()
    if nulls is not None:
        ordering = NullsPlacement(ordering, modifier=op.nulls_first_op if nulls == "first" else op.nulls_last_op)
    return ordering


class NullsPlacement(UnaryExpression[Any]):
    """An ORDER BY term that pins where NULLs sort.

    MySQL, MariaDB and SQL Server have no ``NULLS FIRST``/``NULLS LAST`` syntax. Those backends
    sort NULL as the lowest value, so ascending-first and descending-last are already native
    and compile to the plain ordering term; the other two placements are emulated with a leading
    nullity key. Every other backend gets the native clause, which an index on the column can
    still satisfy.

    UnaryExpression preserves ordering traversal for ORM eager loading and includes
    the column, direction and NULL placement in SQL compilation cache keys.
    """

    inherit_cache = True


@compiles(NullsPlacement, "mysql")
@compiles(NullsPlacement, "mariadb")
@compiles(NullsPlacement, "mssql")
def _compile_nulls_placement_emulated(  # pyright: ignore[reportUnusedFunction]
    element: NullsPlacement, compiler: Any, **kw: Any
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

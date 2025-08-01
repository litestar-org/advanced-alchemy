"""SQLAlchemy filter constructs for advanced query operations.

This module provides a comprehensive collection of filter datastructures designed to
enhance SQLAlchemy query construction. It implements type-safe, reusable filter patterns
for common database query operations.

Features:
    Type-safe filter construction, datetime range filtering, collection-based filtering,
    pagination support, search operations, and customizable ordering.

Note:
    All filter classes implement the :class:`StatementFilter` ABC, ensuring consistent
    interface across different filter types.

See Also:
    - :class:`sqlalchemy.sql.expression.Select`: Core SQLAlchemy select expression
    - :class:`sqlalchemy.orm.Query`: SQLAlchemy ORM query interface
    - :mod:`advanced_alchemy.base`: Base model definitions

"""

import datetime
import logging
from abc import ABC, abstractmethod
from collections.abc import Collection
from dataclasses import dataclass
from operator import attrgetter
from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    Literal,
    Optional,
    Union,
    cast,
)

from sqlalchemy import (
    BinaryExpression,
    ColumnElement,
    Date,
    Delete,
    Select,
    Update,
    and_,
    any_,
    exists,
    false,
    not_,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import operators as op
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from typing_extensions import TypeAlias, TypedDict, TypeVar

from advanced_alchemy.base import ModelProtocol

__all__ = (
    "BeforeAfter",
    "CollectionFilter",
    "ComparisonFilter",
    "ExistsFilter",
    "FilterGroup",
    "FilterMap",
    "FilterTypes",
    "InAnyFilter",
    "LimitOffset",
    "LogicalOperatorMap",
    "MultiFilter",
    "NotExistsFilter",
    "NotInCollectionFilter",
    "NotInSearchFilter",
    "OnBeforeAfter",
    "OrderBy",
    "PaginationFilter",
    "SearchFilter",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
)

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=ModelProtocol)
StatementFilterT = TypeVar("StatementFilterT", bound="StatementFilter")
StatementTypeT = TypeVar(
    "StatementTypeT",
    bound=Union[
        ReturningDelete[tuple[Any]], ReturningUpdate[tuple[Any]], Select[tuple[Any]], Select[Any], Update, Delete
    ],
)

logger = logging.getLogger("advanced_alchemy")


# Define TypedDicts for filter and logical maps
class FilterMap(TypedDict):
    before_after: "type[BeforeAfter]"
    on_before_after: "type[OnBeforeAfter]"
    collection: "type[CollectionFilter[Any]]"
    not_in_collection: "type[NotInCollectionFilter[Any]]"
    limit_offset: "type[LimitOffset]"
    order_by: "type[OrderBy]"
    search: "type[SearchFilter]"
    not_in_search: "type[NotInSearchFilter]"
    comparison: "type[ComparisonFilter]"
    exists: "type[ExistsFilter]"
    not_exists: "type[NotExistsFilter]"
    filter_group: "type[FilterGroup]"


class LogicalOperatorMap(TypedDict):
    and_: Callable[..., ColumnElement[bool]]
    or_: Callable[..., ColumnElement[bool]]


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
    def _get_instrumented_attr(model: Any, key: Union[str, InstrumentedAttribute[Any]]) -> InstrumentedAttribute[Any]:
        """Get SQLAlchemy instrumented attribute from model.

        Args:
            model: SQLAlchemy model class or instance
            key: Attribute name or instrumented attribute

        Returns:
            InstrumentedAttribute[Any]: SQLAlchemy instrumented attribute

        See Also:
            :class:`sqlalchemy.orm.attributes.InstrumentedAttribute`: SQLAlchemy attribute
        """
        if isinstance(key, str):
            return cast("InstrumentedAttribute[Any]", getattr(model, key))
        return key


@dataclass
class BeforeAfter(StatementFilter):
    """DateTime range filter with exclusive bounds.

    This filter creates date/time range conditions using < and > operators,
    excluding the boundary values.

    If either `before` or `after` is None, that boundary condition is not applied.

    See Also:
    ---------
        :class:`OnBeforeAfter` : Inclusive datetime range filtering

    """

    field_name: str
    """Name of the model attribute to filter on."""
    before: Optional[datetime.datetime]
    """Filter results where field is earlier than this value."""
    after: Optional[datetime.datetime]
    """Filter results where field is later than this value."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply datetime range conditions to statement.

        Parameters
        ----------
        statement : StatementTypeT
            The SQLAlchemy statement to modify
        model : type[ModelT]
            The SQLAlchemy model class

        Returns:
        --------
        StatementTypeT
            Modified statement with datetime range conditions
        """
        field = self._get_instrumented_attr(model, self.field_name)
        if self.before is not None:
            statement = cast("StatementTypeT", statement.where(field < self.before))
        if self.after is not None:
            statement = cast("StatementTypeT", statement.where(field > self.after))
        return statement


@dataclass
class OnBeforeAfter(StatementFilter):
    """DateTime range filter with inclusive bounds.

    This filter creates date/time range conditions using <= and >= operators,
    including the boundary values.

    If either `on_or_before` or `on_or_after` is None, that boundary condition
    is not applied.

    See Also:
    ---------
        :class:`BeforeAfter` : Exclusive datetime range filtering

    """

    field_name: str
    """Name of the model attribute to filter on."""
    on_or_before: Optional[datetime.datetime]
    """Filter results where field is on or earlier than this value."""
    on_or_after: Optional[datetime.datetime]
    """Filter results where field is on or later than this value."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply inclusive datetime range conditions to statement.

        Parameters
        ----------
        statement : StatementTypeT
            The SQLAlchemy statement to modify
        model : type[ModelT]
            The SQLAlchemy model class

        Returns:
        --------
        StatementTypeT
            Modified statement with inclusive datetime range conditions
        """
        field = self._get_instrumented_attr(model, self.field_name)
        if self.on_or_before is not None:
            statement = cast("StatementTypeT", statement.where(field <= self.on_or_before))
        if self.on_or_after is not None:
            statement = cast("StatementTypeT", statement.where(field >= self.on_or_after))
        return statement


class InAnyFilter(StatementFilter, ABC):
    """Base class for filters using IN or ANY operators.

    This abstract class provides common functionality for filters that check
    membership in a collection using either the SQL IN operator or the ANY operator.
    """


@dataclass
class CollectionFilter(InAnyFilter, Generic[T]):
    """Data required to construct a WHERE ... IN (...) clause.

    This filter restricts records based on a field's presence in a collection of values.

    The filter supports both ``IN`` and ``ANY`` operators for collection membership testing.
    Use ``prefer_any=True`` in ``append_to_statement`` to use the ``ANY`` operator.
    """

    field_name: str
    """Name of the model attribute to filter on."""
    values: Union[Collection[T], None]
    """Values for the ``IN`` clause. If this is None, no filter is applied.
        An empty list will force an empty result set (WHERE 1=-1)"""

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> StatementTypeT:
        """Apply a WHERE ... IN or WHERE ... ANY (...) clause to the statement.

        Parameters
        ----------
        statement : StatementTypeT
            The SQLAlchemy statement to modify
        model : type[ModelT]
            The SQLAlchemy model class
        prefer_any : bool, optional
            If True, uses the SQLAlchemy :func:`any_` operator instead of
            :func:`in_` for the filter condition

        Returns:
        --------
        StatementTypeT
            Modified statement with the appropriate IN conditions
        """
        field = self._get_instrumented_attr(model, self.field_name)
        if self.values is None:
            return statement
        if not self.values:
            # Return empty result set by forcing a false condition
            return cast("StatementTypeT", statement.where(text("1=-1")))
        if prefer_any:
            return cast("StatementTypeT", statement.where(any_(self.values) == field))  # type: ignore[arg-type]
        return cast("StatementTypeT", statement.where(field.in_(self.values)))


@dataclass
class NotInCollectionFilter(InAnyFilter, Generic[T]):
    """Data required to construct a WHERE ... NOT IN (...) clause.

    This filter restricts records based on a field's absence in a collection of values.

    The filter supports both ``NOT IN`` and ``!= ANY`` operators for collection exclusion.
    Use ``prefer_any=True`` in ``append_to_statement`` to use the ``ANY`` operator.

    Parameters
    ----------
    field_name : str
        Name of the model attribute to filter on
    values : abc.Collection[T] | None
        Values for the ``NOT IN`` clause. If this is None or empty,
        the filter is not applied.

    """

    field_name: str
    """Name of the model attribute to filter on."""
    values: Union[Collection[T], None]
    """Values for the ``NOT IN`` clause. If None or empty, no filter is applied."""

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> StatementTypeT:
        """Apply a WHERE ... NOT IN or WHERE ... != ANY(...) clause to the statement.

        Parameters
        ----------
        statement : StatementTypeT
            The SQLAlchemy statement to modify
        model : type[ModelT]
            The SQLAlchemy model class
        prefer_any : bool, optional
            If True, uses the SQLAlchemy :func:`any_` operator instead of
            :func:`notin_` for the filter condition

        Returns:
        --------
        StatementTypeT
            Modified statement with the appropriate NOT IN conditions
        """
        field = self._get_instrumented_attr(model, self.field_name)
        if not self.values:
            # If None or empty, we do not modify the statement
            return statement
        if prefer_any:
            return cast("StatementTypeT", statement.where(any_(self.values) != field))  # type: ignore[arg-type]
        return cast("StatementTypeT", statement.where(field.notin_(self.values)))


class PaginationFilter(StatementFilter, ABC):
    """Abstract base class for pagination filters.

    Subclasses should implement pagination logic, such as limit/offset or
    cursor-based pagination.
    """


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
            return statement.limit(self.limit).offset(self.offset)
        return statement


@dataclass
class OrderBy(StatementFilter):
    """Order by a specific field.

    Appends an ORDER BY clause to SELECT statements, sorting records by the
    specified field in ascending or descending order.

    Note:
        This filter only modifies SELECT statements. For other statement types,
        the statement is returned unchanged.

    See Also:
        - :meth:`sqlalchemy.sql.expression.Select.order_by`: SQLAlchemy ORDER BY clause
        - :meth:`sqlalchemy.sql.expression.ColumnElement.asc`: Ascending order
        - :meth:`sqlalchemy.sql.expression.ColumnElement.desc`: Descending order
    """

    field_name: str
    """Name of the model attribute to sort on."""
    sort_order: Literal["asc", "desc"] = "asc"
    """Sort direction ("asc" or "desc")."""

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
        if not isinstance(statement, Select):
            return statement
        field = self._get_instrumented_attr(model, self.field_name)
        if self.sort_order == "desc":
            return statement.order_by(field.desc())
        return statement.order_by(field.asc())


@dataclass
class SearchFilter(StatementFilter):
    """Case-sensitive or case-insensitive substring matching filter.

    Implements text search using SQL LIKE or ILIKE operators. Can search across
    multiple fields using OR conditions.

    Note:
        The search pattern automatically adds wildcards before and after the search
        value, equivalent to SQL pattern '%value%'.

    See Also:
        - :class:`.NotInSearchFilter`: Opposite filter using NOT LIKE/ILIKE
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.like`: Case-sensitive LIKE
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.ilike`: Case-insensitive LIKE
    """

    field_name: Union[str, set[str]]
    """Name or set of names of model attributes to search on."""
    value: str
    """Text to match within the field(s)."""
    ignore_case: Optional[bool] = False
    """Whether to use case-insensitive matching."""

    @property
    def _operator(self) -> Callable[..., ColumnElement[bool]]:
        """Return the SQL operator for combining multiple search clauses.

        Returns:
            Callable[..., ColumnElement[bool]]: The `or_` operator for OR conditions

        See Also:
            :func:`sqlalchemy.sql.expression.or_`: SQLAlchemy OR operator
        """
        return or_

    @property
    def _func(self) -> "attrgetter[Callable[[str], BinaryExpression[bool]]]":
        """Return the appropriate LIKE or ILIKE operator as a function.

        Returns:
            attrgetter: Bound method for LIKE or ILIKE operations

        See Also:
            - :meth:`sqlalchemy.sql.expression.ColumnOperators.like`: LIKE operator
            - :meth:`sqlalchemy.sql.expression.ColumnOperators.ilike`: ILIKE operator
        """
        return attrgetter("ilike" if self.ignore_case else "like")

    @property
    def normalized_field_names(self) -> set[str]:
        """Convert field_name to a set if it's a single string.

        Returns:
            set[str]: Set of field names to be searched
        """
        return {self.field_name} if isinstance(self.field_name, str) else self.field_name

    def get_search_clauses(self, model: type[ModelT]) -> list[BinaryExpression[bool]]:
        """Generate the LIKE/ILIKE clauses for all specified fields.

        Args:
            model: The SQLAlchemy model class

        Returns:
            list[BinaryExpression[bool]]: List of text matching expressions

        See Also:
            :class:`sqlalchemy.sql.expression.BinaryExpression`: SQLAlchemy expression
        """
        search_clause: list[BinaryExpression[bool]] = []
        for field_name in self.normalized_field_names:
            try:
                field = self._get_instrumented_attr(model, field_name)
                search_text = f"%{self.value}%"
                search_clause.append(self._func(field)(search_text))
            except AttributeError:
                msg = f"Skipping search for field {field_name}.  It is not found in model {model.__name__}"
                logger.debug(msg)
                continue
        return search_clause

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Append a LIKE/ILIKE clause to the statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with text search clauses

        See Also:
            :meth:`sqlalchemy.sql.expression.Select.where`: SQLAlchemy WHERE clause
        """
        where_clause = self._operator(*self.get_search_clauses(model))
        return cast("StatementTypeT", statement.where(where_clause))


# Regular typed dictionary for operators_map
operators_map: dict[str, Callable[[Any, Any], ColumnElement[bool]]] = {
    "eq": op.eq,
    "ne": op.ne,
    "gt": op.gt,
    "ge": op.ge,
    "lt": op.lt,
    "le": op.le,
    "in": op.in_op,
    "notin": op.notin_op,
    "between": lambda c, v: c.between(v[0], v[1]),
    "like": op.like_op,
    "ilike": op.ilike_op,
    "startswith": op.startswith_op,
    "istartswith": lambda c, v: c.ilike(v + "%"),
    "endswith": op.endswith_op,
    "iendswith": lambda c, v: c.ilike(v + "%"),
    "dateeq": lambda c, v: cast("Date", c) == v,
}

VALID_OPERATORS = set(operators_map.keys())
"""Set of valid operators that can be used in ComparisonFilter."""


@dataclass
class ComparisonFilter(StatementFilter):
    """Simple comparison filter for equality and inequality operations.

    This filter applies basic comparison operators (=, !=, >, >=, <, <=) to a field.
    It provides a generic way to perform common comparison operations.

    Args:
        field_name: Name of the model attribute to filter on
        operator: Comparison operator to use (must be one of: 'eq', 'ne', 'gt', 'ge', 'lt', 'le', 'in', 'notin', 'between', 'like', 'ilike', 'startswith', 'istartswith', 'endswith', 'iendswith', 'dateeq')
        value: Value to compare against

    Raises:
        ValueError: If an invalid operator is provided
    """

    field_name: str
    """Name of the model attribute to filter on."""
    operator: str
    """Comparison operator to use (one of 'eq', 'ne', 'gt', 'ge', 'lt', 'le')."""
    value: Any
    """Value to compare against."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply a comparison operation to the statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with the comparison condition

        Raises:
            ValueError: If an invalid operator is provided
        """
        field = self._get_instrumented_attr(model, self.field_name)
        operator_func = operators_map.get(self.operator)

        if operator_func is None:
            msg = f"Invalid operator '{self.operator}'. Must be one of: {', '.join(sorted(VALID_OPERATORS))}"
            raise ValueError(msg)

        condition = operator_func(field, self.value)
        return cast("StatementTypeT", statement.where(condition))


@dataclass
class NotInSearchFilter(SearchFilter):
    """Filter for excluding records that match a substring.

    Implements negative text search using SQL NOT LIKE or NOT ILIKE operators.
    Can exclude across multiple fields using AND conditions.

    Args:
        field_name: Name or set of names of model attributes to search on
        value: Text to exclude from the field(s)
        ignore_case: If True, uses NOT ILIKE for case-insensitive matching

    Note:
        Uses AND for multiple fields, meaning records matching any field will be excluded.

    See Also:
        - :class:`.SearchFilter`: Opposite filter using LIKE/ILIKE
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.notlike`: NOT LIKE operator
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.notilike`: NOT ILIKE operator
    """

    @property
    def _operator(self) -> Callable[..., ColumnElement[bool]]:
        """Return the SQL operator for combining multiple negated search clauses.

        Returns:
            Callable[..., ColumnElement[bool]]: The `and_` operator for AND conditions

        See Also:
            :func:`sqlalchemy.sql.expression.and_`: SQLAlchemy AND operator
        """
        return and_

    @property
    def _func(self) -> "attrgetter[Callable[[str], BinaryExpression[bool]]]":
        """Return the appropriate NOT LIKE or NOT ILIKE operator as a function.

        Returns:
            attrgetter: Bound method for NOT LIKE or NOT ILIKE operations

        See Also:
            - :meth:`sqlalchemy.sql.expression.ColumnOperators.notlike`: NOT LIKE
            - :meth:`sqlalchemy.sql.expression.ColumnOperators.notilike`: NOT ILIKE
        """
        return attrgetter("not_ilike" if self.ignore_case else "not_like")


@dataclass
class ExistsFilter(StatementFilter):
    """Filter for EXISTS subqueries.

    This filter creates an EXISTS condition using a list of column expressions.
    The expressions can be combined using either AND or OR logic. The filter applies
    a correlated subquery that returns only the rows from the main query that match
    the specified conditions.

    For example, if searching movies with `Movie.genre == "Action"`, only rows where
    the genre is "Action" will be returned.

    Parameters
    ----------
    values : list[ColumnElement[bool]]
        values: List of SQLAlchemy column expressions to use in the EXISTS clause
    operator : Literal["and", "or"], optional
        operator: If "and", combines conditions with AND, otherwise uses OR. Defaults to "and".

    Example:
    --------
        Basic usage with AND conditions::

            from sqlalchemy import select
            from advanced_alchemy.filters import ExistsFilter

            filter = ExistsFilter(
                values=[User.email.like("%@example.com%")],
            )
            statement = filter.append_to_statement(
                select(Organization), Organization
            )

        This will return only organizations where the user's email contains "@example.com".

        Using OR conditions::

            filter = ExistsFilter(
                values=[User.role == "admin", User.role == "owner"],
                operator="or",
            )

        This will return organizations where the user's role is either "admin" OR "owner".

    See Also:
    --------
        :class:`NotExistsFilter`: The inverse of this filter
        :func:`sqlalchemy.sql.expression.exists`: SQLAlchemy EXISTS expression
    """

    values: list[ColumnElement[bool]]
    """List of SQLAlchemy column expressions to use in the EXISTS clause."""
    operator: Literal["and", "or"] = "and"
    """If "and", combines conditions with the AND operator, otherwise uses OR."""

    @property
    def _and(self) -> Callable[..., ColumnElement[bool]]:
        """Access the SQLAlchemy `and_` operator.

        Returns:
            Callable[..., ColumnElement[bool]]: The `and_` operator for AND conditions

        See Also:
            :func:`sqlalchemy.sql.expression.and_`: SQLAlchemy AND operator
        """
        return and_

    @property
    def _or(self) -> Callable[..., ColumnElement[bool]]:
        """Access the SQLAlchemy `or_` operator.

        Returns:
            Callable[..., ColumnElement[bool]]: The `or_` operator for OR conditions

        See Also:
            :func:`sqlalchemy.sql.expression.or_`: SQLAlchemy OR operator
        """
        return or_

    def _get_combined_conditions(self) -> ColumnElement[bool]:
        """Combine the filter conditions using the specified operator.

        Returns:
            ColumnElement[bool]:
                A SQLAlchemy column expression combining all conditions with AND or OR
        """
        op = self._and if self.operator == "and" else self._or
        return op(*self.values)

    def get_exists_clause(self, model: type[ModelT]) -> ColumnElement[bool]:
        """Generate the EXISTS clause for the statement.

        Args:
            model : type[ModelT]
                The SQLAlchemy model class to correlate with

        Returns:
            ColumnElement[bool]:
                A correlated EXISTS expression for use in a WHERE clause
        """
        # Handle empty values list case
        if not self.values:
            # Use explicitly imported 'false' from sqlalchemy
            # Return SQLAlchemy FALSE expression
            return false()

        # Combine all values with AND or OR (using the operator specified in the filter)
        # This creates a single boolean expression from multiple conditions
        combined_conditions = self._get_combined_conditions()

        # Create a correlated subquery with the combined conditions
        try:
            subquery = select(1).where(combined_conditions)
            correlated_subquery = subquery.correlate(model.__table__)
            return exists(correlated_subquery)
        except Exception:  # noqa: BLE001
            return false()

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Append EXISTS condition to the statement.

        Args:
            statement : StatementTypeT
                The SQLAlchemy statement to modify
            model : type[ModelT]
            The SQLAlchemy model class

        Returns:
            StatementTypeT:
                Modified statement with EXISTS condition
        """
        # We apply the exists clause regardless of whether self.values is empty,
        # as get_exists_clause handles the empty case by returning false().
        exists_clause = self.get_exists_clause(model)
        return cast("StatementTypeT", statement.where(exists_clause))


@dataclass
class NotExistsFilter(StatementFilter):
    """Filter for NOT EXISTS subqueries.

    This filter creates a NOT EXISTS condition using a list of column expressions.
    The expressions can be combined using either AND or OR logic. The filter applies
    a correlated subquery that returns only the rows from the main query that DO NOT
    match the specified conditions.

    For example, if searching movies with `Movie.genre == "Action"`, only rows where
    the genre is NOT "Action" will be returned.

    Parameters
    ----------
    values : list[ColumnElement[bool]]
        values: List of SQLAlchemy column expressions to use in the NOT EXISTS clause
    operator : Literal["and", "or"], optional
        operator: If "and", combines conditions with AND, otherwise uses OR. Defaults to "and".

    Example:
    --------
        Basic usage with AND conditions::

            from sqlalchemy import select
            from advanced_alchemy.filters import NotExistsFilter

            filter = NotExistsFilter(
                values=[User.email.like("%@example.com%")],
            )
            statement = filter.append_to_statement(
                select(Organization), Organization
            )

        This will return only organizations where the user's email does NOT contain "@example.com".

        Using OR conditions::

            filter = NotExistsFilter(
                values=[User.role == "admin", User.role == "owner"],
                operator="or",
            )

        This will return organizations where the user's role is NEITHER "admin" NOR "owner".

    See Also:
    --------
        :class:`ExistsFilter`: The inverse of this filter
        :func:`sqlalchemy.sql.expression.not_`: SQLAlchemy NOT operator
        :func:`sqlalchemy.sql.expression.exists`: SQLAlchemy EXISTS expression
    """

    values: list[ColumnElement[bool]]
    """List of SQLAlchemy column expressions to use in the NOT EXISTS clause."""
    operator: Literal["and", "or"] = "and"
    """If "and", combines conditions with the AND operator, otherwise uses OR."""

    @property
    def _and(self) -> Callable[..., ColumnElement[bool]]:
        """Access the SQLAlchemy `and_` operator.

        Returns:
            Callable[..., ColumnElement[bool]]: The `and_` operator for AND conditions

        See Also:
            :func:`sqlalchemy.sql.expression.and_`: SQLAlchemy AND operator
        """
        return and_

    @property
    def _or(self) -> Callable[..., ColumnElement[bool]]:
        """Access the SQLAlchemy `or_` operator.

        Returns:
            Callable[..., ColumnElement[bool]]: The `or_` operator for OR conditions

        See Also:
            :func:`sqlalchemy.sql.expression.or_`: SQLAlchemy OR operator
        """
        return or_

    def _get_combined_conditions(self) -> ColumnElement[bool]:
        op = self._and if self.operator == "and" else self._or
        return op(*self.values)

    def get_exists_clause(self, model: type[ModelT]) -> ColumnElement[bool]:
        """Generate the NOT EXISTS clause for the statement.

        Args:
            model : type[ModelT]
                The SQLAlchemy model class to correlate with


        Returns:
            ColumnElement[bool]:
                A correlated NOT EXISTS expression for use in a WHERE clause
        """
        # Handle empty values list case
        if not self.values:
            # Return SQLAlchemy TRUE expression
            return true()

        # Combine conditions and create correlated subquery
        combined_conditions = self._get_combined_conditions()
        subquery = select(1).where(combined_conditions)
        correlated_subquery = subquery.correlate(model.__table__)
        return not_(exists(correlated_subquery))

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Append NOT EXISTS condition to the statement.

        Args:
            statement : StatementTypeT
                The SQLAlchemy statement to modify
            model : type[ModelT]
                The SQLAlchemy model class

        Returns:
            StatementTypeT:
                Modified statement with NOT EXISTS condition
        """
        # We apply the exists clause regardless of whether self.values is empty,
        # as get_exists_clause handles the empty case by returning true.
        exists_clause = self.get_exists_clause(model)
        return cast("StatementTypeT", statement.where(exists_clause))


@dataclass
class FilterGroup(StatementFilter):
    """A group of filters combined with a logical operator.

    This class combines multiple filters with a logical operator (AND/OR).
    It provides a way to create complex nested filter conditions.
    """

    logical_operator: Callable[..., ColumnElement[bool]]
    """Logical operator to combine the filters."""
    filters: list[StatementFilter]
    """List of filters to combine."""

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
    ) -> "StatementTypeT":
        """Apply all filters combined with the logical operator.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with combined filters
        """
        if not self.filters:
            return statement

        # Create a list of expressions from each filter
        expressions = []
        for filter_obj in self.filters:
            # Each filter needs to be applied to a clean version of the statement
            # to get just its expression
            filter_statement = filter_obj.append_to_statement(select(), model)
            # Extract the whereclause from the filter's statement
            if hasattr(filter_statement, "whereclause") and filter_statement.whereclause is not None:
                expressions.append(filter_statement.whereclause)  # pyright: ignore

        if expressions:
            # Combine all expressions with the logical operator
            combined = self.logical_operator(*expressions)
            return cast("StatementTypeT", statement.where(combined))
        return statement


@dataclass
class MultiFilter(StatementFilter):
    """Apply multiple filters to a query based on a JSON/dict input.

    This filter provides a way to construct complex filter trees from
    a structured dictionary input, supporting nested logical groups and
    various filter types.
    """

    filters: dict[str, Any]
    """JSON/dict structure representing the filters."""

    # TypedDict class variables
    _filter_map: ClassVar[FilterMap] = {
        "before_after": BeforeAfter,
        "on_before_after": OnBeforeAfter,
        "collection": CollectionFilter,
        "not_in_collection": NotInCollectionFilter,
        "limit_offset": LimitOffset,
        "order_by": OrderBy,
        "search": SearchFilter,
        "not_in_search": NotInSearchFilter,
        "filter_group": FilterGroup,
        "comparison": ComparisonFilter,
        "exists": ExistsFilter,
        "not_exists": NotExistsFilter,
    }

    _logical_map: ClassVar[LogicalOperatorMap] = {
        "and_": and_,
        "or_": or_,
    }

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
    ) -> StatementTypeT:
        """Apply the filters to the statement based on the filter definitions.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with all filters applied
        """
        for filter_type, conditions in self.filters.items():
            operator = self._logical_map.get(filter_type)
            if operator and isinstance(conditions, list):
                # Create filters from the conditions
                valid_filters = []
                for cond in conditions:  # pyright: ignore
                    filter_instance = self._create_filter(cond)  # pyright: ignore
                    if filter_instance is not None:
                        valid_filters.append(filter_instance)  # pyright: ignore

                # Only create a filter group if we have valid filters
                if valid_filters:
                    filter_group = FilterGroup(
                        logical_operator=operator,  # type: ignore
                        filters=valid_filters,  # pyright: ignore
                    )
                    statement = filter_group.append_to_statement(statement, model)
        return statement

    def _create_filter(self, condition: dict[str, Any]) -> Optional[StatementFilter]:
        """Create a filter instance from a condition dictionary.

        Args:
            condition: Dictionary defining a filter

        Returns:
            Optional[StatementFilter]: Filter instance if successfully created, None otherwise
        """
        # Check if condition is a nested logical group
        logical_keys = set(self._logical_map.keys())
        intersect = logical_keys.intersection(condition.keys())
        if intersect:
            # It's a nested filter group
            for key in intersect:
                operator = self._logical_map.get(key)
                if operator and isinstance(condition.get(key), list):
                    nested_filters = []
                    for cond in condition[key]:
                        filter_instance = self._create_filter(cond)
                        if filter_instance is not None:
                            nested_filters.append(filter_instance)  # pyright: ignore

                    if nested_filters:
                        return FilterGroup(logical_operator=operator, filters=nested_filters)  # type: ignore
        else:
            # Regular filter
            filter_type = condition.get("type")
            if filter_type is not None and isinstance(filter_type, str):
                filter_class = self._filter_map.get(filter_type)
                if filter_class is not None:
                    try:
                        # Create a copy of the condition without the type key
                        filter_args = {k: v for k, v in condition.items() if k != "type"}
                        return filter_class(**filter_args)  # type: ignore
                    except Exception:  # noqa: BLE001
                        return None
        return None


# Define FilterTypes using direct class references
FilterTypes: TypeAlias = Union[
    BeforeAfter,
    OnBeforeAfter,
    CollectionFilter[Any],
    LimitOffset,
    OrderBy,
    SearchFilter,
    NotInCollectionFilter[Any],
    NotInSearchFilter,
    ExistsFilter,
    NotExistsFilter,
    ComparisonFilter,
    MultiFilter,
    FilterGroup,
]
"""Aggregate type alias of the types supported for collection filtering."""

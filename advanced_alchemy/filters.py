"""SQLAlchemy filter constructs for advanced query operations.

This module provides a comprehensive collection of filter datastructures designed to
enhance SQLAlchemy query construction. It implements type-safe, reusable filter patterns
for common database query operations.

Features:
    Type-safe filter construction, datetime range filtering, collection-based filtering,
    pagination support, search operations, and customizable ordering.

Example:
    Basic usage with a datetime filter::

        import datetime
        from advanced_alchemy.filters import BeforeAfter

        filter = BeforeAfter(
            field_name="created_at",
            before=datetime.datetime.now(),
            after=datetime.datetime(2023, 1, 1),
        )
        statement = filter.append_to_statement(select(Model), Model)

Note:
    All filter classes implement the :class:`StatementFilter` ABC, ensuring consistent
    interface across different filter types.

See Also:
    - :class:`sqlalchemy.sql.expression.Select`: Core SQLAlchemy select expression
    - :class:`sqlalchemy.orm.Query`: SQLAlchemy ORM query interface
    - :mod:`advanced_alchemy.base`: Base model definitions

"""

import datetime
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
    "AGGridFilter",
    "BeforeAfter",
    "CollectionFilter",
    "ExistsFilter",
    "FilterGroup",
    "FilterTypes",
    "InAnyFilter",
    "LimitOffset",
    "MultiFilter",
    "NotExistsFilter",
    "NotInCollectionFilter",
    "NotInSearchFilter",
    "OnBeforeAfter",
    "OrderBy",
    "PaginationFilter",
    "SearchFilter",
    "SimpleFilter",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
    "TanStackFilter",
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
FilterTypes: TypeAlias = "Union[BeforeAfter, OnBeforeAfter, CollectionFilter[Any], LimitOffset, OrderBy, SearchFilter, NotInCollectionFilter[Any], NotInSearchFilter, ExistsFilter, NotExistsFilter]"
"""Aggregate type alias of the types supported for collection filtering."""


# Define TypedDicts for filter and logical maps
class FilterMapDict(TypedDict):
    before_after: "type[BeforeAfter]"
    on_before_after: "type[OnBeforeAfter]"
    collection: "type[CollectionFilter[Any]]"
    not_in_collection: "type[NotInCollectionFilter[Any]]"
    limit_offset: "type[LimitOffset]"
    order_by: "type[OrderBy]"
    search: "type[SearchFilter]"
    not_in_search: "type[NotInSearchFilter]"
    filter_group: "type[FilterGroup]"  # For nested filter groups
    simple_filter: "type[SimpleFilter]"  # For basic comparison operations


class LogicalMapDict(TypedDict):
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
            return cast("StatementTypeT", statement.limit(self.limit).offset(self.offset))
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
            return cast("StatementTypeT", statement.order_by(field.desc()))
        return cast("StatementTypeT", statement.order_by(field.asc()))


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
            field = self._get_instrumented_attr(model, field_name)
            search_text = f"%{self.value}%"
            search_clause.append(self._func(field)(search_text))
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


@dataclass
class SimpleFilter(StatementFilter):
    """Simple comparison filter for equality and inequality operations.

    This filter applies basic comparison operators (=, !=, >, >=, <, <=) to a field.
    It provides a generic way to perform common comparison operations.

    Attributes:
    ----------~
    field_name : str
        Name of the model attribute to filter on
    operator : str
        Comparison operator to use ('eq', 'ne', 'gt', 'ge', 'lt', 'le')
    value : Any
        Value to compare against

    Examples:
    --------~
    >>> filter = SimpleFilter(
    ...     field_name="age", operator="gt", value=18
    ... )
    >>> statement = filter.append_to_statement(select(User), User)
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
        """
        field = self._get_instrumented_attr(model, self.field_name)
        operator_func = operators_map.get(self.operator)

        if operator_func is None:
            return statement

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

    Attributes:
    ----------~
    logical_operator : Callable[..., ColumnElement[bool]]
        The SQLAlchemy operator to combine filters with (and_, or_)
    filters : list[StatementFilter]
        List of filters to apply
    """

    logical_operator: Callable[..., ColumnElement[bool]]
    """Logical operator to combine the filters (e.g., and_, or_)."""
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


@dataclass
class MultiFilter(StatementFilter):
    """Apply multiple filters to a query based on a JSON/dict input.

    This filter provides a way to construct complex filter trees from
    a structured dictionary input, supporting nested logical groups and
    various filter types.

    Attributes:
    ----------~
    filters : dict[str, Any]
        Dictionary structure representing the filters, where keys can be
        logical operators ("and_", "or_") and values are lists of filter
        definitions.
    """

    filters: dict[str, Any]
    """JSON/dict structure representing the filters."""

    # TypedDict class variables
    _filter_map: ClassVar[FilterMapDict] = {
        "before_after": BeforeAfter,
        "on_before_after": OnBeforeAfter,
        "collection": CollectionFilter,
        "not_in_collection": NotInCollectionFilter,
        "limit_offset": LimitOffset,
        "order_by": OrderBy,
        "search": SearchFilter,
        "not_in_search": NotInSearchFilter,
        "filter_group": FilterGroup,
        "simple_filter": SimpleFilter,
    }

    _logical_map: ClassVar[LogicalMapDict] = {
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


@dataclass
class TanStackFilter:
    """Adapter to convert TanStack Tables filter input into MultiFilter-compatible format.

    TanStack Tables is a popular React framework for building data tables.
    This adapter converts TanStack's filter format to MultiFilter's format.

    Attributes:
    ----------~
    tanstack_filters : list[dict[str, Any]]
        List of filter objects from TanStack Tables
    """

    tanstack_filters: list[dict[str, Any]]

    def to_multifilter_format(self) -> dict[str, Any]:
        """Convert TanStack filter list to MultiFilter dict.

        Returns:
            dict[str, Any]: Filter structure compatible with MultiFilter
        """

        def parse_filters(filters: list[dict[str, Any]], logical_op: str = "and_") -> dict[str, Any]:
            result = []
            for f in filters:
                parsed = self._parse_single_filter(f)
                if parsed is not None:
                    result.append(parsed)  # pyright: ignore
            return {logical_op: result} if result else {}

        return parse_filters(self.tanstack_filters)

    def _parse_single_filter(self, filter_obj: dict[str, Any]) -> Optional[dict[str, Any]]:  # noqa: PLR0911
        """Parse a single TanStack filter object.

        Args:
            filter_obj: TanStack filter object

        Returns:
            Optional[dict[str, Any]]: Parsed filter in MultiFilter format, or None if invalid
        """
        # Handle nested logical filters
        if "logical" in filter_obj and "filters" in filter_obj:
            logical_op = filter_obj.get("logical")
            filters = filter_obj.get("filters")
            if isinstance(logical_op, str) and isinstance(filters, list):
                result = []
                for f in filters:  # pyright: ignore
                    parsed = self._parse_single_filter(f)  # pyright: ignore
                    if parsed is not None:
                        result.append(parsed)  # pyright: ignore
                return {logical_op: result} if result else None
            return None

        # Handle single filter condition
        field = filter_obj.get("field")
        operator = filter_obj.get("operator")
        value = filter_obj.get("value")

        if not isinstance(field, str) or not isinstance(operator, str):
            return None

        # Map TanStack operators to filter types and operators
        operator_mapping = {
            "contains": "like",
            "notContains": "not_like",
            "equals": "eq",
            "notEqual": "ne",
            "greaterThan": "gt",
            "greaterThanOrEqual": "ge",
            "lessThan": "lt",
            "lessThanOrEqual": "le",
            "inNumberRange": "between",
            "in": "in",
            "notIn": "notin",
            "startsWith": "startswith",
            "endsWith": "endswith",
        }

        mapped_operator = operator_mapping.get(operator)
        if mapped_operator is None:
            return None

        # Determine filter type based on operator
        if mapped_operator in {"eq", "ne", "gt", "ge", "lt", "le"}:
            # Handle datetime filters separately
            if "before" in filter_obj or "after" in filter_obj:
                return {
                    "type": "before_after",
                    "field_name": field,
                    "before": filter_obj.get("before"),
                    "after": filter_obj.get("after"),
                }
            # Handle on_before/on_after
            if "on_or_before" in filter_obj or "on_or_after" in filter_obj:
                return {
                    "type": "on_before_after",
                    "field_name": field,
                    "on_or_before": filter_obj.get("on_or_before"),
                    "on_or_after": filter_obj.get("on_or_after"),
                }
            # Regular comparison operator
            return {
                "type": "simple_filter",
                "field_name": field,
                "operator": mapped_operator,
                "value": value,
            }
        if mapped_operator == "between":
            return {
                "type": "between",
                "field_name": field,
                "value": value,  # Expecting a list like [min, max]
            }
        if mapped_operator in {"like", "not_like", "startswith", "endswith"}:
            return {
                "type": "search" if "not" not in mapped_operator else "not_in_search",
                "field_name": field,
                "value": value,
                "ignore_case": filter_obj.get("ignore_case", True),
            }
        if mapped_operator in {"in", "notin"}:
            return {
                "type": "collection" if mapped_operator == "in" else "not_in_collection",
                "field_name": field,
                "values": value,
            }
        return None


@dataclass
class AGGridFilter:
    """Adapter to convert AG Grid filter input into MultiFilter-compatible format.

    AG Grid is a feature-rich data grid for JavaScript applications.
    This adapter converts AG Grid's filter format to MultiFilter's format.

    Attributes:
    ----------~
    aggrid_filters : dict[str, dict[str, Any]]
        Dictionary of filter objects from AG Grid, keyed by field name
    """

    aggrid_filters: dict[str, dict[str, Any]]

    def to_multifilter_format(self) -> dict[str, Any]:  # noqa: C901
        """Convert AG Grid filter model to MultiFilter dict.

        Returns:
            dict[str, Any]: Filter structure compatible with MultiFilter
        """
        filters = []
        for field, condition in self.aggrid_filters.items():
            # Extract filter components - ignore filter_type that's not used
            operator = condition.get("type")
            value = condition.get("filter")

            if not isinstance(operator, str):
                continue

            # Map AG Grid operators to filter types and operators
            operator_mapping = {
                "equals": "eq",
                "notEqual": "ne",
                "contains": "like",
                "notContains": "not_like",
                "startsWith": "startswith",
                "endsWith": "endswith",
                "inRange": "between",
                "greaterThan": "gt",
                "greaterThanOrEqual": "ge",
                "lessThan": "lt",
                "lessThanOrEqual": "le",
                "blank": None,  # Special case for null/empty values
                "notBlank": None,  # Special case for non-null/non-empty values
            }

            mapped_operator = operator_mapping.get(operator)
            if mapped_operator is None:
                # Handle special cases
                if operator == "blank":
                    filters.append(  # pyright: ignore
                        {
                            "type": "search",
                            "field_name": field,
                            "value": "",
                            "ignore_case": True,
                        }
                    )
                elif operator == "notBlank":
                    filters.append(  # pyright: ignore
                        {
                            "type": "not_in_search",
                            "field_name": field,
                            "value": "",
                            "ignore_case": True,
                        }
                    )
                continue

            filter_conditions = {}
            if mapped_operator == "between":
                filter_to = condition.get("filterTo")
                if value is not None and filter_to is not None:
                    filter_conditions = {
                        "type": "on_before_after",
                        "field_name": field,
                        "on_or_after": value,
                        "on_or_before": filter_to,
                    }
            elif mapped_operator in {"like", "not_like", "startswith", "endswith"}:
                if value is not None:
                    filter_conditions = {
                        "type": "search" if "not" not in mapped_operator else "not_in_search",
                        "field_name": field,
                        "value": value,
                        "ignore_case": condition.get("caseSensitive", False) is False,
                    }
            # Regular comparison operators
            elif value is not None:
                # Set the appropriate before/after fields for comparison operators
                if mapped_operator == "gt":
                    filter_conditions = {
                        "type": "before_after",
                        "field_name": field,
                        "after": value,
                        "before": None,
                    }
                elif mapped_operator == "ge":
                    filter_conditions = {
                        "type": "on_before_after",
                        "field_name": field,
                        "on_or_after": value,
                        "on_or_before": None,
                    }
                elif mapped_operator == "lt":
                    filter_conditions = {
                        "type": "before_after",
                        "field_name": field,
                        "before": value,
                        "after": None,
                    }
                elif mapped_operator == "le":
                    filter_conditions = {
                        "type": "on_before_after",
                        "field_name": field,
                        "on_or_before": value,
                        "on_or_after": None,
                    }
                else:
                    # For eq, ne operators
                    filter_conditions = {
                        "type": "simple_filter",
                        "field_name": field,
                        "operator": mapped_operator,
                        "value": value,
                    }

            if filter_conditions:
                filters.append(filter_conditions)  # pyright: ignore

        return {"and_": filters} if filters else {}

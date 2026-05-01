"""Column-level filters: comparisons, datetime ranges, IN, NULL, and friends."""

import datetime
from collections.abc import Collection
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Optional,
    Union,
    cast,
)

from sqlalchemy import (
    ColumnElement,
    Date,
    any_,
    text,
)
from sqlalchemy.sql import operators as op

from advanced_alchemy.filters._base import (
    InAnyFilter,
    ModelT,
    StatementFilter,
    StatementTypeT,
    T,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute

__all__ = (
    "VALID_OPERATORS",
    "BeforeAfter",
    "CollectionFilter",
    "ComparisonFilter",
    "NotInCollectionFilter",
    "NotNullFilter",
    "NullFilter",
    "OnBeforeAfter",
    "operators_map",
)


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

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""
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

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""
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


@dataclass
class CollectionFilter(InAnyFilter, Generic[T]):
    """Data required to construct a WHERE ... IN (...) clause.

    This filter restricts records based on a field's presence in a collection of values.

    The filter supports both ``IN`` and ``ANY`` operators for collection membership testing.
    Use ``prefer_any=True`` in ``append_to_statement`` to use the ``ANY`` operator.

    Enhanced to properly handle many-to-many relationships when used within MultiFilter
    or directly on relationship attributes.
    """

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""
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

        Enhanced to detect relationship attributes and delegate to RelationshipFilter
        for proper handling.

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
        # Lazy import to avoid a circular dep with ``_relationship``: the
        # relationship-handling path is only reached when ``field`` is a
        # relationship attribute, so we don't pay for the import on hot column
        # paths.
        from advanced_alchemy.filters._relationship import RelationshipFilter

        field = self._get_instrumented_attr(model, self.field_name)

        if self.values is None:
            return statement
        if not self.values:
            # Return empty result set by forcing a false condition
            return cast("StatementTypeT", statement.where(text("1=-1")))

        # Check if field is a relationship attribute and delegate to RelationshipFilter.
        #
        # This is primarily used to fix Issue #505 where many-to-many relationships
        # previously produced invalid SQL when used with MultiFilter.
        prop = getattr(field, "property", None)
        mapper = getattr(prop, "mapper", None)
        if mapper is not None:
            related_pk = list(mapper.primary_key)
            if len(related_pk) != 1:
                msg = (
                    "CollectionFilter does not support relationship filters against related models with composite "
                    f"primary keys (relationship={getattr(field, 'key', self.field_name)!r}). "
                    "Use RelationshipFilter with explicit filters instead."
                )
                raise ValueError(msg)

            relationship_attr = cast("InstrumentedAttribute[Any]", field)
            rel_filter = RelationshipFilter(
                relationship=relationship_attr,
                filters=[CollectionFilter(field_name=related_pk[0].key, values=self.values)],
            )
            return rel_filter.append_to_statement(statement, model)

        # Regular column - use existing logic
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

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""
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


@dataclass
class NullFilter(StatementFilter):
    """Filter for NULL values (IS NULL).

    This filter creates IS NULL conditions for database fields.
    Use this to find records where a field has no value.

    Example:
        Basic NULL filtering::

            from advanced_alchemy.filters import NullFilter

            # Find records where email_verified_at is NULL
            null_filter = NullFilter("email_verified_at")
            unverified = await repo.get_many(null_filter)

        With multiple filters::

            from advanced_alchemy.filters import (
                NullFilter,
                CollectionFilter,
            )

            # Find unverified users in specific roles
            filters = [
                NullFilter("email_verified_at"),
                CollectionFilter("role", ["admin", "moderator"]),
            ]
            results = await repo.get_many(*filters)

    See Also:
        - :class:`NotNullFilter`: Filter for NOT NULL values
        - :class:`CollectionFilter`: Filter by collection membership
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.is_`: IS NULL operator
    """

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply IS NULL condition to the statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with IS NULL condition applied
        """
        field = self._get_instrumented_attr(model, self.field_name)
        return cast("StatementTypeT", statement.where(field.is_(None)))


@dataclass
class NotNullFilter(StatementFilter):
    """Filter for NOT NULL values (IS NOT NULL).

    This filter creates IS NOT NULL conditions for database fields.
    Use this to find records where a field has a value.

    Example:
        Basic NOT NULL filtering::

            from advanced_alchemy.filters import NotNullFilter

            # Find records where email_verified_at is NOT NULL
            not_null_filter = NotNullFilter("email_verified_at")
            verified = await repo.get_many(not_null_filter)

        With multiple filters::

            from advanced_alchemy.filters import (
                NotNullFilter,
                CollectionFilter,
            )

            # Find verified users in specific roles
            filters = [
                NotNullFilter("email_verified_at"),
                CollectionFilter("role", ["admin", "moderator"]),
            ]
            results = await repo.get_many(*filters)

    See Also:
        - :class:`NullFilter`: Filter for NULL values
        - :class:`CollectionFilter`: Filter by collection membership
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.is_not`: IS NOT NULL operator
    """

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply IS NOT NULL condition to the statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with IS NOT NULL condition applied
        """
        field = self._get_instrumented_attr(model, self.field_name)
        return cast("StatementTypeT", statement.where(field.is_not(None)))


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
    "iendswith": lambda c, v: c.ilike("%" + v),
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

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""
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

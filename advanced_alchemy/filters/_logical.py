"""Logical-aggregator filters: EXISTS, NOT EXISTS, FilterGroup, MultiFilter."""

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    ClassVar,
    Literal,
    Optional,
    Union,
    cast,
)

from sqlalchemy import (
    ColumnElement,
    and_,
    exists,
    false,
    not_,
    or_,
    select,
    true,
)

from advanced_alchemy.filters._base import (
    FilterMap,
    LogicalOperatorMap,
    ModelT,
    StatementFilter,
    StatementTypeT,
)
from advanced_alchemy.filters._columns import (
    BeforeAfter,
    CollectionFilter,
    ComparisonFilter,
    NotInCollectionFilter,
    NotNullFilter,
    NullFilter,
    OnBeforeAfter,
)
from advanced_alchemy.filters._pagination import LimitOffset, OrderBy
from advanced_alchemy.filters._relationship import RelationshipFilter
from advanced_alchemy.filters._search import NotInSearchFilter, SearchFilter

__all__ = (
    "ExistsFilter",
    "FilterGroup",
    "MultiFilter",
    "NotExistsFilter",
)


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
        "null": NullFilter,
        "not_null": NotNullFilter,
        "order_by": OrderBy,
        "search": SearchFilter,
        "not_in_search": NotInSearchFilter,
        "filter_group": FilterGroup,
        "comparison": ComparisonFilter,
        "exists": ExistsFilter,
        "not_exists": NotExistsFilter,
        "relationship": RelationshipFilter,
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

    def _create_nested_filter_group(self, condition: dict[str, Any]) -> Optional[FilterGroup]:
        logical_keys = set(self._logical_map.keys())
        group_keys = logical_keys.intersection(condition.keys())
        for key in group_keys:
            operator = self._logical_map.get(key)
            nested_conditions = condition.get(key)
            if operator is None or not isinstance(nested_conditions, list):
                continue

            nested_filters: list[StatementFilter] = []
            for nested in cast("list[object]", nested_conditions):
                if isinstance(nested, dict):
                    nested_filter = self._create_filter(cast("dict[str, Any]", nested))
                    if nested_filter is not None:
                        nested_filters.append(nested_filter)

            if nested_filters:
                return FilterGroup(logical_operator=operator, filters=nested_filters)  # type: ignore[arg-type]
        return None

    def _create_relationship_filter(self, condition: dict[str, Any]) -> Optional[RelationshipFilter]:
        relationship = condition.get("relationship")
        nested_conditions = condition.get("filters", [])
        if not isinstance(relationship, str) or not isinstance(nested_conditions, list):
            return None

        nested_filters: list[Union[StatementFilter, ColumnElement[bool]]] = []
        for nested in cast("list[object]", nested_conditions):
            if isinstance(nested, dict):
                nested_filter = self._create_filter(cast("dict[str, Any]", nested))
                if nested_filter is not None:
                    nested_filters.append(nested_filter)

        return RelationshipFilter(
            relationship=relationship,
            filters=nested_filters,
            negate=bool(condition.get("negate", False)),
        )

    def _create_filter(self, condition: dict[str, Any]) -> Optional[StatementFilter]:
        """Create a filter instance from a condition dictionary."""
        nested_group = self._create_nested_filter_group(condition)
        if nested_group is not None:
            return nested_group

        filter_type = condition.get("type")
        if not isinstance(filter_type, str):
            return None

        if filter_type == "relationship":
            return self._create_relationship_filter(condition)

        filter_class = self._filter_map.get(filter_type)
        if filter_class is None:
            return None

        try:
            filter_args = {k: v for k, v in condition.items() if k != "type"}
            filter_cls = cast("type[StatementFilter]", filter_class)
            return filter_cls(**filter_args)
        except Exception:  # noqa: BLE001
            return None

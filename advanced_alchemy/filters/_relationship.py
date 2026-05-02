"""Relationship-aware filtering via correlated EXISTS subqueries."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Union,
    cast,
)

from sqlalchemy import (
    ColumnElement,
    Select,
    exists,
    not_,
    select,
)
from sqlalchemy.orm import class_mapper

from advanced_alchemy.filters._base import (
    ModelT,
    StatementFilter,
    StatementTypeT,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute, RelationshipProperty

__all__ = ("RelationshipFilter",)


@dataclass
class RelationshipFilter(StatementFilter):
    """Filter records based on related model fields.

    This filter creates an EXISTS subquery that applies filters to a related
    model, allowing efficient single-query filtering across relationships.

    Supports:
        - One-to-many relationships (Order.customer)
        - Many-to-one relationships (Customer.orders)
        - Many-to-many with secondary table (User.tags)
        - Many-to-many with association objects (Article.article_keywords)
        - Nested relationships (Order.customer.company)

    Performance:
        Uses correlated EXISTS subqueries for optimal query planning.
        Single database round-trip regardless of nesting depth.

    Examples:
        Filter orders by customer country::

            RelationshipFilter(
                relationship="customer",
                filters=[
                    CollectionFilter("country", ["USA", "Canada"])
                ],
            )

        Filter users by tag names (many-to-many)::

            RelationshipFilter(
                relationship="tags",
                filters=[
                    CollectionFilter("name", ["python", "sqlalchemy"])
                ],
            )

        Nested filtering (orders from enterprise customers in USA)::

            RelationshipFilter(
                relationship="customer",
                filters=[
                    CollectionFilter("country", ["USA"]),
                    RelationshipFilter(
                        relationship="tier",
                        filters=[
                            ComparisonFilter("name", "eq", "Enterprise")
                        ],
                    ),
                ],
            )

        Negative filtering (articles NOT in archived categories)::

            RelationshipFilter(
                relationship="category",
                filters=[ComparisonFilter("archived", "eq", True)],
                negate=True,
            )

    See Also:
        - :class:`ExistsFilter`: For custom correlated subqueries
        - :class:`CollectionFilter`: For IN/NOT IN filtering
        - :class:`FilterGroup`: For combining multiple filters
    """

    relationship: "Union[str, InstrumentedAttribute[Any]]"
    """Name of SQLAlchemy relationship attribute or the attribute itself."""

    filters: Sequence[Union[StatementFilter, ColumnElement[bool]]]
    """Filters to apply to the related model."""

    negate: bool = False
    """If True, uses NOT EXISTS instead of EXISTS."""

    def _get_relationship_name(self) -> str:
        """Extract relationship name from string or InstrumentedAttribute."""
        if isinstance(self.relationship, str):
            return self.relationship
        return self.relationship.key

    def _get_relationship_property(self, model: type[ModelT]) -> "RelationshipProperty[Any]":
        """Get RelationshipProperty from model mapper.

        Args:
            model: SQLAlchemy model class

        Returns:
            RelationshipProperty: SQLAlchemy relationship property

        Raises:
            ValueError: If relationship not found on model
        """
        mapper = class_mapper(model)
        rel_name = self._get_relationship_name()
        if rel_name not in mapper.relationships:
            msg = f"Relationship '{rel_name}' not found on model {model.__name__}"
            raise ValueError(msg)
        return mapper.relationships[rel_name]

    def _build_exists_subquery(
        self,
        model: type[ModelT],
        rel_prop: "RelationshipProperty[Any]",
    ) -> ColumnElement[bool]:
        """Build EXISTS subquery for relationship filtering.

        Args:
            model: Parent model class
            rel_prop: SQLAlchemy relationship property

        Returns:
            ColumnElement[bool]: EXISTS or NOT EXISTS clause
        """
        related_model = rel_prop.mapper.class_

        # Start with basic subquery and ensure required FROM elements are present.
        #
        # For many-to-many relationships, the subquery must include the secondary table,
        # otherwise the join conditions may reference columns that are not present in FROM.
        subquery = select(1)
        if rel_prop.secondary is not None:
            secondary_table = rel_prop.secondary
            secondaryjoin = rel_prop.secondaryjoin
            if secondaryjoin is None:
                msg = "Many-to-many relationship is missing required secondary join configuration."
                raise ValueError(msg)
            subquery = subquery.select_from(related_model).join(secondary_table, secondaryjoin)
        else:
            subquery = subquery.select_from(related_model)

        # Apply all filters to the related model
        for filter_ in self.filters:
            if isinstance(filter_, ColumnElement):
                subquery = subquery.where(filter_)
            else:
                subquery = filter_.append_to_statement(subquery, related_model)

        # Add join condition based on relationship type
        if rel_prop.secondary is not None:
            # Many-to-many with secondary table: correlation is expressed via primaryjoin.
            subquery = subquery.where(rel_prop.primaryjoin)
        else:
            # One-to-many or many-to-one
            subquery = self._add_o2m_join_condition(subquery, model, rel_prop)

        # Correlate with parent query
        parent_table = class_mapper(model).local_table
        subquery = subquery.correlate(parent_table)

        # Create EXISTS or NOT EXISTS
        exists_clause: ColumnElement[bool] = exists(subquery)
        if self.negate:
            exists_clause = not_(exists_clause)

        return exists_clause

    def _add_o2m_join_condition(
        self,
        subquery: Select[Any],
        model: type[ModelT],
        rel_prop: "RelationshipProperty[Any]",
    ) -> Select[Any]:
        """Add join condition for one-to-many or many-to-one relationship.

        Args:
            subquery: Subquery to modify
            model: Parent model class
            rel_prop: SQLAlchemy relationship property

        Returns:
            Select[Any]: Modified subquery with join condition
        """
        # Use the relationship's join condition directly
        join_condition = rel_prop.primaryjoin

        # The primaryjoin already contains the correlation references
        # which will be handled by correlate() in _build_exists_subquery
        return subquery.where(join_condition)

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
    ) -> StatementTypeT:
        """Apply relationship filter to statement.

        Args:
            statement: SQLAlchemy statement to modify
            model: Parent model class

        Returns:
            StatementTypeT: Modified statement with relationship filter applied

        Raises:
            ValueError: If relationship not found on model
        """
        rel_prop = self._get_relationship_property(model)
        exists_clause = self._build_exists_subquery(model, rel_prop)
        return cast("StatementTypeT", statement.where(exists_clause))

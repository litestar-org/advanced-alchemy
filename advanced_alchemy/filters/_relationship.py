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


@dataclass(init=False)
class RelationshipFilter(StatementFilter):
    """Filter records based on related model fields.

    This filter creates a correlated ``EXISTS`` subquery that applies filters to
    a related model in a single database round-trip across one-to-many,
    many-to-one, many-to-many, and nested relationships.

    Example:
        Filter orders by customer country or nested relationship::

            RelationshipFilter(
                relationship="customer",
                filters=[
                    CollectionFilter("country", ["USA", "Canada"]),
                    RelationshipFilter(
                        relationship="tier",
                        filters=[
                            ComparisonFilter("name", "eq", "Enterprise")
                        ],
                    ),
                ],
            )

    See Also:
        - :class:`ExistsFilter`: For custom correlated subqueries
        - :class:`CollectionFilter`: For IN/NOT IN filtering
        - :class:`FilterGroup`: For combining multiple filters
    """

    __slots__ = ("filters", "negate", "relationship")

    relationship: "Union[str, InstrumentedAttribute[Any]]"
    """Name of SQLAlchemy relationship attribute or the attribute itself."""

    filters: Sequence[Union[StatementFilter, ColumnElement[bool]]]
    """Filters to apply to the related model."""

    negate: bool
    """If True, uses NOT EXISTS instead of EXISTS."""

    def __init__(
        self,
        relationship: "Union[str, InstrumentedAttribute[Any]]",
        filters: Sequence[Union[StatementFilter, ColumnElement[bool]]],
        negate: bool = False,
    ) -> None:
        self.relationship = relationship
        self.filters = filters
        self.negate = negate

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

        for filter_ in self.filters:
            if isinstance(filter_, ColumnElement):
                subquery = subquery.where(filter_)
            else:
                subquery = filter_.append_to_statement(subquery, related_model)

        subquery = subquery.where(rel_prop.primaryjoin)

        parent_table = class_mapper(model).local_table
        subquery = subquery.correlate(parent_table)

        exists_clause: ColumnElement[bool] = exists(subquery)
        if self.negate:
            exists_clause = not_(exists_clause)

        return exists_clause

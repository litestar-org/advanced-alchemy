"""Text-search filters (LIKE / ILIKE / NOT LIKE / NOT ILIKE)."""

from dataclasses import dataclass
from operator import attrgetter
from typing import (
    Callable,
    Optional,
    Union,
    cast,
)

from sqlalchemy import (
    BinaryExpression,
    ColumnElement,
    and_,
    or_,
)

from advanced_alchemy.filters._base import (
    ModelT,
    StatementFilter,
    StatementTypeT,
    logger,
)

__all__ = ("NotInSearchFilter", "SearchFilter")


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
        search_clauses = self.get_search_clauses(model)
        if not search_clauses:
            return statement
        where_clause = self._operator(*search_clauses)
        return cast("StatementTypeT", statement.where(where_clause))


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

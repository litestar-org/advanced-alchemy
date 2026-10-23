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

__all__ = (
    "LIKE_ESCAPE_CHAR",
    "NotInSearchFilter",
    "SearchFilter",
    "escape_like_value",
)


LIKE_ESCAPE_CHAR = "/"
"""Escape character used when :class:`SearchFilter` escapes LIKE wildcards.

Not a backslash: SQLAlchemy renders one into the ``ESCAPE`` clause as ``'\\\\'``, which DuckDB reads
as two characters and rejects with "Escape string must be empty or one character". ``/`` needs no
such doubling on dialects that support an explicit ``ESCAPE`` clause.
"""


def escape_like_value(value: str, escape_char: str = LIKE_ESCAPE_CHAR) -> str:
    """Escape the LIKE wildcards ``%`` and ``_`` so they match literally.

    The escape character itself is escaped first, otherwise it would consume the
    escape characters added for the wildcards.

    Args:
        value: The raw search term.
        escape_char: The character to escape with.

    Returns:
        str: ``value`` with ``escape_char``, ``%`` and ``_`` escaped.
    """
    return value.replace(escape_char, escape_char * 2).replace("%", f"{escape_char}%").replace("_", f"{escape_char}_")


@dataclass(init=False)
class SearchFilter(StatementFilter):
    """Case-sensitive or case-insensitive substring matching filter.

    Implements text search using SQL LIKE or ILIKE operators. Can search across
    multiple fields using OR conditions.

    Note:
        The search pattern automatically adds wildcards before and after the search
        value, equivalent to SQL pattern '%value%'.

    Note:
        ``%`` and ``_`` in ``value`` remain SQL wildcards by default. Set
        ``escape_wildcards=True`` to match them literally on databases supporting
        the SQL ``ESCAPE`` clause. Spanner has no ``ESCAPE`` clause, so
        ``escape_wildcards`` must stay ``False`` there.

    See Also:
        - :class:`.NotInSearchFilter`: Opposite filter using NOT LIKE/ILIKE
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.like`: Case-sensitive LIKE
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.ilike`: Case-insensitive LIKE
    """

    __slots__ = ("escape_wildcards", "field_name", "ignore_case", "value")

    field_name: Union[str, set[str]]
    """Name or set of names of model attributes to search on."""
    value: str
    """Text to match within the field(s)."""
    ignore_case: Optional[bool]
    """Whether to use case-insensitive matching."""
    escape_wildcards: bool
    """Whether to treat ``%`` and ``_`` in :attr:`value` as literal characters."""

    def __init__(
        self,
        field_name: Union[str, set[str]],
        value: str,
        ignore_case: Optional[bool] = False,
        escape_wildcards: bool = False,
    ) -> None:
        self.field_name = field_name
        self.value = value
        self.ignore_case = ignore_case
        self.escape_wildcards = escape_wildcards

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
    def _func(self) -> "attrgetter[Callable[..., BinaryExpression[bool]]]":
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
        escape_char = LIKE_ESCAPE_CHAR if self.escape_wildcards else None
        value = escape_like_value(self.value) if self.escape_wildcards else self.value
        search_text = f"%{value}%"
        op_func = self._func
        for field_name in self.normalized_field_names:
            try:
                field = self._get_instrumented_attr(model, field_name)
                search_clause.append(op_func(field)(search_text, escape=escape_char))
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


@dataclass(init=False)
class NotInSearchFilter(SearchFilter):
    """Filter for excluding records that match a substring.

    Implements negative text search using SQL NOT LIKE or NOT ILIKE operators.
    Can exclude across multiple fields using AND conditions.

    Args:
        field_name: Name or set of names of model attributes to search on
        value: Text to exclude from the field(s)
        ignore_case: If True, uses NOT ILIKE for case-insensitive matching
        escape_wildcards: If True, matches wildcard characters literally using
            SQL ESCAPE. Defaults to False; not supported by Spanner when enabled.

    Note:
        Uses AND for multiple fields, meaning records matching any field will be excluded.

    See Also:
        - :class:`.SearchFilter`: Opposite filter using LIKE/ILIKE
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.notlike`: NOT LIKE operator
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.notilike`: NOT ILIKE operator
    """

    __slots__ = ()

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
    def _func(self) -> "attrgetter[Callable[..., BinaryExpression[bool]]]":
        """Return the appropriate NOT LIKE or NOT ILIKE operator as a function.

        Returns:
            attrgetter: Bound method for NOT LIKE or NOT ILIKE operations

        See Also:
            - :meth:`sqlalchemy.sql.expression.ColumnOperators.notlike`: NOT LIKE
            - :meth:`sqlalchemy.sql.expression.ColumnOperators.notilike`: NOT ILIKE
        """
        return attrgetter("not_ilike" if self.ignore_case else "not_like")

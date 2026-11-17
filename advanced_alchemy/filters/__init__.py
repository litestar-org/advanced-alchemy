"""SQLAlchemy statement filter constructs for repositories and services.

Provides :class:`StatementFilter` implementations for pagination (:class:`LimitOffsetFilter`),
ordering (:class:`OrderByFilter`), datetime ranges (:class:`BeforeAfterFilter`, :class:`OnBeforeAfterFilter`),
collection membership (:class:`InCollectionFilter`, :class:`NotInCollectionFilter`, :class:`ChoicesFilter`),
nullability (:class:`NullFilter`, :class:`NotNullFilter`), boolean and comparison checks
(:class:`BooleanFilter`, :class:`ComparisonFilter`), substring search (:class:`SearchFilter`,
:class:`NotInSearchFilter`), correlated subqueries (:class:`ExistsFilter`, :class:`NotExistsFilter`,
:class:`RelationshipFilter`), logical groups (:class:`AndGroup`, :class:`OrGroup`,
:class:`LogicalFilterGroup`), and structured JSON filter payloads (:class:`MultiFilter`).
"""

import datetime as dt
import logging
from abc import ABC
from collections.abc import Collection, Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from operator import attrgetter
from typing import (
    TYPE_CHECKING,
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
    Select,
    and_,
    any_,
    exists,
    false,
    inspect,
    not_,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql import operators as op
from typing_extensions import TypeAlias, TypedDict, TypeVar

from advanced_alchemy.filters._base import (
    FilterFieldName,
    InstrumentedField,
    ModelT,
    StatementFilter,
    StatementFilterT,
    StatementTypeT,
    ordering_term,
)
from advanced_alchemy.filters._cursor import register_cursor_type
from advanced_alchemy.filters._pagination import (
    CursorFilter,
    CursorKey,
    CursorKeys,
    LimitOffsetFilter,
    PaginationFilter,
    normalize_cursor_keys,
)
from advanced_alchemy.operations import validate_identifier

if TYPE_CHECKING:
    from sqlalchemy.orm import RelationshipProperty

    RelationshipHop: TypeAlias = Union[str, InstrumentedAttribute[Any]]
    RelationshipPath: TypeAlias = Union[RelationshipHop, Sequence[RelationshipHop]]
else:
    RelationshipHop: TypeAlias = Any
    RelationshipPath: TypeAlias = Any

__all__ = (
    "LIKE_ESCAPE_CHAR",
    "BeforeAfter",
    "BeforeAfterFilter",
    "BooleanFilter",
    "ChoicesFilter",
    "CollectionFilter",
    "ComparisonFilter",
    "CursorFilter",
    "CursorKey",
    "CursorKeys",
    "ExistsFilter",
    "FilterGroup",
    "FilterMap",
    "FilterSet",
    "FilterTypes",
    "InAnyFilter",
    "InCollectionFilter",
    "LimitOffset",
    "LimitOffsetFilter",
    "LogicalOperatorMap",
    "MultiFilter",
    "NotExistsFilter",
    "NotInCollectionFilter",
    "NotInSearchFilter",
    "NotNullFilter",
    "NullFilter",
    "OnBeforeAfter",
    "OnBeforeAfterFilter",
    "OrderBy",
    "OrderByFilter",
    "PaginationFilter",
    "RelationshipFilter",
    "SearchFilter",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
    "escape_like_value",
    "normalize_cursor_keys",
    "register_cursor_type",
)

T = TypeVar("T")

logger = logging.getLogger("advanced_alchemy")


class FilterMap(TypedDict):
    """Mapping of filter type keys to their corresponding filter classes."""

    before_after: "type[BeforeAfterFilter]"
    """Exclusive datetime range filter class."""
    on_before_after: "type[OnBeforeAfterFilter]"
    """Inclusive datetime range filter class."""
    boolean: "type[BooleanFilter]"
    """Boolean equality filter class."""
    choices: "type[ChoicesFilter[Any]]"
    """Fixed-choice membership filter class."""
    collection: "type[InCollectionFilter[Any]]"
    """Collection ``IN`` / ``ANY`` membership filter class."""
    not_in_collection: "type[NotInCollectionFilter[Any]]"
    """Collection ``NOT IN`` / ``!= ANY`` exclusion filter class."""
    limit_offset: "type[LimitOffsetFilter]"
    """Limit and offset pagination filter class."""
    null: "type[NullFilter]"
    """``IS NULL`` filter class."""
    not_null: "type[NotNullFilter]"
    """``IS NOT NULL`` filter class."""
    order_by: "type[OrderByFilter]"
    """Column ordering filter class."""
    search: "type[SearchFilter]"
    """Substring ``LIKE`` / ``ILIKE`` filter class."""
    not_in_search: "type[NotInSearchFilter]"
    """Negated substring ``NOT LIKE`` / ``NOT ILIKE`` filter class."""
    comparison: "type[ComparisonFilter]"
    """Binary comparison operator filter class."""
    exists: "type[ExistsFilter]"
    """Correlated ``EXISTS`` subquery filter class."""
    not_exists: "type[NotExistsFilter]"
    """Correlated ``NOT EXISTS`` subquery filter class."""
    filter_group: "type[FilterGroup]"
    """Logical ``AND`` / ``OR`` filter group class."""
    relationship: "type[RelationshipFilter]"
    """Correlated ``EXISTS`` / ``NOT EXISTS`` relationship filter class."""


class LogicalOperatorMap(TypedDict):
    """Mapping of logical operator keys to SQLAlchemy conjunction functions."""

    and_: Callable[..., ColumnElement[bool]]
    """SQLAlchemy ``and_`` conjunction callable."""
    or_: Callable[..., ColumnElement[bool]]
    """SQLAlchemy ``or_`` disjunction callable."""


@dataclass
class BeforeAfterFilter(StatementFilter):
    """DateTime range filter with exclusive bounds.

    This filter creates date/time range conditions using < and > operators,
    excluding the boundary values.

    If either `before` or `after` is None, that boundary condition is not applied.

    See Also:
        :class:`OnBeforeAfterFilter`: Inclusive datetime range filtering
    """

    field_name: FilterFieldName
    """Field name, model attribute, or func expression."""
    before: Optional[dt.datetime]
    """Filter results where field is earlier than this value."""
    after: Optional[dt.datetime]
    """Filter results where field is later than this value."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply datetime range conditions to statement.

        Args:
            statement: The SQLAlchemy statement to modify.
            model: The SQLAlchemy model class.

        Returns:
            StatementTypeT: Modified statement with datetime range conditions.
        """
        field = self._get_instrumented_attr(model, self.field_name)
        if self.before is not None:
            statement = cast("StatementTypeT", statement.where(field < self.before))
        if self.after is not None:
            statement = cast("StatementTypeT", statement.where(field > self.after))
        return statement


@dataclass
class OnBeforeAfterFilter(StatementFilter):
    """DateTime range filter with inclusive bounds.

    This filter creates date/time range conditions using <= and >= operators,
    including the boundary values.

    If either `on_or_before` or `on_or_after` is None, that boundary condition
    is not applied.

    See Also:
        :class:`BeforeAfterFilter`: Exclusive datetime range filtering
    """

    field_name: FilterFieldName
    """Field name, model attribute, or func expression."""
    on_or_before: Optional[dt.datetime]
    """Filter results where field is on or earlier than this value."""
    on_or_after: Optional[dt.datetime]
    """Filter results where field is on or later than this value."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply inclusive datetime range conditions to statement.

        Args:
            statement: The SQLAlchemy statement to modify.
            model: The SQLAlchemy model class.

        Returns:
            StatementTypeT: Modified statement with inclusive datetime range conditions.
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

    def _append_relationship_collection(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
        field: InstrumentedField,
        values: Collection[Any],
        *,
        negate: bool,
    ) -> Optional[StatementTypeT]:
        """Delegate collection membership on relationship attributes to :class:`RelationshipFilter`.

        Raises:
            ValueError: If the related model defines a composite primary key.
        """
        prop = getattr(field, "property", None)
        mapper = getattr(prop, "mapper", None)
        if mapper is None:
            return None
        related_pk = list(mapper.primary_key)
        if len(related_pk) != 1:
            msg = (
                f"{type(self).__name__} does not support relationship filters against related models with composite "
                f"primary keys (relationship={getattr(field, 'key', getattr(self, 'field_name', None))!r}). "
                "Use RelationshipFilter with explicit filters instead."
            )
            raise ValueError(msg)
        pk_attr_key = mapper.get_property_by_column(related_pk[0]).key
        relationship_attr = cast("InstrumentedAttribute[Any]", field)
        rel_filter = RelationshipFilter(
            relationship=relationship_attr,
            filters=(InCollectionFilter(field_name=pk_attr_key, values=values),),
            negate=negate,
        )
        return rel_filter.append_to_statement(statement, model)


@dataclass
class InCollectionFilter(InAnyFilter, Generic[T]):
    """Data required to construct a WHERE ... IN (...) clause.

    This filter restricts records based on a field's presence in a collection of values.

    The filter supports both ``IN`` and ``ANY`` operators for collection membership testing.
    Use ``prefer_any=True`` in ``append_to_statement`` to use the ``ANY`` operator. When
    ``field_name`` refers to a relationship attribute on a related model with a single
    primary key, filtering delegates to :class:`RelationshipFilter`.
    """

    field_name: FilterFieldName
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

        Args:
            statement: The SQLAlchemy statement to modify.
            model: The SQLAlchemy model class.
            prefer_any: If True, uses the SQLAlchemy :func:`sqlalchemy.any_` operator instead of
                :meth:`sqlalchemy.sql.expression.ColumnOperators.in_` for the filter condition.

        Returns:
            StatementTypeT: Modified statement with the appropriate IN conditions.
        """
        field = self._get_instrumented_attr(model, self.field_name)
        if self.values is None:
            return statement
        if not self.values:
            return cast("StatementTypeT", statement.where(text("1=-1")))
        rel_statement = self._append_relationship_collection(statement, model, field, self.values, negate=False)
        if rel_statement is not None:
            return rel_statement
        if prefer_any:
            return cast("StatementTypeT", statement.where(any_(self.values) == field))  # type: ignore[arg-type]
        return cast("StatementTypeT", statement.where(field.in_(self.values)))


@dataclass
class ChoicesFilter(InCollectionFilter[T]):
    """Filter records whose field matches one of a fixed set of choices."""


@dataclass
class BooleanFilter(StatementFilter):
    """Filter records by a boolean field value.

    If ``value`` is ``None``, the statement is returned unchanged.
    """

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or func expression."""
    value: Optional[bool]
    """Boolean value to match. If None, no filter is applied."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply a boolean equality condition to the statement."""
        if self.value is None:
            return statement
        field = self._get_instrumented_attr(model, self.field_name)
        return cast("StatementTypeT", statement.where(field == self.value))


@dataclass
class NotInCollectionFilter(InAnyFilter, Generic[T]):
    """Data required to construct a WHERE ... NOT IN (...) clause.

    This filter restricts records based on a field's absence in a collection of values.

    The filter supports both ``NOT IN`` and ``!= ANY`` operators for collection exclusion.
    Use ``prefer_any=True`` in ``append_to_statement`` to use the ``ANY`` operator.

    Args:
        field_name: Name of the model attribute to filter on.
        values: Values for the ``NOT IN`` clause. If this is None or empty,
            the filter is not applied.
    """

    field_name: FilterFieldName
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

        Args:
            statement: The SQLAlchemy statement to modify.
            model: The SQLAlchemy model class.
            prefer_any: If True, uses the SQLAlchemy :func:`sqlalchemy.any_` operator instead of
                :meth:`sqlalchemy.sql.expression.ColumnOperators.notin_` for the filter condition.

        Returns:
            StatementTypeT: Modified statement with the appropriate NOT IN conditions.
        """
        field = self._get_instrumented_attr(model, self.field_name)
        if not self.values:
            return statement
        rel_statement = self._append_relationship_collection(statement, model, field, self.values, negate=True)
        if rel_statement is not None:
            return rel_statement
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

            null_filter = NullFilter("email_verified_at")
            unverified = await repo.get_many(null_filter)

        With multiple filters::

            from advanced_alchemy.filters import (
                NullFilter,
                InCollectionFilter,
            )

            filters = [
                NullFilter("email_verified_at"),
                InCollectionFilter("role", ["admin", "moderator"]),
            ]
            results = await repo.get_many(*filters)

    See Also:
        - :class:`NotNullFilter`: Filter for NOT NULL values
        - :class:`InCollectionFilter`: Filter by collection membership
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.is_`: IS NULL operator
    """

    field_name: FilterFieldName
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

            not_null_filter = NotNullFilter("email_verified_at")
            verified = await repo.get_many(not_null_filter)

        With multiple filters::

            from advanced_alchemy.filters import (
                NotNullFilter,
                InCollectionFilter,
            )

            filters = [
                NotNullFilter("email_verified_at"),
                InCollectionFilter("role", ["admin", "moderator"]),
            ]
            results = await repo.get_many(*filters)

    See Also:
        - :class:`NullFilter`: Filter for NULL values
        - :class:`InCollectionFilter`: Filter by collection membership
        - :meth:`sqlalchemy.sql.expression.ColumnOperators.is_not`: IS NOT NULL operator
    """

    field_name: FilterFieldName
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


@dataclass
class OrderByFilter(StatementFilter):
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

    field_name: FilterFieldName
    """Field name, model attribute, or func expression (e.g., ``func.random()``)."""
    sort_order: Literal["asc", "desc"] = "asc"
    """Sort direction ("asc" or "desc")."""
    nulls: Optional[Literal["first", "last"]] = None
    """Where NULLs sort. ``None`` leaves the placement to the database."""

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
            if isinstance(self.field_name, str) and "." in self.field_name:
                field: InstrumentedField = self._get_relationship_order_expr(model, self.field_name)
            else:
                field = self._get_instrumented_attr(model, self.field_name)
            ordering = ordering_term(field, descending=self.sort_order == "desc", nulls=self.nulls)
            statement = cast("StatementTypeT", statement.order_by(ordering))
        return statement

    @staticmethod
    def _get_relationship_order_expr(model: Any, field_path: str) -> ColumnElement[Any]:
        """Build a correlated scalar subquery ordering expression for a to-one relationship path."""
        parts = field_path.split(".")
        min_rel_parts = 2
        if len(parts) < min_rel_parts or any(not part for part in parts):
            msg = f"Invalid relationship order path {field_path!r}"
            raise ValueError(msg)
        hops, leaf_field = parts[:-1], parts[-1]
        for part in parts:
            validate_identifier(part, "relationship" if part != leaf_field else "column")

        parent_info = inspect(model)
        first_rel = parent_info.mapper.relationships.get(hops[0])
        if first_rel is None:
            msg = f"Relationship {hops[0]!r} not found on model {parent_info.mapper.class_.__name__}"
            raise ValueError(msg)
        if first_rel.uselist:
            msg = f"OrderByFilter only supports single-valued (to-one) relationship paths; {hops[0]!r} is a collection."
            raise ValueError(msg)

        first_alias = aliased(first_rel.mapper.class_, flat=True)
        first_info = inspect(first_alias)
        primaryjoin, secondaryjoin, _src, _dest, secondary, _adapter = first_rel._create_joins(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            source_selectable=parent_info.selectable,
            dest_selectable=first_info.selectable,
            source_polymorphic=True,
            of_type_entity=first_info,
            alias_secondary=True,
        )
        correlate_keep: list[Any] = [first_info.selectable]
        if secondary is not None:
            correlate_keep.append(secondary)

        current_alias = first_alias
        joins: list[tuple[Any, Any]] = []
        for hop in hops[1:]:
            current_mapper = inspect(current_alias).mapper
            next_rel = current_mapper.relationships.get(hop)
            if next_rel is None:
                msg = f"Relationship {hop!r} not found on model {current_mapper.class_.__name__}"
                raise ValueError(msg)
            if next_rel.uselist:
                msg = f"OrderByFilter only supports single-valued (to-one) relationship paths; {hop!r} is a collection."
                raise ValueError(msg)
            next_alias = aliased(next_rel.mapper.class_, flat=True)
            next_info = inspect(next_alias)
            joins.append((next_alias, getattr(current_alias, hop)))
            correlate_keep.append(next_info.selectable)
            current_alias = next_alias

        leaf_attr = cast("ColumnElement[Any]", getattr(current_alias, leaf_field))
        subquery = select(leaf_attr).select_from(first_alias)
        if secondary is not None:
            if secondaryjoin is None:
                msg = "Many-to-many relationship is missing required secondary join configuration."
                raise ValueError(msg)
            subquery = subquery.select_from(secondary).where(and_(primaryjoin, secondaryjoin))
        else:
            subquery = subquery.where(primaryjoin)
        for next_alias, join_attr in joins:
            subquery = subquery.join(next_alias, join_attr)
        return subquery.correlate_except(*correlate_keep).scalar_subquery()


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


@dataclass
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

    field_name: "Union[FilterFieldName, AbstractSet[FilterFieldName], Sequence[FilterFieldName]]"
    """Field name, attribute, expression, or collection of field references to search on."""
    value: str
    """Text to match within the field(s)."""
    ignore_case: Optional[bool] = False
    """Whether to use case-insensitive matching."""
    escape_wildcards: bool = False
    """Whether to treat ``%`` and ``_`` in :attr:`value` as literal characters."""

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
    def normalized_field_names(self) -> "set[FilterFieldName]":
        """Convert field_name to a set if it is a single field reference.

        Returns:
            set[FilterFieldName]: Set of field names or expressions to be searched.
        """
        raw_fields: Any = self.field_name
        if isinstance(raw_fields, (str, ColumnElement, InstrumentedAttribute)):
            return {raw_fields}
        return set(cast("Iterable[FilterFieldName]", raw_fields))

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
        model_name = getattr(model, "__name__", type(model).__name__)
        for field_name in self.normalized_field_names:
            try:
                field = self._get_instrumented_attr(model, field_name)
                search_text = f"%{value}%"
                search_clause.append(self._func(field)(search_text, escape=escape_char))
            except AttributeError:
                msg = f"Skipping search for field {field_name}.  It is not found in model {model_name}"
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

    field_name: FilterFieldName
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


@dataclass
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


@dataclass
class ExistsFilter(StatementFilter):
    """Filter for EXISTS subqueries.

    This filter creates an EXISTS condition using a list of column expressions.
    The expressions can be combined using either AND or OR logic.

    .. important::

        ``values`` must include the condition that joins the subquery to the outer query.
        :meth:`~sqlalchemy.sql.expression.Select.correlate` only *permits* correlation; it cannot
        infer a join. Conditions that never mention the outer table produce a standalone subquery,
        which is true whenever any row matches it — so the filter matches **every** row of the outer
        query rather than raising.

    Args:
        values: List of SQLAlchemy column expressions to use in the EXISTS clause, including the
            correlation between the outer table and the subquery table.
        operator: If "and", combines conditions with AND, otherwise uses OR. Defaults to "and".

    Example:
        Basic usage with AND conditions::

            from sqlalchemy import select
            from advanced_alchemy.filters import ExistsFilter

            filter = ExistsFilter(
                values=[
                    User.organization_id == Organization.id,
                    User.email.like("%@example.com%"),
                ],
            )
            statement = filter.append_to_statement(
                select(Organization), Organization
            )

        This will return only organizations that have a user whose email contains "@example.com".

        Using OR conditions::

            filter = ExistsFilter(
                values=[User.role == "admin", User.role == "owner"],
                operator="or",
            )

        Note that this example is *not* correlated on its own — combine it with the correlation, or
        nest it in a :class:`FilterGroup`, to restrict the outer query.

    See Also:
        - :class:`NotExistsFilter`: The inverse of this filter
        - :func:`sqlalchemy.sql.expression.exists`: SQLAlchemy EXISTS expression
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
            ColumnElement[bool]: A SQLAlchemy column expression combining all conditions with AND or OR.
        """
        op = self._and if self.operator == "and" else self._or
        return op(*self.values)

    def get_exists_clause(self, model: type[ModelT]) -> ColumnElement[bool]:
        """Generate the EXISTS clause for the statement.

        Args:
            model: The SQLAlchemy model class to correlate with.

        Returns:
            ColumnElement[bool]: A correlated EXISTS expression for use in a WHERE clause.
        """
        if not self.values:
            return false()

        combined_conditions = self._get_combined_conditions()

        try:
            subquery = select(1).where(combined_conditions)
            correlated_subquery = subquery.correlate(model.__table__)
            return exists(correlated_subquery)
        except Exception:  # noqa: BLE001
            return false()

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Append EXISTS condition to the statement.

        Args:
            statement: The SQLAlchemy statement to modify.
            model: The SQLAlchemy model class.

        Returns:
            StatementTypeT: Modified statement with EXISTS condition.
        """
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

    Args:
        values: List of SQLAlchemy column expressions to use in the NOT EXISTS clause.
        operator: If "and", combines conditions with AND, otherwise uses OR. Defaults to "and".

    Example:
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
        - :class:`ExistsFilter`: The inverse of this filter
        - :func:`sqlalchemy.sql.expression.not_`: SQLAlchemy NOT operator
        - :func:`sqlalchemy.sql.expression.exists`: SQLAlchemy EXISTS expression
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
            model: The SQLAlchemy model class to correlate with.

        Returns:
            ColumnElement[bool]: A correlated NOT EXISTS expression for use in a WHERE clause.
        """
        if not self.values:
            return true()

        combined_conditions = self._get_combined_conditions()
        subquery = select(1).where(combined_conditions)
        correlated_subquery = subquery.correlate(model.__table__)
        return not_(exists(correlated_subquery))

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Append NOT EXISTS condition to the statement.

        Args:
            statement: The SQLAlchemy statement to modify.
            model: The SQLAlchemy model class.

        Returns:
            StatementTypeT: Modified statement with NOT EXISTS condition.
        """
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

        expressions = []
        for filter_obj in self.filters:
            filter_statement = filter_obj.append_to_statement(select(), model)
            if hasattr(filter_statement, "whereclause") and filter_statement.whereclause is not None:
                expressions.append(filter_statement.whereclause)  # pyright: ignore

        if expressions:
            combined = self.logical_operator(*expressions)
            return cast("StatementTypeT", statement.where(combined))
        return statement


@dataclass(init=False)
class RelationshipFilter(StatementFilter):
    """Filter records based on related model fields via correlated ``EXISTS`` subqueries.

    Supports one-to-many, many-to-one, many-to-many, self-referential, joined-table
    inheritance, and multi-hop relationship paths in a single database query while preserving
    loader criteria (such as soft-delete filtering) across aliased inner targets.
    """

    __slots__ = ("filters", "negate", "relationship")

    relationship: RelationshipPath
    """Relationship name, instrumented attribute, or sequence of hops."""
    filters: Sequence[Union[StatementFilter, ColumnElement[bool]]]
    """Filters or column predicates applied against the related model, including SQL expressions in filter fields."""
    negate: bool
    """If True, wraps the correlated subquery in ``NOT EXISTS`` instead of ``EXISTS``."""

    def __init__(
        self,
        relationship: RelationshipPath,
        filters: Sequence[Union[StatementFilter, ColumnElement[bool]]] = (),
        negate: bool = False,
    ) -> None:
        self.relationship = (
            tuple(relationship)
            if isinstance(relationship, Sequence) and not isinstance(relationship, str)
            else relationship
        )
        self.filters = tuple(filters)
        self.negate = negate

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
    ) -> StatementTypeT:
        """Apply relationship ``EXISTS`` or ``NOT EXISTS`` clause to statement.

        Args:
            statement: SQLAlchemy statement to modify.
            model: Parent SQLAlchemy model class or aliased class.

        Returns:
            StatementTypeT: Modified statement with the correlated subquery filter applied.

        Raises:
            ValueError: If a relationship hop is missing, invalid, or belongs to an unrelated model.
        """
        hops = self._normalize_hops()
        leaf_clause = self._compile_hops(model, hops, self.filters, negate=self.negate)
        return cast("StatementTypeT", statement.where(leaf_clause))

    def _normalize_hops(self) -> "tuple[RelationshipHop, ...]":
        if isinstance(self.relationship, (str, InstrumentedAttribute)):
            return (self.relationship,)
        hops = tuple(self.relationship)
        if not hops:
            msg = "RelationshipFilter requires at least one relationship hop."
            raise ValueError(msg)
        return hops

    def _compile_hops(
        self,
        model: Any,
        hops: "tuple[RelationshipHop, ...]",
        leaf_filters: Sequence[Union[StatementFilter, ColumnElement[bool]]],
        *,
        negate: bool,
    ) -> ColumnElement[bool]:
        head, *tail = hops
        rel_prop = self._get_relationship_property(model, head)
        target_cls = rel_prop.mapper.class_
        target_alias = aliased(target_cls, flat=True)
        inner_filters: Sequence[Union[StatementFilter, ColumnElement[bool]]] = (
            (self._compile_hops(target_alias, tuple(tail), leaf_filters, negate=False),) if tail else leaf_filters
        )
        return self._build_exists_subquery(model, rel_prop, target_alias, inner_filters, negate=negate)

    @staticmethod
    def _get_relationship_property(model: Any, hop: RelationshipHop) -> "RelationshipProperty[Any]":
        mapper = inspect(model).mapper
        if isinstance(hop, str):
            validate_identifier(hop, "relationship")
            rel_name = hop
        else:
            owner_cls = hop.parent.class_
            owner_matches = issubclass(mapper.class_, owner_cls) or issubclass(owner_cls, mapper.class_)
            if not owner_matches:
                msg = f"Relationship '{hop.key}' does not belong to model {mapper.class_.__name__}"
                raise ValueError(msg)
            rel_name = hop.key
        if rel_name not in mapper.relationships:
            msg = f"Relationship '{rel_name}' not found on model {mapper.class_.__name__}"
            raise ValueError(msg)
        return cast("RelationshipProperty[Any]", mapper.relationships[rel_name])

    @staticmethod
    def _build_exists_subquery(
        model: Any,
        rel_prop: "RelationshipProperty[Any]",
        target_alias: Any,
        filters: Sequence[Union[StatementFilter, ColumnElement[bool]]],
        *,
        negate: bool,
    ) -> ColumnElement[bool]:
        parent_info = inspect(model)
        target_info = inspect(target_alias)
        primaryjoin, secondaryjoin, _src, _dest, secondary, target_adapter = rel_prop._create_joins(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            source_selectable=parent_info.selectable,
            dest_selectable=target_info.selectable,
            source_polymorphic=True,
            of_type_entity=target_info,
            alias_secondary=True,
        )

        subquery: Select[Any] = select(1).select_from(target_alias)
        if secondary is not None:
            if secondaryjoin is None:
                msg = "Many-to-many relationship is missing required secondary join configuration."
                raise ValueError(msg)
            subquery = subquery.select_from(secondary).where(and_(primaryjoin, secondaryjoin))
        else:
            subquery = subquery.where(primaryjoin)

        for filter_ in filters:
            if isinstance(filter_, ColumnElement):
                adapted = target_adapter.traverse(filter_) if target_adapter is not None else filter_
                subquery = subquery.where(adapted)
            else:
                subquery = filter_.append_to_statement(subquery, target_alias)

        correlate_keep = (target_info.selectable, secondary) if secondary is not None else (target_info.selectable,)
        subquery = subquery.correlate_except(*correlate_keep)

        exists_clause: ColumnElement[bool] = exists(subquery)
        return not_(exists_clause) if negate else exists_clause


@dataclass
class MultiFilter(StatementFilter):
    """Apply multiple filters to a query based on a JSON/dict input.

    This filter provides a way to construct complex filter trees from
    a structured dictionary input, supporting nested logical groups and
    various filter types.
    """

    filters: dict[str, Any]
    """JSON/dict structure representing the filters."""
    allowed_relationships: "Optional[AbstractSet[str]]" = None
    """Optional allowlist of relationship names or dotted paths permitted in ``relationship`` nodes."""
    max_relationship_depth: Optional[int] = 3
    """Maximum total relationship nesting depth permitted in ``relationship`` nodes. ``None`` disables the limit."""
    allowed_fields: "Optional[AbstractSet[str]]" = None
    """Optional allowlist of field names or dotted relationship paths permitted in filter nodes."""
    max_depth: Optional[int] = 10
    """Maximum nesting depth permitted across logical groups and relationship filters. ``None`` disables the limit."""
    strict: bool = False
    """Raise ``ValueError`` or ``TypeError`` on malformed logical operators, conditions, or unknown filter types."""

    _filter_map: ClassVar[FilterMap] = {
        "before_after": BeforeAfterFilter,
        "on_before_after": OnBeforeAfterFilter,
        "boolean": BooleanFilter,
        "choices": ChoicesFilter,
        "collection": InCollectionFilter,
        "not_in_collection": NotInCollectionFilter,
        "limit_offset": LimitOffsetFilter,
        "null": NullFilter,
        "not_null": NotNullFilter,
        "order_by": OrderByFilter,
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

    def _build_root_groups(self) -> list[FilterGroup]:
        """Parse and validate top-level logical groups into ``FilterGroup`` instances."""
        groups: list[FilterGroup] = []
        for filter_type, conditions in self.filters.items():
            operator = self._logical_map.get(filter_type)
            if operator is None:
                if self.strict:
                    msg = f"Unsupported logical operator '{filter_type}'."
                    raise ValueError(msg)
                continue
            if not isinstance(conditions, list):
                if self.strict:
                    msg = f"Conditions for logical operator '{filter_type}' must be a list."
                    raise TypeError(msg)
                continue

            valid_filters: list[StatementFilter] = []
            typed_conditions: list[object] = conditions  # pyright: ignore[reportUnknownVariableType]
            for cond in typed_conditions:
                if not isinstance(cond, dict):
                    if self.strict:
                        msg = "Filter condition must be a dictionary."
                        raise TypeError(msg)
                    continue
                filter_instance = self._create_filter(
                    cast("dict[str, Any]", cond),
                    _tree_depth=1,
                    _rel_depth=0,
                    _rel_prefix=(),
                )
                if filter_instance is not None:
                    valid_filters.append(filter_instance)

            if valid_filters:
                groups.append(
                    FilterGroup(
                        logical_operator=operator,  # type: ignore[arg-type]
                        filters=valid_filters,
                    )
                )
        return groups

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
        for filter_group in self._build_root_groups():
            statement = filter_group.append_to_statement(statement, model)
        return statement

    def _validate_filter_fields(
        self,
        filter_type: str,
        filter_instance: StatementFilter,
        rel_prefix: tuple[str, ...],
    ) -> None:
        """Validate instantiated filter fields against ``allowed_fields``."""
        if self.allowed_fields is None:
            return

        if filter_type in {"exists", "not_exists", "filter_group"}:
            msg = f"Filter type '{filter_type}' is not permitted when allowed_fields is set."
            raise ValueError(msg)

        if filter_type == "limit_offset":
            return

        field_name = getattr(filter_instance, "field_name", None)
        if isinstance(field_name, str):
            full_path = ".".join((*rel_prefix, field_name))
            if not field_name or full_path not in self.allowed_fields:
                msg = f"Field '{full_path}' is not permitted by allowed_fields."
                raise ValueError(msg)
            return

        if isinstance(filter_instance, (SearchFilter, NotInSearchFilter)) and isinstance(
            field_name, (list, tuple, set, frozenset)
        ):
            field_names = cast("Collection[Any]", field_name)
            if not field_names:
                msg = "Search filter 'field_name' cannot be empty when allowed_fields is set."
                raise ValueError(msg)
            for candidate in field_names:
                if not isinstance(candidate, str) or not candidate:
                    msg = f"Field expression {candidate!r} is not permitted when allowed_fields is set."
                    raise ValueError(msg)
                full_path = ".".join((*rel_prefix, candidate))
                if full_path not in self.allowed_fields:
                    msg = f"Field '{full_path}' is not permitted by allowed_fields."
                    raise ValueError(msg)
            return

        msg = f"Field expression {field_name!r} is not permitted when allowed_fields is set."
        raise ValueError(msg)

    def _instantiate_leaf_filter(
        self,
        filter_type: str,
        condition: dict[str, Any],
        rel_prefix: tuple[str, ...],
    ) -> Optional[StatementFilter]:
        filter_class = self._filter_map.get(filter_type)
        if filter_class is None:
            if self.strict:
                msg = f"Unsupported filter type '{filter_type}'."
                raise ValueError(msg)
            return None

        try:
            filter_args = {k: v for k, v in condition.items() if k != "type"}
            filter_instance = cast("StatementFilter", filter_class(**filter_args))  # type: ignore
        except Exception:
            if self.strict:
                raise
            return None

        self._validate_filter_fields(filter_type, filter_instance, rel_prefix)
        return filter_instance

    def _create_filter(
        self,
        condition: dict[str, Any],
        *,
        _tree_depth: int = 1,
        _rel_depth: int = 0,
        _rel_prefix: tuple[str, ...] = (),
    ) -> Optional[StatementFilter]:
        """Create a filter instance from a condition dictionary.

        Args:
            condition: Dictionary defining a filter

        Returns:
            Optional[StatementFilter]: Filter instance if successfully created, None otherwise
        """
        if self.max_depth is not None and _tree_depth > self.max_depth:
            msg = f"Filter nesting depth {_tree_depth} exceeds maximum allowed depth {self.max_depth}."
            raise ValueError(msg)

        nested_group = self._create_nested_filter_group(
            condition,
            _tree_depth=_tree_depth,
            _rel_depth=_rel_depth,
            _rel_prefix=_rel_prefix,
        )
        if nested_group is not None or (self._logical_map.keys() & condition.keys()):
            return nested_group

        filter_type = condition.get("type")
        if not isinstance(filter_type, str):
            if self.strict:
                msg = "Filter condition requires a string 'type' field."
                raise ValueError(msg)
            return None

        if filter_type == "relationship":
            return self._create_relationship_filter(
                condition,
                _tree_depth=_tree_depth,
                _rel_depth=_rel_depth,
                _rel_prefix=_rel_prefix,
            )

        return self._instantiate_leaf_filter(filter_type, condition, _rel_prefix)

    def _create_nested_filter_group(
        self,
        condition: dict[str, Any],
        *,
        _tree_depth: int = 1,
        _rel_depth: int = 0,
        _rel_prefix: tuple[str, ...] = (),
    ) -> Optional[FilterGroup]:
        logical_keys = set(self._logical_map.keys())
        intersect = logical_keys.intersection(condition.keys())
        if not intersect:
            return None

        if self.strict and len(intersect) > 1:
            msg = "Filter group condition cannot specify multiple logical operators."
            raise ValueError(msg)

        if self.strict and not set(condition.keys()).issubset(logical_keys):
            msg = "Filter group condition cannot mix logical operators with extra keys."
            raise ValueError(msg)

        for key in intersect:
            operator = self._logical_map.get(key)
            nested_conditions = condition.get(key)
            if not isinstance(nested_conditions, list):
                if self.strict:
                    msg = f"Conditions for logical operator '{key}' must be a list."
                    raise TypeError(msg)
                continue

            next_tree_depth = _tree_depth + 1
            if self.max_depth is not None and next_tree_depth > self.max_depth:
                msg = f"Filter nesting depth {next_tree_depth} exceeds maximum allowed depth {self.max_depth}."
                raise ValueError(msg)

            if operator:
                nested_filters: list[StatementFilter] = []
                typed_conditions: list[object] = nested_conditions  # pyright: ignore[reportUnknownVariableType]
                for cond in typed_conditions:
                    if not isinstance(cond, dict):
                        if self.strict:
                            msg = "Filter condition must be a dictionary."
                            raise TypeError(msg)
                        continue
                    filter_instance = self._create_filter(
                        cast("dict[str, Any]", cond),
                        _tree_depth=next_tree_depth,
                        _rel_depth=_rel_depth,
                        _rel_prefix=_rel_prefix,
                    )
                    if filter_instance is not None:
                        nested_filters.append(filter_instance)

                if nested_filters:
                    return FilterGroup(logical_operator=operator, filters=nested_filters)  # type: ignore[arg-type]
        return None

    def _create_relationship_filter(
        self,
        condition: dict[str, Any],
        *,
        _tree_depth: int = 1,
        _rel_depth: int = 0,
        _rel_prefix: tuple[str, ...] = (),
    ) -> Optional[RelationshipFilter]:
        relationship = condition.get("relationship")
        nested_conditions = condition.get("filters", [])
        if not isinstance(nested_conditions, (list, tuple)):
            msg = "Relationship filter 'filters' must be a list of filter definitions."
            raise TypeError(msg)

        if isinstance(relationship, str):
            hops: tuple[str, ...] = (relationship,)
        elif (
            isinstance(relationship, (list, tuple))
            and relationship
            and all(isinstance(h, str) for h in cast("Sequence[Any]", relationship))
        ):
            hops = tuple(cast("Sequence[str]", relationship))
        else:
            msg = "Relationship filter requires a relationship name or sequence of relationship names."
            raise ValueError(msg)

        for hop in hops:
            validate_identifier(hop, "relationship")

        next_rel_depth = _rel_depth + len(hops)
        if self.max_relationship_depth is not None and next_rel_depth > self.max_relationship_depth:
            msg = f"Relationship filter depth {next_rel_depth} exceeds maximum allowed depth {self.max_relationship_depth}."
            raise ValueError(msg)

        next_tree_depth = _tree_depth + len(hops)
        if self.max_depth is not None and next_tree_depth > self.max_depth:
            msg = f"Filter nesting depth {next_tree_depth} exceeds maximum allowed depth {self.max_depth}."
            raise ValueError(msg)

        next_rel_prefix = (*_rel_prefix, *hops)
        if self.allowed_relationships is not None:
            dotted_path = ".".join(hops)
            prefixed_dotted_path = ".".join(next_rel_prefix)
            if (
                prefixed_dotted_path not in self.allowed_relationships
                and dotted_path not in self.allowed_relationships
                and not all(hop in self.allowed_relationships for hop in hops)
            ):
                msg = f"Relationship '{prefixed_dotted_path}' is not permitted by allowed_relationships."
                raise ValueError(msg)

        nested_filters: list[StatementFilter] = []
        for nested in cast("Sequence[Any]", nested_conditions):
            if not isinstance(nested, dict):
                if self.strict:
                    msg = "Relationship filter condition must be a dictionary."
                    raise TypeError(msg)
                continue
            nested_filter = self._create_filter(
                cast("dict[str, Any]", nested),
                _tree_depth=next_tree_depth,
                _rel_depth=next_rel_depth,
                _rel_prefix=next_rel_prefix,
            )
            if nested_filter is not None:
                nested_filters.append(nested_filter)

        rel_arg: RelationshipPath = hops[0] if len(hops) == 1 else hops
        return RelationshipFilter(
            relationship=rel_arg,
            filters=nested_filters,
            negate=bool(condition.get("negate", False)),
        )


FilterTypes: TypeAlias = Union[
    BeforeAfterFilter,
    OnBeforeAfterFilter,
    BooleanFilter,
    ChoicesFilter[Any],
    InCollectionFilter[Any],
    LimitOffsetFilter,
    NullFilter,
    NotNullFilter,
    OrderByFilter,
    SearchFilter,
    NotInCollectionFilter[Any],
    NotInSearchFilter,
    ExistsFilter,
    NotExistsFilter,
    ComparisonFilter,
    RelationshipFilter,
    MultiFilter,
    FilterGroup,
    CursorFilter,
]
"""Aggregate type alias of the types supported for collection filtering."""


_DEPRECATED_FILTER_NAMES = {
    "BeforeAfter": "BeforeAfterFilter",
    "CollectionFilter": "InCollectionFilter",
    "LimitOffset": "LimitOffsetFilter",
    "OnBeforeAfter": "OnBeforeAfterFilter",
    "OrderBy": "OrderByFilter",
}

if TYPE_CHECKING:
    from advanced_alchemy.filters._filterset import FilterSet

    BeforeAfter = BeforeAfterFilter
    CollectionFilter = InCollectionFilter
    LimitOffset = LimitOffsetFilter
    OnBeforeAfter = OnBeforeAfterFilter
    OrderBy = OrderByFilter
else:

    def __getattr__(name: str) -> Any:
        """Resolve ``FilterSet`` lazily and deprecated filter names to their ``*Filter`` replacements."""
        if name == "FilterSet":
            from advanced_alchemy.filters._filterset import FilterSet

            globals()["FilterSet"] = FilterSet
            return FilterSet
        new_name = _DEPRECATED_FILTER_NAMES.get(name)
        if new_name is None:
            msg = f"module {__name__!r} has no attribute {name!r}"
            raise AttributeError(msg)

        from advanced_alchemy.utils.deprecation import warn_deprecation

        warn_deprecation(
            version="1.13.0",
            removal_in="2.0.0",
            deprecated_name=f"{__name__}.{name}",
            kind="import",
            alternative=f"{__name__}.{new_name}",
            stacklevel=3,
        )
        return globals()[new_name]

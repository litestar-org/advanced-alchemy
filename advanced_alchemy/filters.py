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
    - :class:`~advanced_alchemy.base.BasicAttributes`: Base model definitions

"""

import datetime
import logging
from abc import ABC, abstractmethod
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
    Delete,
    Integer,
    Select,
    Update,
    and_,
    any_,
    case,
    exists,
    false,
    inspect,
    literal_column,
    not_,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql import operators as op
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from sqlalchemy.sql.elements import UnaryExpression
from typing_extensions import TypeAlias, TypedDict, TypeVar

from advanced_alchemy.base import ModelProtocol
from advanced_alchemy.operations import validate_identifier

if TYPE_CHECKING:
    from sqlalchemy.orm import RelationshipProperty

    FilterFieldName: TypeAlias = Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]
    InstrumentedField: TypeAlias = Union[ColumnElement[Any], InstrumentedAttribute[Any]]
    RelationshipHop: TypeAlias = Union[str, InstrumentedAttribute[Any]]
    RelationshipPath: TypeAlias = Union[RelationshipHop, Sequence[RelationshipHop]]
else:
    FilterFieldName: TypeAlias = Any
    InstrumentedField: TypeAlias = Any
    RelationshipHop: TypeAlias = Any
    RelationshipPath: TypeAlias = Any

__all__ = (
    "LIKE_ESCAPE_CHAR",
    "BeforeAfter",
    "BooleanFilter",
    "ChoicesFilter",
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
    "NotNullFilter",
    "NullFilter",
    "OnBeforeAfter",
    "OrderBy",
    "PaginationFilter",
    "RelationshipFilter",
    "SearchFilter",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
    "escape_like_value",
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


class FilterMap(TypedDict):
    """Mapping of filter type keys to their corresponding filter classes."""

    before_after: "type[BeforeAfter]"
    """Exclusive datetime range filter class."""
    on_before_after: "type[OnBeforeAfter]"
    """Inclusive datetime range filter class."""
    boolean: "type[BooleanFilter]"
    """Boolean equality filter class."""
    choices: "type[ChoicesFilter[Any]]"
    """Fixed-choice membership filter class."""
    collection: "type[CollectionFilter[Any]]"
    """Collection ``IN`` / ``ANY`` membership filter class."""
    not_in_collection: "type[NotInCollectionFilter[Any]]"
    """Collection ``NOT IN`` / ``!= ANY`` exclusion filter class."""
    limit_offset: "type[LimitOffset]"
    """Limit and offset pagination filter class."""
    null: "type[NullFilter]"
    """``IS NULL`` filter class."""
    not_null: "type[NotNullFilter]"
    """``IS NOT NULL`` filter class."""
    order_by: "type[OrderBy]"
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


@dataclass
class BeforeAfter(StatementFilter):
    """DateTime range filter with exclusive bounds.

    This filter creates date/time range conditions using < and > operators,
    excluding the boundary values.

    If either `before` or `after` is None, that boundary condition is not applied.

    See Also:
        :class:`OnBeforeAfter`: Inclusive datetime range filtering
    """

    field_name: FilterFieldName
    """Field name, model attribute, or func expression."""
    before: Optional[datetime.datetime]
    """Filter results where field is earlier than this value."""
    after: Optional[datetime.datetime]
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
class OnBeforeAfter(StatementFilter):
    """DateTime range filter with inclusive bounds.

    This filter creates date/time range conditions using <= and >= operators,
    including the boundary values.

    If either `on_or_before` or `on_or_after` is None, that boundary condition
    is not applied.

    See Also:
        :class:`BeforeAfter`: Exclusive datetime range filtering
    """

    field_name: FilterFieldName
    """Field name, model attribute, or func expression."""
    on_or_before: Optional[datetime.datetime]
    """Filter results where field is on or earlier than this value."""
    on_or_after: Optional[datetime.datetime]
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
            filters=(CollectionFilter(field_name=pk_attr_key, values=values),),
            negate=negate,
        )
        return rel_filter.append_to_statement(statement, model)


@dataclass
class CollectionFilter(InAnyFilter, Generic[T]):
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
class ChoicesFilter(CollectionFilter[T]):
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
                CollectionFilter,
            )

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
                CollectionFilter,
            )

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
            statement = cast("StatementTypeT", statement.limit(self.limit).offset(self.offset))
        return statement


@dataclass
class OrderBy(StatementFilter):
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
            ordering: ColumnElement[Any] = field.desc() if self.sort_order == "desc" else field.asc()
            if self.nulls is not None:
                ordering = _NullsPlacement(
                    ordering, modifier=op.nulls_first_op if self.nulls == "first" else op.nulls_last_op
                )
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
            msg = f"OrderBy only supports single-valued (to-one) relationship paths; {hops[0]!r} is a collection."
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
                msg = f"OrderBy only supports single-valued (to-one) relationship paths; {hop!r} is a collection."
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

    _filter_map: ClassVar[FilterMap] = {
        "before_after": BeforeAfter,
        "on_before_after": OnBeforeAfter,
        "boolean": BooleanFilter,
        "choices": ChoicesFilter,
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
                valid_filters: list[StatementFilter] = []
                for cond in conditions:  # pyright: ignore
                    filter_instance = self._create_filter(cond)  # pyright: ignore
                    if filter_instance is not None:
                        valid_filters.append(filter_instance)

                if valid_filters:
                    filter_group = FilterGroup(
                        logical_operator=operator,  # type: ignore
                        filters=valid_filters,
                    )
                    statement = filter_group.append_to_statement(statement, model)
        return statement

    def _create_filter(self, condition: dict[str, Any], *, _depth: int = 0) -> Optional[StatementFilter]:
        """Create a filter instance from a condition dictionary.

        Args:
            condition: Dictionary defining a filter

        Returns:
            Optional[StatementFilter]: Filter instance if successfully created, None otherwise
        """
        nested_group = self._create_nested_filter_group(condition, _depth=_depth)
        if nested_group is not None:
            return nested_group

        filter_type = condition.get("type")
        if not isinstance(filter_type, str):
            return None

        if filter_type == "relationship":
            return self._create_relationship_filter(condition, _depth=_depth)

        filter_class = self._filter_map.get(filter_type)
        if filter_class is not None:
            try:
                filter_args = {k: v for k, v in condition.items() if k != "type"}
                return filter_class(**filter_args)  # type: ignore
            except Exception:  # noqa: BLE001
                return None
        return None

    def _create_nested_filter_group(self, condition: dict[str, Any], *, _depth: int = 0) -> Optional[FilterGroup]:
        logical_keys = set(self._logical_map.keys())
        intersect = logical_keys.intersection(condition.keys())
        for key in intersect:
            operator = self._logical_map.get(key)
            nested_conditions = condition.get(key)
            if operator and isinstance(nested_conditions, list):
                nested_filters: list[StatementFilter] = []
                typed_conditions: list[object] = nested_conditions  # pyright: ignore[reportUnknownVariableType]
                for cond in typed_conditions:
                    if isinstance(cond, dict):
                        filter_instance = self._create_filter(cast("dict[str, Any]", cond), _depth=_depth)
                        if filter_instance is not None:
                            nested_filters.append(filter_instance)

                if nested_filters:
                    return FilterGroup(logical_operator=operator, filters=nested_filters)  # type: ignore[arg-type]
        return None

    def _create_relationship_filter(
        self, condition: dict[str, Any], *, _depth: int = 0
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

        next_depth = _depth + len(hops)
        if self.max_relationship_depth is not None and next_depth > self.max_relationship_depth:
            msg = f"Relationship filter depth {next_depth} exceeds maximum allowed depth {self.max_relationship_depth}."
            raise ValueError(msg)

        if self.allowed_relationships is not None:
            dotted_path = ".".join(hops)
            if dotted_path not in self.allowed_relationships and not all(
                hop in self.allowed_relationships for hop in hops
            ):
                msg = f"Relationship '{dotted_path}' is not permitted by allowed_relationships."
                raise ValueError(msg)

        nested_filters: list[StatementFilter] = []
        for nested in cast("Sequence[Any]", nested_conditions):
            if isinstance(nested, dict):
                nested_filter = self._create_filter(cast("dict[str, Any]", nested), _depth=next_depth)
                if nested_filter is not None:
                    nested_filters.append(nested_filter)

        rel_arg: RelationshipPath = hops[0] if len(hops) == 1 else hops
        return RelationshipFilter(
            relationship=rel_arg,
            filters=nested_filters,
            negate=bool(condition.get("negate", False)),
        )


FilterTypes: TypeAlias = Union[
    BeforeAfter,
    OnBeforeAfter,
    BooleanFilter,
    ChoicesFilter[Any],
    CollectionFilter[Any],
    LimitOffset,
    NullFilter,
    NotNullFilter,
    OrderBy,
    SearchFilter,
    NotInCollectionFilter[Any],
    NotInSearchFilter,
    ExistsFilter,
    NotExistsFilter,
    ComparisonFilter,
    RelationshipFilter,
    MultiFilter,
    FilterGroup,
]
"""Aggregate type alias of the types supported for collection filtering."""


class _NullsPlacement(UnaryExpression[Any]):
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


@compiles(_NullsPlacement, "mysql")
@compiles(_NullsPlacement, "mariadb")
@compiles(_NullsPlacement, "mssql")
def _compile_nulls_placement_emulated(  # pyright: ignore[reportUnusedFunction]
    element: _NullsPlacement, compiler: Any, **kw: Any
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

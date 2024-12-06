"""Collection filter datastructures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import abc  # noqa: TC003
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from operator import attrgetter
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Generic,
    Literal,
    TypeVar,
    cast,
)

from sqlalchemy import BinaryExpression, ColumnElement, Date, Delete, Select, Update, and_, any_, or_, text
from sqlalchemy.sql import operators as op
from typing_extensions import TypeAlias, TypedDict

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate

    from advanced_alchemy import base

__all__ = (
    "BeforeAfter",
    "CollectionFilter",
    "FilterGroup",
    "FilterTypes",
    "InAnyFilter",
    "LimitOffset",
    "MultiFilter",
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
ModelT = TypeVar("ModelT", bound="base.ModelProtocol")
StatementFilterT = TypeVar("StatementFilterT", bound="StatementFilter")
StatementTypeT = TypeVar(
    "StatementTypeT",
    bound="ReturningDelete[tuple[Any]] | ReturningUpdate[tuple[Any]] | Select[tuple[Any]] | Select[Any] | Update | Delete",
)
FilterTypes: TypeAlias = "BeforeAfter | OnBeforeAfter | CollectionFilter[Any] | LimitOffset | OrderBy | SearchFilter | NotInCollectionFilter[Any] | NotInSearchFilter"
"""Aggregate type alias of the types supported for collection filtering."""


# Define TypedDicts for filter and logical maps
class FilterMapDict(TypedDict):
    before_after: type[BeforeAfter]
    on_before_after: type[OnBeforeAfter]
    collection: type[CollectionFilter]
    not_in_collection: type[NotInCollectionFilter]
    limit_offset: type[LimitOffset]
    order_by: type[OrderBy]
    search: type[SearchFilter]
    not_in_search: type[NotInSearchFilter]
    filter_group: type[FilterGroup]  # For nested filter groups


class LogicalMapDict(TypedDict):
    and_: Callable[..., ColumnElement[bool]]
    or_: Callable[..., ColumnElement[bool]]


class StatementFilter(ABC):
    @abstractmethod
    def append_to_statement(
        self, statement: StatementTypeT, model: type[ModelT], *args: Any, **kwargs: Any
    ) -> StatementTypeT:
        return statement

    @staticmethod
    def _get_instrumented_attr(model: Any, key: str | InstrumentedAttribute[Any]) -> InstrumentedAttribute[Any]:
        if isinstance(key, str):
            return cast("InstrumentedAttribute[Any]", getattr(model, key))
        return key


@dataclass
class BeforeAfter(StatementFilter):
    """Data required to filter a query on a ``datetime`` column."""

    field_name: str
    """Name of the model attribute to filter on."""
    before: datetime | None
    """Filter results where field earlier than this."""
    after: datetime | None
    """Filter results where field later than this."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.before is not None:
            statement = cast("StatementTypeT", statement.where(field < self.before))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if self.after is not None:
            statement = cast("StatementTypeT", statement.where(field > self.after))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement


@dataclass
class OnBeforeAfter(StatementFilter):
    """Data required to filter a query on a ``datetime`` column."""

    field_name: str
    """Name of the model attribute to filter on."""
    on_or_before: datetime | None
    """Filter results where field is on or earlier than this."""
    on_or_after: datetime | None
    """Filter results where field on or later than this."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.on_or_before is not None:
            statement = cast("StatementTypeT", statement.where(field <= self.on_or_before))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if self.on_or_after is not None:
            statement = cast("StatementTypeT", statement.where(field >= self.on_or_after))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement


class InAnyFilter(StatementFilter, ABC):
    """Subclass for methods that have a `prefer_any` attribute."""


@dataclass
class CollectionFilter(InAnyFilter, Generic[T]):
    """Data required to construct a ``WHERE ... IN (...)`` clause."""

    field_name: str
    """Name of the model attribute to filter on."""
    values: abc.Collection[T] | None
    """Values for ``IN`` clause.

    An empty list will return an empty result set, however, if ``None``, the filter is not applied to the query, and all rows are returned. """

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> StatementTypeT:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.values is None:
            return statement
        if not self.values:
            return cast("StatementTypeT", statement.where(text("1=-1")))
        if prefer_any:
            return cast("StatementTypeT", statement.where(any_(self.values) == field))  # type: ignore[arg-type]
        return cast("StatementTypeT", statement.where(field.in_(self.values)))


@dataclass
class NotInCollectionFilter(InAnyFilter, Generic[T]):
    """Data required to construct a ``WHERE ... NOT IN (...)`` clause."""

    field_name: str
    """Name of the model attribute to filter on."""
    values: abc.Collection[T] | None
    """Values for ``NOT IN`` clause.

    An empty list or ``None`` will return all rows."""

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> StatementTypeT:
        field = self._get_instrumented_attr(model, self.field_name)
        if not self.values:
            return statement
        if prefer_any:
            return cast("StatementTypeT", statement.where(any_(self.values) != field))  # type: ignore[arg-type]
        return cast("StatementTypeT", statement.where(field.notin_(self.values)))


class PaginationFilter(StatementFilter, ABC):
    """Subclass for methods that function as a pagination type."""


@dataclass
class LimitOffset(PaginationFilter):
    """Data required to add limit/offset filtering to a query."""

    limit: int
    """Value for ``LIMIT`` clause of query."""
    offset: int
    """Value for ``OFFSET`` clause of query."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        if isinstance(statement, Select):
            return cast("StatementTypeT", statement.limit(self.limit).offset(self.offset))
        return statement


@dataclass
class OrderBy(StatementFilter):
    """Data required to construct a ``ORDER BY ...`` clause."""

    field_name: str
    """Name of the model attribute to sort on."""
    sort_order: Literal["asc", "desc"] = "asc"
    """Sort ascending or descending"""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        if not isinstance(statement, Select):
            return statement
        field = self._get_instrumented_attr(model, self.field_name)
        if self.sort_order == "desc":
            return cast("StatementTypeT", statement.order_by(field.desc()))
        return cast("StatementTypeT", statement.order_by(field.asc()))


@dataclass
class SearchFilter(StatementFilter):
    """Data required to construct a ``WHERE field_name LIKE '%' || :value || '%'`` clause."""

    field_name: str | set[str]
    """Name of the model attribute to search on."""
    value: str
    """Search value."""
    ignore_case: bool | None = False
    """Should the search be case insensitive."""

    @property
    def _operator(self) -> Callable[..., ColumnElement[bool]]:
        return or_

    @property
    def _func(self) -> attrgetter[Callable[[str], BinaryExpression[bool]]]:
        return attrgetter("ilike" if self.ignore_case else "like")

    @property
    def normalized_field_names(self) -> set[str]:
        return {self.field_name} if isinstance(self.field_name, str) else self.field_name

    def get_search_clauses(self, model: type[ModelT]) -> list[BinaryExpression[bool]]:
        search_clause: list[BinaryExpression[bool]] = []
        for field_name in self.normalized_field_names:
            field = self._get_instrumented_attr(model, field_name)
            search_text = f"%{self.value}%"
            search_clause.append(self._func(field)(search_text))
        return search_clause

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
    ) -> StatementTypeT:
        where_clause = self._operator(*self.get_search_clauses(model))
        return cast("StatementTypeT", statement.where(where_clause))


@dataclass
class NotInSearchFilter(SearchFilter):
    """Data required to construct a ``WHERE field_name NOT LIKE '%' || :value || '%'`` clause."""

    @property
    def _operator(self) -> Callable[..., ColumnElement[bool]]:
        return and_

    @property
    def _func(self) -> attrgetter[Callable[[str], BinaryExpression[bool]]]:
        return attrgetter("not_ilike" if self.ignore_case else "not_like")


@dataclass
class FilterGroup(StatementFilter):
    """A group of filters combined with a logical operator."""

    logical_operator: Callable[..., BinaryExpression[bool]]
    """Logical operator to combine the filters (e.g., and_, or_)."""
    filters: list[StatementFilter]
    """List of filters to combine."""

    def append_to_statement(
        self,
        statement: StatementTypeT,
        model: type[ModelT],
    ) -> StatementTypeT:
        clauses = [f.append_to_statement(statement, model) for f in self.filters]
        if clauses:
            combined = self.logical_operator(*clauses)
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
    "dateeq": lambda c, v: cast(Date, c) == v,
}


@dataclass
class MultiFilter(StatementFilter):
    """Apply multiple filters to a query based on a JSON/dict input."""

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
        for filter_type, conditions in self.filters.items():
            operator = self._logical_map.get(filter_type)
            if operator:
                # Create a FilterGroup with the logical operator and corresponding filters
                filter_group = FilterGroup(
                    logical_operator=operator,
                    filters=[
                        self._create_filter(cond)
                        for cond in conditions
                        if (filter_instance := self._create_filter(cond))
                    ],
                )
                statement = filter_group.append_to_statement(statement, model)
            else:
                # Handle other filter types if necessary
                pass
        return statement

    def _create_filter(self, condition: dict[str, Any]) -> StatementFilter | None:
        if not isinstance(condition, dict):
            return None

        # Check if condition is a nested logical group
        logical_keys = set(self._logical_map.keys())
        intersect = logical_keys.intersection(condition.keys())
        if intersect:
            # It's a nested filter group
            for key in intersect:
                operator = self._logical_map.get(key)
                if operator:
                    nested_filters = [self._create_filter(cond) for cond in condition[key] if self._create_filter(cond)]
                    if nested_filters:
                        return FilterGroup(logical_operator=operator, filters=nested_filters)
        else:
            # Regular filter
            filter_type = condition.get("type")
            filter_class = self._filter_map.get(filter_type)
            if filter_class:
                return filter_class(**{k: v for k, v in condition.items() if k != "type"})
        return None


@dataclass
class TanStackFilter:
    """Adapter to convert TanStack Tables filter input into MultiFilter-compatible format."""

    tanstack_filters: list[dict[str, Any]]

    def to_multifilter_format(self) -> dict[str, Any]:
        """Convert TanStack filter list to MultiFilter dict."""

        def parse_filters(filters: list[dict[str, Any]], logical_op: str = "and") -> dict[str, Any]:
            return {
                logical_op: [
                    self._parse_single_filter(filt) for filt in filters if self._parse_single_filter(filt) is not None
                ]
            }

        return parse_filters(self.tanstack_filters)

    def _parse_single_filter(self, filter_obj: dict[str, Any]) -> dict[str, Any] | None:
        if "logical" in filter_obj and "filters" in filter_obj:
            # Nested logical group
            return {
                filter_obj["logical"]: [
                    self._parse_single_filter(filt)
                    for filt in filter_obj["filters"]
                    if self._parse_single_filter(filt) is not None
                ]
            }
        # Single filter condition
        field = filter_obj.get("field")
        operator = filter_obj.get("operator")
        value = filter_obj.get("value")

        # Map TanStack operators to your filter types and operators_map
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
            # Add more mappings as needed
        }

        mapped_operator = operator_mapping.get(operator)
        if not mapped_operator:
            return None  # Unsupported operator

        # Determine filter type based on operator
        if mapped_operator in {"eq", "ne", "gt", "ge", "lt", "le"}:
            return {
                "type": "before_after" if "before" in filter_obj or "after" in filter_obj else "simple_filter",
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
        if mapped_operator in {"like", "not_like"}:
            return {
                "type": "search",
                "field_name": field,
                "value": value,
                "ignore_case": True,  # Adjust based on requirements
            }
        # Add more conditions as needed
        return None


@dataclass
class AGGridFilterAdapter:
    """Adapter to convert AG Grid filter input into MultiFilter-compatible format."""

    aggrid_filters: dict[str, dict[str, Any]]

    def to_multifilter_format(self) -> dict[str, Any]:
        """Convert AG Grid filter model to MultiFilter dict."""
        filters = []
        for field, condition in self.aggrid_filters.items():
            _filter_type = condition.get("filterType")
            operator = condition.get("type")
            value = condition.get("filter")
            filter_conditions = {}

            # Map AG Grid operators to your operators_map
            operator_mapping = {
                "equals": "eq",
                "notEqual": "ne",
                "contains": "like",
                "notContains": "not_like",
                "startsWith": "startswith",
                "endsWith": "endswith",
                "inRange": "between",
                # Add more mappings as needed
            }

            mapped_operator = operator_mapping.get(operator)
            if not mapped_operator:
                continue  # Unsupported operator

            if mapped_operator == "between":
                filter_conditions = {
                    "type": "between",
                    "field_name": field,
                    "value": [
                        condition.get("filter", 0),
                        condition.get("filterTo", 0),
                    ],  # Expecting 'filter' and 'filterTo'
                }
            else:
                filter_conditions = {
                    "type": "search" if "like" in mapped_operator else "simple_filter",
                    "field_name": field,
                    "operator": mapped_operator,
                    "value": value,
                    "ignore_case": True,  # Adjust based on requirements
                }

            filters.append(filter_conditions)

        return {"and_": filters}  # Combine all filters with AND by default

"""Collection filter datastructures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import abc  # noqa: TC003
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Generic, Literal, cast

from sqlalchemy import BinaryExpression, Delete, Select, Update, and_, any_, or_, text
from typing_extensions import TypeVar

if TYPE_CHECKING:
    from typing import Callable

    from sqlalchemy import ColumnElement
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
    from typing_extensions import TypeAlias

    from advanced_alchemy import base


__all__ = (
    "BeforeAfter",
    "CollectionFilter",
    "FilterTypes",
    "InAnyFilter",
    "LimitOffset",
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
    bound="ReturningDelete[tuple[Any]] |  ReturningUpdate[tuple[Any]] | Select[tuple[Any]] | Select[Any] | Update | Delete",
)
FilterTypes: TypeAlias = "BeforeAfter | OnBeforeAfter | CollectionFilter[Any] | LimitOffset | OrderBy | SearchFilter | NotInCollectionFilter[Any] | NotInSearchFilter"
"""Aggregate type alias of the types supported for collection filtering."""


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

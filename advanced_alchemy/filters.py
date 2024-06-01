"""Collection filter datastructures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import abc  # noqa: TCH003
from dataclasses import dataclass
from datetime import datetime  # noqa: TCH003
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, cast

from sqlalchemy import any_, text

if TYPE_CHECKING:
    from sqlalchemy import Select, StatementLambdaElement
    from sqlalchemy.orm import InstrumentedAttribute
    from typing_extensions import TypeAlias

    from advanced_alchemy import base


__all__ = (
    "BeforeAfter",
    "CollectionFilter",
    "FilterTypes",
    "LimitOffset",
    "OrderBy",
    "SearchFilter",
    "NotInCollectionFilter",
    "OnBeforeAfter",
    "NotInSearchFilter",
    "PaginationFilter",
    "InAnyFilter",
)

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="base.ModelProtocol")
StatementFilterT = TypeVar("StatementFilterT", bound="StatementFilter")
FilterTypes: TypeAlias = "BeforeAfter | OnBeforeAfter | CollectionFilter[Any] | LimitOffset | OrderBy | SearchFilter | NotInCollectionFilter[Any] | NotInSearchFilter"
"""Aggregate type alias of the types supported for collection filtering."""


class StatementFilter(ABC):
    @abstractmethod
    def append_to_statement(self, statement: Select[tuple[ModelT]], model: type[ModelT]) -> Select[tuple[ModelT]]:
        return statement

    @abstractmethod
    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        *args: Any,
        **kwargs: Any,
    ) -> StatementLambdaElement:
        return statement

    @staticmethod
    def _get_instrumented_attr(model: Any, key: str | InstrumentedAttribute[Any]) -> InstrumentedAttribute[Any]:
        # copy this here to avoid a circular import of `get_instrumented_attribute`.  Maybe we move that function somewhere else?
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

    def append_to_statement(self, statement: Select[tuple[ModelT]], model: type[ModelT]) -> Select[tuple[ModelT]]:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.before is not None:
            statement = statement.where(field < self.before)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if self.after is not None:
            statement = statement.where(field > self.after)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
    ) -> StatementLambdaElement:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.before is not None:
            before = self.before
            statement += lambda s: s.where(field < before)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if self.after is not None:
            after = self.after
            statement += lambda s: s.where(field > after)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
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

    def append_to_statement(self, statement: Select[tuple[ModelT]], model: type[ModelT]) -> Select[tuple[ModelT]]:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.on_or_before is not None:
            statement = statement.where(field <= self.on_or_before)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if self.on_or_after is not None:
            statement = statement.where(field >= self.on_or_after)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
    ) -> StatementLambdaElement:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.on_or_before is not None:
            on_or_before = self.on_or_before
            statement += lambda s: s.where(field <= on_or_before)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if self.on_or_after is not None:
            on_or_after = self.on_or_after
            statement += lambda s: s.where(field >= on_or_after)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
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
        statement: Select[tuple[ModelT]],
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> Select[tuple[ModelT]]:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.values is None:
            return statement.where(text("1=1"))
        if prefer_any:
            return statement.where(any_(self.values) == field)  # type: ignore[arg-type]
        return statement.where(field.in_(self.values))

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> StatementLambdaElement:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.values is None:
            statement += lambda s: s.where(text("1=1"))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
            return statement
        if prefer_any:
            values = self.values
            statement += lambda s: s.where(any_(values) == field)  # type: ignore[arg-type]
            return statement
        values = self.values
        statement += lambda s: s.where(field.in_(values))  # pyright: ignore[reportUnknownLambdaType,reportArgumentType,reportUnknownMemberType]
        return statement


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
        statement: Select[tuple[ModelT]],
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> Select[tuple[ModelT]]:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.values is None:
            return statement.where(text("1=-1"))
        if prefer_any:
            return statement.where(any_(self.values) == field)  # type: ignore[arg-type]
        return statement.where(field.in_(self.values))

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
        prefer_any: bool = False,
    ) -> StatementLambdaElement:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.values is None:
            statement += lambda s: s.where(text("1=-1"))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
            return statement
        if prefer_any:
            values = self.values
            statement += lambda s: s.where(any_(values) != field)  # type: ignore[arg-type]
            return statement
        values = self.values
        statement += lambda s: s.where(field.notin_(values))  # pyright: ignore[reportUnknownLambdaType,reportArgumentType,reportUnknownMemberType]
        return statement


class PaginationFilter(StatementFilter, ABC):
    """Subclass for methods that function as a pagination type."""


@dataclass
class LimitOffset(PaginationFilter):
    """Data required to add limit/offset filtering to a query."""

    limit: int
    """Value for ``LIMIT`` clause of query."""
    offset: int
    """Value for ``OFFSET`` clause of query."""

    def append_to_statement(self, statement: Select[tuple[ModelT]], model: type[ModelT]) -> Select[tuple[ModelT]]:
        return statement.limit(self.limit).offset(self.offset)

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
    ) -> StatementLambdaElement:
        limit = self.limit
        offset = self.offset
        statement += lambda s: s.limit(limit).offset(offset)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement


@dataclass
class OrderBy(StatementFilter):
    """Data required to construct a ``ORDER BY ...`` clause."""

    field_name: str
    """Name of the model attribute to sort on."""
    sort_order: Literal["asc", "desc"] = "asc"
    """Sort ascending or descending"""

    def append_to_statement(self, statement: Select[tuple[ModelT]], model: type[ModelT]) -> Select[tuple[ModelT]]:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.sort_order == "desc":
            return statement.order_by(field.desc())
        return statement.order_by(field.asc())

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
    ) -> StatementLambdaElement:
        field = self._get_instrumented_attr(model, self.field_name)
        if self.sort_order == "desc":
            statement += lambda s: s.order_by(field.desc())  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
            return statement
        statement += lambda s: s.order_by(field.asc())  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement


@dataclass
class SearchFilter(StatementFilter):
    """Data required to construct a ``WHERE field_name LIKE '%' || :value || '%'`` clause."""

    field_name: str
    """Name of the model attribute to sort on."""
    value: str
    """Values for ``LIKE`` clause."""
    ignore_case: bool | None = False
    """Should the search be case insensitive."""

    def append_to_statement(
        self,
        statement: Select[tuple[ModelT]],
        model: type[ModelT],
    ) -> Select[tuple[ModelT]]:
        field = self._get_instrumented_attr(model, self.field_name)
        search_text = f"%{self.value}%"
        if self.ignore_case:
            return statement.where(field.ilike(search_text))
        return statement.where(field.like(search_text))

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
    ) -> StatementLambdaElement:
        field = self._get_instrumented_attr(model, self.field_name)
        search_text = f"%{self.value}%"
        if self.ignore_case:
            statement += lambda s: s.where(field.ilike(search_text))  # pyright: ignore[reportUnknownLambdaType,reportArgumentType,reportUnknownMemberType]
            return statement
        statement += lambda s: s.where(field.like(search_text))  # pyright: ignore[reportUnknownLambdaType,reportArgumentType,reportUnknownMemberType]
        return statement


@dataclass
class NotInSearchFilter(StatementFilter):
    """Data required to construct a ``WHERE field_name NOT LIKE '%' || :value || '%'`` clause."""

    field_name: str
    """Name of the model attribute to search on."""
    value: str
    """Values for ``NOT LIKE`` clause."""
    ignore_case: bool | None = False
    """Should the search be case insensitive."""

    def append_to_statement(
        self,
        statement: Select[tuple[ModelT]],
        model: type[ModelT],
    ) -> Select[tuple[ModelT]]:
        field = self._get_instrumented_attr(model, self.field_name)
        search_text = f"%{self.value}%"
        if self.ignore_case:
            return statement.where(field.not_ilike(search_text))
        return statement.where(field.not_like(search_text))

    def append_to_lambda_statement(
        self,
        statement: StatementLambdaElement,
        model: type[ModelT],
    ) -> StatementLambdaElement:
        field = self._get_instrumented_attr(model, self.field_name)
        search_text = f"%{self.value}%"
        if self.ignore_case:
            statement += lambda s: s.where(field.not_ilike(search_text))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
            return statement
        statement += lambda s: s.where(field.not_like(search_text))  # pyright: ignore[reportUnknownLambdaType,reportArgumentType,reportUnknownMemberType]
        return statement

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Iterable, cast

from sqlalchemy import (
    StatementLambdaElement,
    any_,
    text,
)
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement

from advanced_alchemy.exceptions import RepositoryError
from advanced_alchemy.exceptions import wrap_sqlalchemy_exception as _wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    FilterTypes,
    LimitOffset,
    NotInCollectionFilter,
    NotInSearchFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.repository.typing import ModelT

if TYPE_CHECKING:
    from collections import abc
    from datetime import datetime

    from sqlalchemy.orm import InstrumentedAttribute

    from advanced_alchemy.base import ModelProtocol

# NOTE: For backward compatibility with Litestar - this is imported from here within the litestar codebase.
wrap_sqlalchemy_exception = _wrap_sqlalchemy_exception


def get_instrumented_attr(
    model: type[ModelProtocol],
    key: str | InstrumentedAttribute[Any],
) -> InstrumentedAttribute[Any]:
    if isinstance(key, str):
        return cast("InstrumentedAttribute[Any]", getattr(model, key))
    return key


def model_from_dict(model: ModelT, **kwargs: Any) -> ModelT:
    """Return ORM Object from Dictionary."""
    data = {
        column_name: kwargs[column_name]
        for column_name in model.__mapper__.columns.keys()  # noqa: SIM118  # pyright: ignore[reportUnknownMemberType]
        if column_name in kwargs
    }
    return cast("ModelT", model(**data))  # type: ignore[operator]


class FilterableRepository(Generic[ModelT]):
    model_type: type[ModelT]
    _prefer_any: bool = False
    prefer_any_dialects: tuple[str] | None = ("postgresql",)
    """List of dialects that prefer to use ``field.id = ANY(:1)`` instead of ``field.id IN (...)``."""

    def _apply_limit_offset_pagination(
        self,
        limit: int,
        offset: int,
        statement: StatementLambdaElement,
    ) -> StatementLambdaElement:
        statement += lambda s: s.limit(limit).offset(offset)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _apply_filters(
        self,
        *filters: FilterTypes | ColumnElement[bool],
        apply_pagination: bool = True,
        statement: StatementLambdaElement,
    ) -> StatementLambdaElement:
        """Apply filters to a select statement.

        Args:
            *filters: filter types to apply to the query
            apply_pagination: applies pagination filters if true
            statement: select statement to apply filters

        Keyword Args:
            select: select to apply filters against

        Returns:
            The select with filters applied.
        """
        for filter_ in filters:
            if isinstance(filter_, (LimitOffset,)):
                if apply_pagination:
                    statement = self._apply_limit_offset_pagination(filter_.limit, filter_.offset, statement=statement)
            elif isinstance(filter_, (BeforeAfter,)):
                statement = self._filter_on_datetime_field(
                    field_name=filter_.field_name,
                    before=filter_.before,
                    after=filter_.after,
                    statement=statement,
                )
            elif isinstance(filter_, (OnBeforeAfter,)):
                statement = self._filter_on_datetime_field(
                    field_name=filter_.field_name,
                    on_or_before=filter_.on_or_before,
                    on_or_after=filter_.on_or_after,
                    statement=statement,
                )

            elif isinstance(filter_, (NotInCollectionFilter,)):
                if filter_.values is not None:
                    if self._prefer_any:
                        statement = self._filter_not_any_collection(
                            filter_.field_name,
                            filter_.values,
                            statement=statement,
                        )
                    else:
                        statement = self._filter_not_in_collection(
                            filter_.field_name,
                            filter_.values,
                            statement=statement,
                        )

            elif isinstance(filter_, (CollectionFilter,)):
                if filter_.values is not None:
                    if self._prefer_any:
                        statement = self._filter_any_collection(filter_.field_name, filter_.values, statement=statement)
                    else:
                        statement = self._filter_in_collection(filter_.field_name, filter_.values, statement=statement)
            elif isinstance(filter_, (OrderBy,)):
                statement = self._order_by(statement, filter_.field_name, sort_desc=filter_.sort_order == "desc")
            elif isinstance(filter_, (SearchFilter,)):
                statement = self._filter_by_like(
                    statement,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                )
            elif isinstance(filter_, (NotInSearchFilter,)):
                statement = self._filter_by_not_like(
                    statement,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                )
            elif isinstance(filter_, ColumnElement):  # pyright: ignore[reportUnnecessaryIsInstance]
                statement = self._filter_by_expression(expression=filter_, statement=statement)
            else:
                msg = f"Unexpected filter: {filter_}"  # type: ignore[unreachable]
                raise RepositoryError(msg)
        return statement

    def _filter_in_collection(
        self,
        field_name: str | InstrumentedAttribute[Any],
        values: abc.Collection[Any],
        statement: StatementLambdaElement,
    ) -> StatementLambdaElement:
        if not values:
            statement += lambda s: s.where(text("1=-1"))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
            return statement
        field = get_instrumented_attr(self.model_type, field_name)
        statement += lambda s: s.where(field.in_(values))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _filter_not_in_collection(
        self,
        field_name: str | InstrumentedAttribute[Any],
        values: abc.Collection[Any],
        statement: StatementLambdaElement,
    ) -> StatementLambdaElement:
        if not values:
            return statement
        field = get_instrumented_attr(self.model_type, field_name)
        statement += lambda s: s.where(field.notin_(values))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _filter_any_collection(
        self,
        field_name: str | InstrumentedAttribute[Any],
        values: abc.Collection[Any],
        statement: StatementLambdaElement,
    ) -> StatementLambdaElement:
        if not values:
            statement += lambda s: s.where(text("1=-1"))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
            return statement
        field = get_instrumented_attr(self.model_type, field_name)
        statement += lambda s: s.where(any_(values) == field)  # type: ignore[arg-type]
        return statement

    def _filter_not_any_collection(
        self,
        field_name: str | InstrumentedAttribute[Any],
        values: abc.Collection[Any],
        statement: StatementLambdaElement,
    ) -> StatementLambdaElement:
        if not values:
            return statement
        field = get_instrumented_attr(self.model_type, field_name)
        statement += lambda s: s.where(any_(values) != field)  # type: ignore[arg-type]
        return statement

    def _filter_on_datetime_field(
        self,
        field_name: str | InstrumentedAttribute[Any],
        statement: StatementLambdaElement,
        before: datetime | None = None,
        after: datetime | None = None,
        on_or_before: datetime | None = None,
        on_or_after: datetime | None = None,
    ) -> StatementLambdaElement:
        field = get_instrumented_attr(self.model_type, field_name)
        if before is not None:
            statement += lambda s: s.where(field < before)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if after is not None:
            statement += lambda s: s.where(field > after)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if on_or_before is not None:
            statement += lambda s: s.where(field <= on_or_before)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        if on_or_after is not None:
            statement += lambda s: s.where(field >= on_or_after)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _filter_select_by_kwargs(
        self,
        statement: StatementLambdaElement,
        kwargs: dict[Any, Any] | Iterable[tuple[Any, Any]],
    ) -> StatementLambdaElement:
        for key, val in dict(kwargs).items():
            statement = self._filter_by_where(statement=statement, field_name=key, value=val)
        return statement

    def _filter_by_expression(
        self,
        statement: StatementLambdaElement,
        expression: ColumnElement[bool],
    ) -> StatementLambdaElement:
        statement += lambda s: s.where(expression)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _filter_by_where(
        self,
        statement: StatementLambdaElement,
        field_name: str | InstrumentedAttribute[Any],
        value: Any,
    ) -> StatementLambdaElement:
        field = get_instrumented_attr(self.model_type, field_name)
        statement += lambda s: s.where(field == value)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _filter_by_like(
        self,
        statement: StatementLambdaElement,
        field_name: str | InstrumentedAttribute[Any],
        value: str,
        ignore_case: bool,
    ) -> StatementLambdaElement:
        field = get_instrumented_attr(self.model_type, field_name)
        search_text = f"%{value}%"
        if ignore_case:
            statement += lambda s: s.where(field.ilike(search_text))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        else:
            statement += lambda s: s.where(field.like(search_text))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _filter_by_not_like(
        self,
        statement: StatementLambdaElement,
        field_name: str | InstrumentedAttribute[Any],
        value: str,
        ignore_case: bool,
    ) -> StatementLambdaElement:
        field = get_instrumented_attr(self.model_type, field_name)
        search_text = f"%{value}%"
        if ignore_case:
            statement += lambda s: s.where(field.not_ilike(search_text))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        else:
            statement += lambda s: s.where(field.not_like(search_text))  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

    def _order_by(
        self,
        statement: StatementLambdaElement,
        field_name: str | InstrumentedAttribute[Any],
        sort_desc: bool = False,
    ) -> StatementLambdaElement:
        field = get_instrumented_attr(self.model_type, field_name)
        if sort_desc:
            statement += lambda s: s.order_by(field.desc())  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        else:
            statement += lambda s: s.order_by(field.asc())  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

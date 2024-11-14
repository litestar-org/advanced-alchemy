from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Literal, Protocol, Sequence, Union, cast, overload

from sqlalchemy import (
    Select,
)
from sqlalchemy.orm import InstrumentedAttribute, MapperProperty, RelationshipProperty, joinedload, selectinload
from sqlalchemy.orm.strategy_options import (
    _AbstractLoad,  # pyright: ignore[reportPrivateUsage]  # pyright: ignore[reportPrivateUsage]
)
from sqlalchemy.sql import ColumnElement, ColumnExpressionArgument
from sqlalchemy.sql.base import ExecutableOption
from typing_extensions import TypeAlias

from advanced_alchemy.exceptions import ErrorMessages
from advanced_alchemy.exceptions import wrap_sqlalchemy_exception as _wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    InAnyFilter,
    PaginationFilter,
    StatementFilter,
    StatementTypeT,
)
from advanced_alchemy.repository.typing import ModelT, OrderingPair

if TYPE_CHECKING:
    from sqlalchemy import (
        Delete,
        Dialect,
        Update,
    )
    from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate

    from advanced_alchemy.base import ModelProtocol


WhereClauseT = ColumnExpressionArgument[bool]
SingleLoad: TypeAlias = Union[
    _AbstractLoad,
    Literal["*"],
    InstrumentedAttribute[Any],
    RelationshipProperty[Any],
    MapperProperty[Any],
]
LoadCollection: TypeAlias = Sequence[Union[SingleLoad, Sequence[SingleLoad]]]
ExecutableOptions: TypeAlias = Sequence[ExecutableOption]
LoadSpec: TypeAlias = Union[LoadCollection, SingleLoad, ExecutableOption, ExecutableOptions]

OrderByT: TypeAlias = Union[
    str,
    InstrumentedAttribute[Any],
    RelationshipProperty[Any],
]

# NOTE: For backward compatibility with Litestar - this is imported from here within the litestar codebase.
wrap_sqlalchemy_exception = _wrap_sqlalchemy_exception

DEFAULT_ERROR_MESSAGE_TEMPLATES: ErrorMessages = {
    "integrity": "There was a data validation error during processing",
    "foreign_key": "A foreign key is missing or invalid",
    "multiple_rows": "Multiple matching rows found",
    "duplicate_key": "A record matching the supplied data already exists.",
    "other": "There was an error during data processing",
    "check_constraint": "The data failed a check constraint during processing",
}


def get_instrumented_attr(
    model: type[ModelProtocol],
    key: str | InstrumentedAttribute[Any],
) -> InstrumentedAttribute[Any]:
    if isinstance(key, str):
        return cast("InstrumentedAttribute[Any]", getattr(model, key))
    return key


def model_from_dict(model: type[ModelT], **kwargs: Any) -> ModelT:
    """Return ORM Object from Dictionary."""
    data = {
        column_name: kwargs[column_name]
        for column_name in model.__mapper__.columns.keys()  # noqa: SIM118  # pyright: ignore[reportUnknownMemberType]
        if column_name in kwargs
    }
    return model(**data)


def get_abstract_loader_options(
    loader_options: LoadSpec | None,
    default_loader_options: list[_AbstractLoad] | None = None,
    default_options_have_wildcards: bool = False,
) -> tuple[list[_AbstractLoad], bool]:
    loads: list[_AbstractLoad] = default_loader_options if default_loader_options is not None else []
    options_have_wildcards = default_options_have_wildcards
    if loader_options is None:
        return (loads, options_have_wildcards)
    if isinstance(loader_options, _AbstractLoad):
        return ([loader_options], options_have_wildcards)
    if isinstance(loader_options, InstrumentedAttribute):
        loader_options = [loader_options.property]
    if isinstance(loader_options, RelationshipProperty):
        class_ = loader_options.class_attribute
        return (
            [selectinload(class_)]
            if loader_options.uselist
            else [joinedload(class_, innerjoin=loader_options.innerjoin)],
            options_have_wildcards if loader_options.uselist else True,
        )
    if isinstance(loader_options, str) and loader_options == "*":
        options_have_wildcards = True
        return ([joinedload("*")], options_have_wildcards)
    if isinstance(loader_options, (list, tuple)):
        for attribute in loader_options:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(attribute, (list, tuple)):
                load_chain, options_have_wildcards = get_abstract_loader_options(
                    loader_options=attribute,  # pyright: ignore[reportUnknownArgumentType]
                    default_options_have_wildcards=options_have_wildcards,
                )
                loader = load_chain[-1]
                for sub_load in load_chain[-2::-1]:
                    loader = sub_load.options(loader)
                loads.append(loader)
            else:
                load_chain, options_have_wildcards = get_abstract_loader_options(
                    loader_options=attribute,  # pyright: ignore[reportUnknownArgumentType]
                    default_options_have_wildcards=options_have_wildcards,
                )
                loads.extend(load_chain)
    return (loads, options_have_wildcards)


class FilterableRepositoryProtocol(Protocol[ModelT]):
    model_type: type[ModelT]


class FilterableRepository(FilterableRepositoryProtocol[ModelT]):
    model_type: type[ModelT]
    _prefer_any: bool = False
    _dialect: Dialect
    prefer_any_dialects: tuple[str] | None = ("postgresql",)
    """List of dialects that prefer to use ``field.id = ANY(:1)`` instead of ``field.id IN (...)``."""
    order_by: list[OrderingPair] | OrderingPair | None = None
    """List of ordering pairs to use for sorting."""

    @overload
    def _apply_filters(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        apply_pagination: bool = True,
        statement: Select[tuple[ModelT]],
    ) -> Select[tuple[ModelT]]: ...

    @overload
    def _apply_filters(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        apply_pagination: bool = True,
        statement: Delete,
    ) -> Delete: ...

    @overload
    def _apply_filters(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        apply_pagination: bool = True,
        statement: ReturningDelete[tuple[ModelT]] | ReturningUpdate[tuple[ModelT]],
    ) -> ReturningDelete[tuple[ModelT]] | ReturningUpdate[tuple[ModelT]]: ...

    @overload
    def _apply_filters(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        apply_pagination: bool = True,
        statement: Update,
    ) -> Update: ...

    def _apply_filters(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        apply_pagination: bool = True,
        statement: StatementTypeT,
    ) -> StatementTypeT:
        """Apply filters to a select statement.

        Args:
            *filters: filter types to apply to the query
            apply_pagination: applies pagination filters if true
            statement: select statement to apply filters

        Returns:
            The select with filters applied.
        """
        for filter_ in filters:
            if isinstance(filter_, (PaginationFilter,)):
                if apply_pagination:
                    statement = filter_.append_to_statement(statement, self.model_type)
            elif isinstance(filter_, (InAnyFilter,)):
                statement = filter_.append_to_statement(statement, self.model_type)
            elif isinstance(filter_, ColumnElement):
                statement = cast("StatementTypeT", statement.where(filter_))
            else:
                statement = filter_.append_to_statement(statement, self.model_type)
        return statement

    def _filter_select_by_kwargs(
        self,
        statement: StatementTypeT,
        kwargs: dict[Any, Any] | Iterable[tuple[Any, Any]],
    ) -> StatementTypeT:
        for key, val in dict(kwargs).items():
            field = get_instrumented_attr(self.model_type, key)
            statement = cast("StatementTypeT", statement.where(field == val))
        return statement

    def _apply_order_by(
        self,
        statement: StatementTypeT,
        order_by: list[tuple[str | InstrumentedAttribute[Any], bool]] | tuple[str | InstrumentedAttribute[Any], bool],
    ) -> StatementTypeT:
        if not isinstance(order_by, list):
            order_by = [order_by]
        for order_field, is_desc in order_by:
            field = get_instrumented_attr(self.model_type, order_field)
            statement = self._order_by_attribute(statement, field, is_desc)
        return statement

    def _order_by_attribute(
        self,
        statement: StatementTypeT,
        field: InstrumentedAttribute[Any],
        is_desc: bool,
    ) -> StatementTypeT:
        if not isinstance(statement, Select):
            return statement
        return cast("StatementTypeT", statement.order_by(field.desc() if is_desc else field.asc()))

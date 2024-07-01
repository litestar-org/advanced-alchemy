from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    List,
    Literal,
    Protocol,
    Sequence,
    Tuple,
    Union,
    cast,
)

from sqlalchemy.orm import InstrumentedAttribute, MapperProperty, RelationshipProperty, joinedload, selectinload
from sqlalchemy.orm.strategy_options import (
    _AbstractLoad,  # pyright: ignore[reportPrivateUsage]  # pyright: ignore[reportPrivateUsage]
)
from sqlalchemy.sql import ColumnElement, ColumnExpressionArgument
from sqlalchemy.sql.base import ExecutableOption
from typing_extensions import TypeAlias

from advanced_alchemy.exceptions import wrap_sqlalchemy_exception as _wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    InAnyFilter,
    PaginationFilter,
    StatementFilter,
)
from advanced_alchemy.repository.typing import ModelT, OrderingPair

if TYPE_CHECKING:
    from sqlalchemy import (
        StatementLambdaElement,
    )

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
    default_loader_options: List[_AbstractLoad] | None = None,  # noqa: UP006
    default_options_have_wildcards: bool = False,
) -> Tuple[List[_AbstractLoad], bool]:  # noqa: UP006
    loads: List[_AbstractLoad] = default_loader_options if default_loader_options is not None else []  # noqa: UP006
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
    prefer_any_dialects: tuple[str] | None = ("postgresql",)
    """List of dialects that prefer to use ``field.id = ANY(:1)`` instead of ``field.id IN (...)``."""
    order_by: list[OrderingPair] | OrderingPair | None = None
    """List of ordering pairs to use for sorting."""

    def _apply_filters(
        self,
        *filters: StatementFilter | ColumnElement[bool],
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
            if isinstance(filter_, (PaginationFilter,)):
                if apply_pagination:
                    statement = filter_.append_to_lambda_statement(statement, self.model_type)
            elif isinstance(filter_, (InAnyFilter,)):
                statement = filter_.append_to_lambda_statement(statement, self.model_type, prefer_any=self._prefer_any)
            elif isinstance(filter_, ColumnElement):
                statement = self._filter_by_expression(expression=filter_, statement=statement)
            else:
                statement = filter_.append_to_lambda_statement(statement, self.model_type)
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

    def _apply_order_by(
        self,
        statement: StatementLambdaElement,
        order_by: list[tuple[str | InstrumentedAttribute[Any], bool]] | tuple[str | InstrumentedAttribute[Any], bool],
    ) -> StatementLambdaElement:
        if not isinstance(order_by, list):
            order_by = [order_by]
        for order_field, is_desc in order_by:
            field = get_instrumented_attr(self.model_type, order_field)
            statement = self._order_by_attribute(statement, field, is_desc)
        return statement

    def _order_by_attribute(
        self,
        statement: StatementLambdaElement,
        field: InstrumentedAttribute[Any],
        is_desc: bool,
    ) -> StatementLambdaElement:
        fragment = field.desc() if is_desc else field.asc()
        statement += lambda s: s.order_by(fragment)  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
        return statement

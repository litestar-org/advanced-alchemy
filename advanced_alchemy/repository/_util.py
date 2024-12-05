from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Literal, Protocol, Sequence, Union, cast, overload

from sqlalchemy import (
    Select,
)
from sqlalchemy.orm import (
    InstrumentedAttribute,
    MapperProperty,
    RelationshipProperty,
    joinedload,
    lazyload,
    selectinload,
)
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
"""Default error messages for repository errors."""


def get_instrumented_attr(
    model: type[ModelProtocol],
    key: str | InstrumentedAttribute[Any],
) -> InstrumentedAttribute[Any]:
    """Get an instrumented attribute from a model.

    Args:
        model: SQLAlchemy model class.
        key: Either a string attribute name or an :class:`sqlalchemy.orm.InstrumentedAttribute`.

    Returns:
        :class:`sqlalchemy.orm.InstrumentedAttribute`: The instrumented attribute from the model.
    """
    if isinstance(key, str):
        return cast("InstrumentedAttribute[Any]", getattr(model, key))
    return key


def model_from_dict(model: type[ModelT], **kwargs: Any) -> ModelT:
    """Create an ORM model instance from a dictionary of attributes.

    Args:
        model: The SQLAlchemy model class to instantiate.
        **kwargs: Keyword arguments containing model attribute values.

    Returns:
        ModelT: A new instance of the model populated with the provided values.
    """
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
    merge_with_default: bool = True,
    inherit_lazy_relationships: bool = True,
    cycle_count: int = 0,
) -> tuple[list[_AbstractLoad], bool]:
    """Generate SQLAlchemy loader options for eager loading relationships.

    Args:
        loader_options :class:`~advanced_alchemy.repository.typing.LoadSpec`|:class:`None`  Specification for how to load relationships. Can be:
            - None: Use defaults
            - :class:`sqlalchemy.orm.strategy_options._AbstractLoad`: Direct SQLAlchemy loader option
            - :class:`sqlalchemy.orm.InstrumentedAttribute`: Model relationship attribute
            - :class:`sqlalchemy.orm.RelationshipProperty`: SQLAlchemy relationship
            - str: "*" for wildcard loading
            - :class:`typing.Sequence` of the above
        default_loader_options: :class:`typing.Sequence` of :class:`sqlalchemy.orm.strategy_options._AbstractLoad` loader options to start with.
        default_options_have_wildcards: Whether the default options contain wildcards.
        merge_with_default: Whether to merge the default options with the loader options.
        inherit_lazy_relationships: Whether to inherit the ``lazy`` configuration from the model's relationships.
        cycle_count: Number of times this function has been called recursively.

    Returns:
        tuple[:class:`list`[:class:`sqlalchemy.orm.strategy_options._AbstractLoad`], bool]: A tuple containing:
            - :class:`list` of :class:`sqlalchemy.orm.strategy_options._AbstractLoad` SQLAlchemy loader option objects
            - Boolean indicating if any wildcard loaders are present
    """
    loads: list[_AbstractLoad] = []
    if cycle_count == 0 and not inherit_lazy_relationships:
        loads.append(lazyload("*"))
    if cycle_count == 0 and merge_with_default and default_loader_options is not None:
        loads.extend(default_loader_options)
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
                    inherit_lazy_relationships=inherit_lazy_relationships,
                    merge_with_default=merge_with_default,
                    cycle_count=cycle_count + 1,
                )
                loader = load_chain[-1]
                for sub_load in load_chain[-2::-1]:
                    loader = sub_load.options(loader)
                loads.append(loader)
            else:
                load_chain, options_have_wildcards = get_abstract_loader_options(
                    loader_options=attribute,  # pyright: ignore[reportUnknownArgumentType]
                    default_options_have_wildcards=options_have_wildcards,
                    inherit_lazy_relationships=inherit_lazy_relationships,
                    merge_with_default=merge_with_default,
                    cycle_count=cycle_count + 1,
                )
                loads.extend(load_chain)
    return (loads, options_have_wildcards)


class FilterableRepositoryProtocol(Protocol[ModelT]):
    """Protocol defining the interface for filterable repositories.

    This protocol defines the required attributes and methods that any
    filterable repository implementation must provide.

    Type Parameters:
        ModelT: :class:`~advanced_alchemy.base.ModelProtocol` The SQLAlchemy model type this repository handles.

    Attributes:
        model_type: :class:`~advanced_alchemy.base.ModelProtocol` The SQLAlchemy model class this repository manages.
    """

    model_type: type[ModelT]


class FilterableRepository(FilterableRepositoryProtocol[ModelT]):
    """Default implementation of a filterable repository.

    Provides core filtering, ordering and pagination functionality for
    SQLAlchemy models.

    Type Parameters:
        ModelT: :class:`~advanced_alchemy.base.ModelProtocol` The SQLAlchemy model type this repository handles.
    """

    model_type: type[ModelT]
    """The SQLAlchemy model class this repository manages."""
    prefer_any_dialects: tuple[str] | None = ("postgresql",)
    """List of dialects that prefer to use ``field.id = ANY(:1)`` instead of ``field.id IN (...)``."""
    order_by: list[OrderingPair] | OrderingPair | None = None
    """List or single :class:`~advanced_alchemy.repository.typing.OrderingPair` to use for sorting."""
    _prefer_any: bool = False
    """Whether to prefer ANY() over IN() in queries."""
    _dialect: Dialect
    """The SQLAlchemy :class:`sqlalchemy.dialects.Dialect` being used."""

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
        """Apply filters to a SQL statement.

        Args:
            *filters: Filter conditions to apply.
            apply_pagination: Whether to apply pagination filters.
            statement: The base SQL statement to filter.

        Returns:
            StatementTypeT: The filtered SQL statement.
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
        """Filter a statement using keyword arguments.

        Args:
            statement: :class:`sqlalchemy.sql.Select` The SQL statement to filter.
            kwargs: Dictionary or iterable of tuples containing filter criteria.
                Keys should be model attribute names, values are what to filter for.

        Returns:
            StatementTypeT: The filtered SQL statement.
        """
        for key, val in dict(kwargs).items():
            field = get_instrumented_attr(self.model_type, key)
            statement = cast("StatementTypeT", statement.where(field == val))
        return statement

    def _apply_order_by(
        self,
        statement: StatementTypeT,
        order_by: list[tuple[str | InstrumentedAttribute[Any], bool]] | tuple[str | InstrumentedAttribute[Any], bool],
    ) -> StatementTypeT:
        """Apply ordering to a SQL statement.

        Args:
            statement: The SQL statement to order.
            order_by: Ordering specification. Either a single tuple or list of tuples where:
                - First element is the field name or :class:`sqlalchemy.orm.InstrumentedAttribute` to order by
                - Second element is a boolean indicating descending (True) or ascending (False)

        Returns:
            StatementTypeT: The ordered SQL statement.
        """
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
        """Apply ordering by a single attribute to a SQL statement.

        Args:
            statement: The SQL statement to order.
            field: The model attribute to order by.
            is_desc: Whether to order in descending (True) or ascending (False) order.

        Returns:
            StatementTypeT: The ordered SQL statement.
        """
        if not isinstance(statement, Select):
            return statement
        return cast("StatementTypeT", statement.order_by(field.desc() if is_desc else field.asc()))

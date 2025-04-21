# ruff: noqa: B008
"""Application dependency providers generators.

This module contains functions to create dependency providers for services and filters.

You should not have modify this module very often and should only be invoked under normal usage.
"""

import datetime
import inspect
from collections.abc import AsyncGenerator, Callable, Generator
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    NamedTuple,
    Optional,
    TypedDict,
    TypeVar,
    Union,
    cast,
    overload,
)
from uuid import UUID

from litestar.di import Provide
from litestar.params import Dependency, Parameter
from typing_extensions import NotRequired

from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    FilterTypes,
    LimitOffset,
    NotInCollectionFilter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.service import (
    Empty,
    EmptyType,
    ErrorMessages,
    LoadSpec,
    ModelT,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.utils.singleton import SingletonMeta
from advanced_alchemy.utils.text import camelize

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig

DTorNone = Optional[datetime.datetime]
StringOrNone = Optional[str]
UuidOrNone = Optional[UUID]
IntOrNone = Optional[int]
BooleanOrNone = Optional[bool]
SortOrder = Literal["asc", "desc"]
SortOrderOrNone = Optional[SortOrder]
AsyncServiceT_co = TypeVar("AsyncServiceT_co", bound=SQLAlchemyAsyncRepositoryService[Any], covariant=True)
SyncServiceT_co = TypeVar("SyncServiceT_co", bound=SQLAlchemySyncRepositoryService[Any], covariant=True)
HashableValue = Union[str, int, float, bool, None]
HashableType = Union[HashableValue, tuple[Any, ...], tuple[tuple[str, Any], ...], tuple[HashableValue, ...]]


class DependencyDefaults:
    FILTERS_DEPENDENCY_KEY: str = "filters"
    """Key for the filters dependency."""
    CREATED_FILTER_DEPENDENCY_KEY: str = "created_filter"
    """Key for the created filter dependency."""
    ID_FILTER_DEPENDENCY_KEY: str = "id_filter"
    """Key for the id filter dependency."""
    LIMIT_OFFSET_FILTER_DEPENDENCY_KEY: str = "limit_offset_filter"
    """Key for the limit offset dependency."""
    UPDATED_FILTER_DEPENDENCY_KEY: str = "updated_filter"
    """Key for the updated filter dependency."""
    ORDER_BY_FILTER_DEPENDENCY_KEY: str = "order_by_filter"
    """Key for the order by dependency."""
    SEARCH_FILTER_DEPENDENCY_KEY: str = "search_filter"
    """Key for the search filter dependency."""
    DEFAULT_PAGINATION_SIZE: int = 20
    """Default pagination size."""


DEPENDENCY_DEFAULTS = DependencyDefaults()


class FieldNameType(NamedTuple):
    """Type for field name and associated type information.

    This allows for specifying both the field name and the expected type for filter values.
    """

    name: str
    """Name of the field to filter on."""
    type_hint: type[Any] = str
    """Type of the filter value. Defaults to str."""


class FilterConfig(TypedDict):
    """Configuration for generating dynamic filters."""

    id_filter: NotRequired[type[Union[UUID, int, str]]]
    """Indicates that the id filter should be enabled.  When set, the type specified will be used for the :class:`CollectionFilter`."""
    id_field: NotRequired[str]
    """The field on the model that stored the primary key or identifier."""
    sort_field: NotRequired[str]
    """The default field to use for the sort filter."""
    sort_order: NotRequired[SortOrder]
    """The default order to use for the sort filter."""
    pagination_type: NotRequired[Literal["limit_offset"]]
    """When set, pagination is enabled based on the type specified."""
    pagination_size: NotRequired[int]
    """The size of the pagination. Defaults to `DEFAULT_PAGINATION_SIZE`."""
    search: NotRequired[Union[str, set[str], list[str]]]
    """Fields to enable search on. Can be a comma-separated string or a set of field names."""
    search_ignore_case: NotRequired[bool]
    """When set, search is case insensitive by default."""
    created_at: NotRequired[bool]
    """When set, created_at filter is enabled."""
    updated_at: NotRequired[bool]
    """When set, updated_at filter is enabled."""
    not_in_fields: NotRequired[Union[FieldNameType, set[FieldNameType], list[Union[str, FieldNameType]]]]
    """Fields that support not-in collection filters. Can be a single field or a set of fields with type information."""
    in_fields: NotRequired[Union[FieldNameType, set[FieldNameType], list[Union[str, FieldNameType]]]]
    """Fields that support in-collection filters. Can be a single field or a set of fields with type information."""


class DependencyCache(metaclass=SingletonMeta):
    """Simple dependency cache for the application.  This is used to help memoize dependencies that are generated dynamically."""

    def __init__(self) -> None:
        self.dependencies: dict[Union[int, str], dict[str, Provide]] = {}

    def add_dependencies(self, key: Union[int, str], dependencies: dict[str, Provide]) -> None:
        self.dependencies[key] = dependencies

    def get_dependencies(self, key: Union[int, str]) -> Optional[dict[str, Provide]]:
        return self.dependencies.get(key)


dep_cache = DependencyCache()


@overload
def create_service_provider(
    service_class: type["AsyncServiceT_co"],
    /,
    statement: "Optional[Select[tuple[ModelT]]]" = None,
    config: "Optional[SQLAlchemyAsyncConfig]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., AsyncGenerator[AsyncServiceT_co, None]]: ...


@overload
def create_service_provider(
    service_class: type["SyncServiceT_co"],
    /,
    statement: "Optional[Select[tuple[ModelT]]]" = None,
    config: "Optional[SQLAlchemySyncConfig]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Generator[SyncServiceT_co, None, None]]: ...


def create_service_provider(
    service_class: type[Union["AsyncServiceT_co", "SyncServiceT_co"]],
    /,
    statement: "Optional[Select[tuple[ModelT]]]" = None,
    config: "Optional[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Union["AsyncGenerator[AsyncServiceT_co, None]", "Generator[SyncServiceT_co,None, None]"]]:
    """Create a dependency provider for a service with a configurable session key.

    Args:
        service_class: The service class inheriting from SQLAlchemyAsyncRepositoryService or SQLAlchemySyncRepositoryService.
        statement: An optional SQLAlchemy Select statement to scope the service.
        config: An optional SQLAlchemy configuration object.
        error_messages: Optional custom error messages for the service.
        load: Optional LoadSpec for eager loading relationships.
        execution_options: Optional dictionary of execution options for SQLAlchemy.
        uniquify: Optional flag to uniquify results.
        count_with_window_function: Optional flag to use window function for counting.

    Returns:
        A dependency provider function suitable for Litestar's DI system.
    """

    session_dependency_key = config.session_dependency_key if config else "db_session"

    if issubclass(service_class, SQLAlchemyAsyncRepositoryService) or service_class is SQLAlchemyAsyncRepositoryService:  # type: ignore[comparison-overlap]
        session_type_annotation = "Optional[AsyncSession]"
        return_type_annotation = AsyncGenerator[service_class, None]  # type: ignore[valid-type]

        async def provide_service_async(*args: Any, **kwargs: Any) -> "AsyncGenerator[AsyncServiceT_co, None]":
            db_session = cast("Optional[AsyncSession]", args[0] if args else kwargs.get(session_dependency_key))
            async with service_class.new(  # type: ignore[union-attr]
                session=db_session,  # type: ignore[arg-type]
                statement=statement,
                config=cast("Optional[SQLAlchemyAsyncConfig]", config),  # type: ignore[arg-type]
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
            ) as service:
                yield service

        session_param = inspect.Parameter(
            name=session_dependency_key,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Dependency(skip_validation=True),
            annotation=session_type_annotation,
        )

        provider_signature = inspect.Signature(
            parameters=[session_param],
            return_annotation=return_type_annotation,
        )
        provide_service_async.__signature__ = provider_signature  # type: ignore[attr-defined]
        provide_service_async.__annotations__ = {
            session_dependency_key: session_type_annotation,
            "return": return_type_annotation,
        }
        return provide_service_async
    session_type_annotation = "Optional[Session]"
    return_type_annotation = Generator[service_class, None, None]  # type: ignore[misc,assignment,valid-type]

    def provide_service_sync(*args: Any, **kwargs: Any) -> "Generator[SyncServiceT_co, None, None]":
        db_session = cast("Optional[Session]", args[0] if args else kwargs.get(session_dependency_key))
        with service_class.new(
            session=db_session,
            statement=statement,
            config=cast("Optional[SQLAlchemySyncConfig]", config),
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            count_with_window_function=count_with_window_function,
        ) as service:
            yield service

    session_param = inspect.Parameter(
        name=session_dependency_key,
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        default=Dependency(skip_validation=True),
        annotation=session_type_annotation,
    )

    provider_signature = inspect.Signature(
        parameters=[session_param],
        return_annotation=return_type_annotation,
    )
    provide_service_sync.__signature__ = provider_signature  # type: ignore[attr-defined]
    provide_service_sync.__annotations__ = {
        session_dependency_key: session_type_annotation,
        "return": return_type_annotation,
    }
    return provide_service_sync


def create_service_dependencies(
    service_class: type[Union["AsyncServiceT_co", "SyncServiceT_co"]],
    /,
    key: str,
    statement: "Optional[Select[tuple[ModelT]]]" = None,
    config: "Optional[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    filters: "Optional[FilterConfig]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
    dep_defaults: "DependencyDefaults" = DEPENDENCY_DEFAULTS,
) -> dict[str, Provide]:
    """Create a dependency provider for the combined filter function.

    Args:
        key: The key to use for the dependency provider.
        service_class: The service class to create a dependency provider for.
        statement: The statement to use for the service.
        config: The configuration to use for the service.
        error_messages: The error messages to use for the service.
        load: The load spec to use for the service.
        execution_options: The execution options to use for the service.
        filters: The filter configuration to use for the service.
        uniquify: Whether to uniquify the service.
        count_with_window_function: Whether to count with a window function.
        dep_defaults: The dependency defaults to use for the service.

    Returns:
        A dictionary of dependency providers for the service.
    """

    if issubclass(service_class, SQLAlchemyAsyncRepositoryService) or service_class is SQLAlchemyAsyncRepositoryService:  # type: ignore[comparison-overlap]
        svc = create_service_provider(  # type: ignore[type-var,misc,unused-ignore]
            service_class,
            statement,
            cast("Optional[SQLAlchemyAsyncConfig]", config),
            error_messages,
            load,
            execution_options,
            uniquify,
            count_with_window_function,
        )
        deps = {key: Provide(svc)}
    else:
        svc = create_service_provider(  # type: ignore[assignment]
            service_class,
            statement,
            cast("Optional[SQLAlchemySyncConfig]", config),
            error_messages,
            load,
            execution_options,
            uniquify,
            count_with_window_function,
        )
        deps = {key: Provide(svc, sync_to_thread=False)}
    if filters:
        deps.update(create_filter_dependencies(filters, dep_defaults))
    return deps


def create_filter_dependencies(
    config: FilterConfig, dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS
) -> dict[str, Provide]:
    """Create a dependency provider for the combined filter function.

    Args:
        config: FilterConfig instance with desired settings.
        dep_defaults: Dependency defaults to use for the filter dependencies

    Returns:
        A dependency provider function for the combined filter function.
    """
    cache_key = hash(_make_hashable(config))
    deps = dep_cache.get_dependencies(cache_key)
    if deps is not None:
        return deps
    deps = _create_statement_filters(config, dep_defaults)
    dep_cache.add_dependencies(cache_key, deps)
    return deps


def _make_hashable(value: Any) -> HashableType:
    """Convert a value into a hashable type.

    This function converts any value into a hashable type by:
    - Converting dictionaries to sorted tuples of (key, value) pairs
    - Converting lists and sets to sorted tuples
    - Preserving primitive types (str, int, float, bool, None)
    - Converting any other type to its string representation

    Args:
        value: Any value that needs to be made hashable.

    Returns:
        A hashable version of the value.
    """
    if isinstance(value, dict):
        # Convert dict to tuple of tuples with sorted keys
        items = []
        for k in sorted(value.keys()):  # pyright: ignore
            v = value[k]  # pyright: ignore
            items.append((str(k), _make_hashable(v)))  # pyright: ignore
        return tuple(items)  # pyright: ignore
    if isinstance(value, (list, set)):
        hashable_items = [_make_hashable(item) for item in value]  # pyright: ignore
        filtered_items = [item for item in hashable_items if item is not None]  # pyright: ignore
        return tuple(sorted(filtered_items, key=str))
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(value)


def _create_statement_filters(  # noqa: C901
    config: FilterConfig, dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS
) -> dict[str, Provide]:
    """Create filter dependencies based on configuration.

    Args:
        config (FilterConfig): Configuration dictionary specifying which filters to enable
        dep_defaults (DependencyDefaults): Dependency defaults to use for the filter dependencies

    Returns:
        dict[str, Provide]: Dictionary of filter provider functions
    """
    filters: dict[str, Provide] = {}

    if config.get("id_filter", False):

        def provide_id_filter(  # pyright: ignore[reportUnknownParameterType]
            ids: Optional[list[str]] = Parameter(query="ids", default=None, required=False),
        ) -> CollectionFilter:  # pyright: ignore[reportMissingTypeArgument]
            return CollectionFilter(field_name=config.get("id_field", "id"), values=ids)

        filters[dep_defaults.ID_FILTER_DEPENDENCY_KEY] = Provide(provide_id_filter, sync_to_thread=False)  # pyright: ignore[reportUnknownArgumentType]

    if config.get("created_at", False):

        def provide_created_filter(
            before: DTorNone = Parameter(query="createdBefore", default=None, required=False),
            after: DTorNone = Parameter(query="createdAfter", default=None, required=False),
        ) -> BeforeAfter:
            return BeforeAfter("created_at", before, after)

        filters[dep_defaults.CREATED_FILTER_DEPENDENCY_KEY] = Provide(provide_created_filter, sync_to_thread=False)

    if config.get("updated_at", False):

        def provide_updated_filter(
            before: DTorNone = Parameter(query="updatedBefore", default=None, required=False),
            after: DTorNone = Parameter(query="updatedAfter", default=None, required=False),
        ) -> BeforeAfter:
            return BeforeAfter("updated_at", before, after)

        filters[dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY] = Provide(provide_updated_filter, sync_to_thread=False)

    if config.get("pagination_type") == "limit_offset":

        def provide_limit_offset_pagination(
            current_page: int = Parameter(ge=1, query="currentPage", default=1, required=False),
            page_size: int = Parameter(
                query="pageSize",
                ge=1,
                default=config.get("pagination_size", dep_defaults.DEFAULT_PAGINATION_SIZE),
                required=False,
            ),
        ) -> LimitOffset:
            return LimitOffset(page_size, page_size * (current_page - 1))

        filters[dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY] = Provide(
            provide_limit_offset_pagination, sync_to_thread=False
        )

    if search_fields := config.get("search"):

        def provide_search_filter(
            search_string: StringOrNone = Parameter(
                title="Field to search",
                query="searchString",
                default=None,
                required=False,
            ),
            ignore_case: BooleanOrNone = Parameter(
                title="Search should be case sensitive",
                query="searchIgnoreCase",
                default=config.get("search_ignore_case", False),
                required=False,
            ),
        ) -> SearchFilter:
            # Handle both string and set input types for search fields
            field_names = set(search_fields.split(",")) if isinstance(search_fields, str) else set(search_fields)

            return SearchFilter(
                field_name=field_names,
                value=search_string,  # type: ignore[arg-type]
                ignore_case=ignore_case or False,
            )

        filters[dep_defaults.SEARCH_FILTER_DEPENDENCY_KEY] = Provide(provide_search_filter, sync_to_thread=False)

    if sort_field := config.get("sort_field"):

        def provide_order_by(
            field_name: StringOrNone = Parameter(
                title="Order by field",
                query="orderBy",
                default=sort_field,
                required=False,
            ),
            sort_order: SortOrderOrNone = Parameter(
                title="Field to search",
                query="sortOrder",
                default=config.get("sort_order", "desc"),
                required=False,
            ),
        ) -> OrderBy:
            return OrderBy(field_name=field_name, sort_order=sort_order)  # type: ignore[arg-type]

        filters[dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY] = Provide(provide_order_by, sync_to_thread=False)

    # Add not_in filter providers
    if not_in_fields := config.get("not_in_fields"):
        # Get all field names, handling both strings and FieldNameType objects
        not_in_fields = {not_in_fields} if isinstance(not_in_fields, (str, FieldNameType)) else not_in_fields

        for field_def in not_in_fields:
            field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def

            def create_not_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType,
            ) -> Callable[..., Optional[NotInCollectionFilter[field_def.type_hint]]]:  # type: ignore
                def provide_not_in_filter(  # pyright: ignore
                    values: Optional[list[field_name.type_hint]] = Parameter(  # type: ignore
                        query=camelize(f"{field_name.name}_not_in"), default=None, required=False
                    ),
                ) -> Optional[NotInCollectionFilter[field_name.type_hint]]:  # type: ignore
                    return (
                        NotInCollectionFilter[field_name.type_hint](field_name=field_name.name, values=values)  # type: ignore
                        if values
                        else None
                    )

                return provide_not_in_filter  # pyright: ignore

            provider = create_not_in_filter_provider(field_def)  # pyright: ignore
            filters[f"{field_def.name}_not_in_filter"] = Provide(provider, sync_to_thread=False)  # pyright: ignore

    # Add in filter providers
    if in_fields := config.get("in_fields"):
        # Get all field names, handling both strings and FieldNameType objects
        in_fields = {in_fields} if isinstance(in_fields, (str, FieldNameType)) else in_fields

        for field_def in in_fields:
            field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def

            def create_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType,
            ) -> Callable[..., Optional[CollectionFilter[field_def.type_hint]]]:  # type: ignore # pyright: ignore
                def provide_in_filter(  # pyright: ignore
                    values: Optional[list[field_name.type_hint]] = Parameter(  # type: ignore # pyright: ignore
                        query=camelize(f"{field_name.name}_in"), default=None, required=False
                    ),
                ) -> Optional[CollectionFilter[field_name.type_hint]]:  # type: ignore # pyright: ignore
                    return (
                        CollectionFilter[field_name.type_hint](field_name=field_name.name, values=values)  # type: ignore  # pyright: ignore
                        if values
                        else None
                    )

                return provide_in_filter  # pyright: ignore

            provider = create_in_filter_provider(field_def)  # type: ignore
            filters[f"{field_def.name}_in_filter"] = Provide(provider, sync_to_thread=False)  # pyright: ignore

    if filters:
        filters[dep_defaults.FILTERS_DEPENDENCY_KEY] = Provide(
            _create_filter_aggregate_function(config), sync_to_thread=False
        )

    return filters


def _create_filter_aggregate_function(config: FilterConfig) -> Callable[..., list[FilterTypes]]:  # noqa: C901, PLR0915
    """Create a filter function based on the provided configuration.

    Args:
        config: The filter configuration.

    Returns:
        A function that returns a list of filters based on the configuration.
    """

    parameters: dict[str, inspect.Parameter] = {}
    annotations: dict[str, Any] = {}

    # Build parameters based on config
    if cls := config.get("id_filter"):
        parameters["id_filter"] = inspect.Parameter(
            name="id_filter",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Dependency(skip_validation=True),
            annotation=CollectionFilter[cls],  # type: ignore[valid-type]
        )
        annotations["id_filter"] = CollectionFilter[cls]  # type: ignore[valid-type]

    if config.get("created_at"):
        parameters["created_filter"] = inspect.Parameter(
            name="created_filter",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Dependency(skip_validation=True),
            annotation=BeforeAfter,
        )
        annotations["created_filter"] = BeforeAfter

    if config.get("updated_at"):
        parameters["updated_filter"] = inspect.Parameter(
            name="updated_filter",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Dependency(skip_validation=True),
            annotation=BeforeAfter,
        )
        annotations["updated_filter"] = BeforeAfter

    if config.get("search"):
        parameters["search_filter"] = inspect.Parameter(
            name="search_filter",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Dependency(skip_validation=True),
            annotation=SearchFilter,
        )
        annotations["search_filter"] = SearchFilter

    if config.get("pagination_type") == "limit_offset":
        parameters["limit_offset_filter"] = inspect.Parameter(
            name="limit_offset_filter",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Dependency(skip_validation=True),
            annotation=LimitOffset,
        )
        annotations["limit_offset_filter"] = LimitOffset

    if config.get("sort_field"):
        parameters["order_by_filter"] = inspect.Parameter(
            name="order_by_filter",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=Dependency(skip_validation=True),
            annotation=OrderBy,
        )
        annotations["order_by_filter"] = OrderBy

    # Add parameters for not_in filters
    if not_in_fields := config.get("not_in_fields"):
        for field_def in not_in_fields:
            field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def
            parameters[f"{field_def.name}_not_in_filter"] = inspect.Parameter(
                name=f"{field_def.name}_not_in_filter",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Dependency(skip_validation=True),
                annotation=NotInCollectionFilter[field_def.type_hint],  # type: ignore
            )
            annotations[f"{field_def.name}_not_in_filter"] = NotInCollectionFilter[field_def.type_hint]  # type: ignore

    # Add parameters for in filters
    if in_fields := config.get("in_fields"):
        for field_def in in_fields:
            field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def
            parameters[f"{field_def.name}_in_filter"] = inspect.Parameter(
                name=f"{field_def.name}_in_filter",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Dependency(skip_validation=True),
                annotation=CollectionFilter[field_def.type_hint],  # type: ignore
            )
            annotations[f"{field_def.name}_in_filter"] = CollectionFilter[field_def.type_hint]  # type: ignore

    def provide_filters(**kwargs: FilterTypes) -> list[FilterTypes]:
        """Provide filter dependencies based on configuration.

        Args:
            **kwargs: Filter parameters dynamically provided based on configuration.

        Returns:
            list[FilterTypes]: List of configured filters.
        """
        filters: list[FilterTypes] = []
        if id_filter := kwargs.get("id_filter"):
            filters.append(id_filter)
        if created_filter := kwargs.get("created_filter"):
            filters.append(created_filter)
        if limit_offset := kwargs.get("limit_offset_filter"):
            filters.append(limit_offset)
        if updated_filter := kwargs.get("updated_filter"):
            filters.append(updated_filter)
        if (
            (search_filter := cast("Optional[SearchFilter]", kwargs.get("search_filter")))
            and search_filter is not None  # pyright: ignore[reportUnnecessaryComparison]
            and search_filter.field_name is not None  # pyright: ignore[reportUnnecessaryComparison]
            and search_filter.value is not None  # pyright: ignore[reportUnnecessaryComparison]
        ):
            filters.append(search_filter)
        if (
            (order_by := cast("Optional[OrderBy]", kwargs.get("order_by_filter")))
            and order_by is not None  # pyright: ignore[reportUnnecessaryComparison]
            and order_by.field_name is not None  # pyright: ignore[reportUnnecessaryComparison]
        ):
            filters.append(order_by)

        # Add not_in filters
        if not_in_fields := config.get("not_in_fields"):
            # Get all field names, handling both strings and FieldNameType objects
            not_in_fields = {not_in_fields} if isinstance(not_in_fields, (str, FieldNameType)) else not_in_fields
            for field_def in not_in_fields:
                field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def
                filter_ = kwargs.get(f"{field_def.name}_not_in_filter")
                if filter_ is not None:
                    filters.append(filter_)

        # Add in filters
        if in_fields := config.get("in_fields"):
            # Get all field names, handling both strings and FieldNameType objects
            in_fields = {in_fields} if isinstance(in_fields, (str, FieldNameType)) else in_fields
            for field_def in in_fields:
                field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def
                filter_ = kwargs.get(f"{field_def.name}_in_filter")
                if filter_ is not None:
                    filters.append(filter_)
        return filters

    # Set both signature and annotations
    provide_filters.__signature__ = inspect.Signature(  # type: ignore
        parameters=list(parameters.values()),
        return_annotation=list[FilterTypes],
    )
    provide_filters.__annotations__ = annotations
    provide_filters.__annotations__["return"] = list[FilterTypes]

    return provide_filters

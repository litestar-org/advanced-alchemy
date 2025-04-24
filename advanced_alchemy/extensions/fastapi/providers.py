# pyright: ignore
"""Application dependency providers generators for FastAPI.

This module contains functions to create dependency providers for filters,
similar to the Litestar extension, but tailored for FastAPI.
"""

import datetime
import inspect
from collections.abc import AsyncGenerator, Generator
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Literal,
    NamedTuple,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)
from uuid import UUID

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from typing_extensions import NotRequired, TypedDict

from advanced_alchemy.extensions.fastapi.extension import AdvancedAlchemy
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
    from advanced_alchemy.extensions.fastapi import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

T = TypeVar("T")
DTorNone = Optional[datetime.datetime]
StringOrNone = Optional[str]
UuidOrNone = Optional[str]  # FastAPI doesn't automatically parse UUIDs from query params like Litestar
IntOrNone = Optional[int]
BooleanOrNone = Optional[bool]
SortOrder = Literal["asc", "desc"]
SortOrderOrNone = Optional[SortOrder]
FilterConfigValues = Union[
    bool, str, list[str], type[Union[str, int]]
]  # Simplified compared to Litestar's UUID/int flexibility for now
AsyncServiceT_co = TypeVar("AsyncServiceT_co", bound=SQLAlchemyAsyncRepositoryService[Any], covariant=True)
SyncServiceT_co = TypeVar("SyncServiceT_co", bound=SQLAlchemySyncRepositoryService[Any], covariant=True)
HashableValue = Union[str, int, float, bool, None]
HashableType = Union[HashableValue, tuple[Any, ...], tuple[tuple[str, Any], ...], tuple[HashableValue, ...]]


class FieldNameType(NamedTuple):
    """Type for field name and associated type information.

    This allows for specifying both the field name and the expected type for filter values.
    """

    name: str
    """Name of the field to filter on."""
    type_hint: type[Any] = str
    """Type of the filter value. Defaults to str."""


class DependencyDefaults:
    """Default values for dependency generation."""

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


class DependencyCache(metaclass=SingletonMeta):
    """Simple dependency cache for the application.  This is used to help memoize dependencies that are generated dynamically."""

    def __init__(self) -> None:
        self.dependencies: dict[int, Callable[[Any], list[FilterTypes]]] = {}

    def add_dependencies(self, key: int, dependencies: Callable[[Any], list[FilterTypes]]) -> None:
        self.dependencies[key] = dependencies

    def get_dependencies(self, key: int) -> Optional[Callable[[Any], list[FilterTypes]]]:
        return self.dependencies.get(key)


dep_cache = DependencyCache()


class FilterConfig(TypedDict):
    """Configuration for generating dynamic filters for FastAPI."""

    id_filter: NotRequired[type[Union[UUID, int, str]]]
    """Indicates that the id filter should be enabled."""
    id_field: NotRequired[str]
    """The field on the model that stored the primary key or identifier. Defaults to 'id'."""
    sort_field: NotRequired[Union[str, set[str]]]
    """The default field(s) to use for the sort filter."""
    sort_order: NotRequired[SortOrder]
    """The default order to use for the sort filter. Defaults to 'desc'."""
    pagination_type: NotRequired[Literal["limit_offset"]]
    """When set, pagination is enabled based on the type specified."""
    pagination_size: NotRequired[int]
    """The size of the pagination. Defaults to `DEFAULT_PAGINATION_SIZE`."""
    search: NotRequired[Union[str, set[str]]]
    """Fields to enable search on. Can be a comma-separated string or a set of field names."""
    search_ignore_case: NotRequired[bool]
    """When set, search is case insensitive by default. Defaults to False."""
    created_at: NotRequired[bool]
    """When set, created_at filter is enabled. Defaults to 'created_at' field."""
    updated_at: NotRequired[bool]
    """When set, updated_at filter is enabled. Defaults to 'updated_at' field."""
    not_in_fields: NotRequired[Union[FieldNameType, set[FieldNameType]]]
    """Fields that support not-in collection filters. Can be a single field or a set of fields with type information."""
    in_fields: NotRequired[Union[FieldNameType, set[FieldNameType]]]
    """Fields that support in-collection filters. Can be a single field or a set of fields with type information."""


@overload
def provide_service(
    service_class: type["AsyncServiceT_co"],
    /,
    extension: AdvancedAlchemy,
    key: Optional[str] = None,
    statement: Optional[Select[tuple[ModelT]]] = None,
    error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
    load: Optional[LoadSpec] = None,
    execution_options: Optional[dict[str, Any]] = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., AsyncGenerator[AsyncServiceT_co, None]]: ...


@overload
def provide_service(
    service_class: type["SyncServiceT_co"],
    /,
    extension: AdvancedAlchemy,
    key: Optional[str] = None,
    statement: Optional[Select[tuple[ModelT]]] = None,
    error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
    load: Optional[LoadSpec] = None,
    execution_options: Optional[dict[str, Any]] = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Generator[SyncServiceT_co, None, None]]: ...


def provide_service(
    service_class: type[Union["AsyncServiceT_co", "SyncServiceT_co"]],
    /,
    extension: AdvancedAlchemy,
    key: Optional[str] = None,
    statement: Optional[Select[tuple[ModelT]]] = None,
    error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
    load: Optional[LoadSpec] = None,
    execution_options: Optional[dict[str, Any]] = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Union[AsyncGenerator[AsyncServiceT_co, None], Generator[SyncServiceT_co, None, None]]]:
    """Create a dependency provider for a service.

    Returns:
        A dependency provider for the service.
    """
    if issubclass(service_class, SQLAlchemyAsyncRepositoryService) or service_class is SQLAlchemyAsyncRepositoryService:  # type: ignore[comparison-overlap]

        async def provide_async_service(
            db_session: AsyncSession = Depends(extension.provide_session(key)),  # noqa: B008
        ) -> AsyncGenerator[AsyncServiceT_co, None]:  # type: ignore[union-attr,unused-ignore]
            async with service_class.new(  # type: ignore[union-attr,unused-ignore]
                session=db_session,  # type: ignore[arg-type, unused-ignore]
                statement=statement,
                config=cast("Optional[SQLAlchemyAsyncConfig]", extension.get_config(key)),  # type: ignore[arg-type]
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
            ) as service:
                yield service

        return provide_async_service

    def provide_sync_service(
        db_session: Session = Depends(extension.provide_session(key)),  # noqa: B008
    ) -> Generator[SyncServiceT_co, None, None]:
        with service_class.new(
            session=db_session,  # type: ignore[arg-type, unused-ignore]
            statement=statement,
            config=cast("Optional[SQLAlchemySyncConfig]", extension.get_config(key)),
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            count_with_window_function=count_with_window_function,
        ) as service:
            yield service

    return provide_sync_service


def provide_filters(
    config: FilterConfig,
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
) -> Callable[..., list[FilterTypes]]:
    """Create FastAPI dependency providers for filters based on the provided configuration.

    Returns:
        A FastAPI dependency provider function that aggregates multiple filter dependencies.
    """
    # Check if any filters are actually requested in the config
    filter_keys = {
        "id_filter",
        "created_at",
        "updated_at",
        "pagination_type",
        "search",
        "sort_field",
        "not_in_fields",
        "in_fields",
    }

    has_filters = False
    for key in filter_keys:
        value = config.get(key)
        if value is not None and value is not False and value != []:
            has_filters = True
            break

    if not has_filters:
        return list

    # Calculate cache key using hashable version of config
    cache_key = hash(_make_hashable(config))

    # Check cache first
    cached_dep = dep_cache.get_dependencies(cache_key)
    if cached_dep is not None:
        return cached_dep

    dep = _create_filter_aggregate_function_fastapi(config, dep_defaults)
    dep_cache.add_dependencies(cache_key, dep)
    return dep


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


def _create_filter_aggregate_function_fastapi(  # noqa: C901, PLR0915
    config: FilterConfig,
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
) -> Callable[..., list[FilterTypes]]:
    """Create a FastAPI dependency provider function that aggregates multiple filter dependencies.

    Returns:
        A FastAPI dependency provider function that aggregates multiple filter dependencies.
    """
    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}

    # Add id filter providers
    if (id_filter := config.get("id_filter", False)) is not False:

        def provide_id_filter(  # pyright: ignore[reportUnknownParameterType]
            ids: Annotated[  # type: ignore
                Optional[list[id_filter]],  # pyright: ignore
                Query(
                    alias="ids",
                    required=False,
                    description="IDs to filter by.",
                ),
            ] = None,
        ) -> Optional[CollectionFilter[id_filter]]:  # type: ignore
            return CollectionFilter[id_filter](field_name=config.get("id_field", "id"), values=ids) if ids else None  # type: ignore

        params.append(
            inspect.Parameter(
                name=dep_defaults.ID_FILTER_DEPENDENCY_KEY,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[Optional[CollectionFilter[id_filter]], Depends(provide_id_filter)],  # type: ignore
            )
        )
        annotations[dep_defaults.ID_FILTER_DEPENDENCY_KEY] = Annotated[
            Optional[CollectionFilter[id_filter]], Depends(provide_id_filter)  # type: ignore
        ]

    # Add created_at filter providers
    if config.get("created_at", False):

        def provide_created_at_filter(
            before: Annotated[
                Optional[str],
                Query(
                    alias="createdBefore",
                    description="Filter by created date before this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
            after: Annotated[
                Optional[str],
                Query(
                    alias="createdAfter",
                    description="Filter by created date after this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
        ) -> Optional[BeforeAfter]:
            before_dt = None
            after_dt = None

            # Validate both parameters regardless of endpoint path
            if before is not None:
                try:
                    before_dt = datetime.datetime.fromisoformat(before.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", "createdBefore"], "msg": "Invalid date format"}]
                    ) from e

            if after is not None:
                try:
                    after_dt = datetime.datetime.fromisoformat(after.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", "createdAfter"], "msg": "Invalid date format"}]
                    ) from e

            return (
                BeforeAfter(field_name="created_at", before=before_dt, after=after_dt)
                if before_dt or after_dt
                else None  # pyright: ignore
            )

        param_name = dep_defaults.CREATED_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[Optional[BeforeAfter], Depends(provide_created_at_filter)],
            )
        )
        annotations[param_name] = Annotated[Optional[BeforeAfter], Depends(provide_created_at_filter)]

    # Add updated_at filter providers
    if config.get("updated_at", False):

        def provide_updated_at_filter(
            before: Annotated[
                Optional[str],
                Query(
                    alias="updatedBefore",
                    description="Filter by updated date before this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
            after: Annotated[
                Optional[str],
                Query(
                    alias="updatedAfter",
                    description="Filter by updated date after this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
        ) -> Optional[BeforeAfter]:
            before_dt = None
            after_dt = None

            # Validate both parameters regardless of endpoint path
            if before is not None:
                try:
                    before_dt = datetime.datetime.fromisoformat(before.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", "updatedBefore"], "msg": "Invalid date format"}]
                    ) from e

            if after is not None:
                try:
                    after_dt = datetime.datetime.fromisoformat(after.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", "updatedAfter"], "msg": "Invalid date format"}]
                    ) from e

            return (
                BeforeAfter(field_name="updated_at", before=before_dt, after=after_dt)
                if before_dt or after_dt
                else None  # pyright: ignore
            )

        param_name = dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[Optional[BeforeAfter], Depends(provide_updated_at_filter)],
            )
        )
        annotations[param_name] = Annotated[Optional[BeforeAfter], Depends(provide_updated_at_filter)]

    # Add pagination filter providers
    if config.get("pagination_type") == "limit_offset":

        def provide_limit_offset_pagination(
            current_page: Annotated[
                int,
                Query(
                    ge=1,
                    alias="currentPage",
                    description="Page number for pagination.",
                ),
            ] = 1,
            page_size: Annotated[
                int,
                Query(
                    ge=1,
                    alias="pageSize",
                    description="Number of items per page.",
                ),
            ] = config.get("pagination_size", dep_defaults.DEFAULT_PAGINATION_SIZE),
        ) -> LimitOffset:
            return LimitOffset(limit=page_size, offset=page_size * (current_page - 1))

        param_name = dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[LimitOffset, Depends(provide_limit_offset_pagination)],
            )
        )
        annotations[param_name] = Annotated[LimitOffset, Depends(provide_limit_offset_pagination)]

    # Add search filter providers
    if search_fields := config.get("search"):

        def provide_search_filter(
            search_string: Annotated[
                Optional[str],
                Query(
                    required=False,
                    alias="searchString",
                    description="Search term.",
                ),
            ] = None,
            ignore_case: Annotated[
                Optional[bool],
                Query(
                    required=False,
                    alias="searchIgnoreCase",
                    description="Whether search should be case-insensitive.",
                ),
            ] = config.get("search_ignore_case", False),
        ) -> SearchFilter:
            field_names = set(search_fields.split(",")) if isinstance(search_fields, str) else search_fields

            return SearchFilter(
                field_name=field_names,
                value=search_string,  # type: ignore[arg-type]
                ignore_case=ignore_case or False,
            )

        param_name = dep_defaults.SEARCH_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[Optional[SearchFilter], Depends(provide_search_filter)],
            )
        )
        annotations[param_name] = Annotated[Optional[SearchFilter], Depends(provide_search_filter)]

    # Add sort filter providers
    if sort_field := config.get("sort_field"):
        sort_order_default = config.get("sort_order", "desc")

        def provide_order_by(
            field_name: Annotated[
                str,
                Query(
                    alias="orderBy",
                    description="Field to order by.",
                    required=False,
                ),
            ] = sort_field,  # type: ignore[assignment]
            sort_order: Annotated[
                Optional[SortOrder],
                Query(
                    alias="sortOrder",
                    description="Sort order ('asc' or 'desc').",
                    required=False,
                ),
            ] = sort_order_default,
        ) -> OrderBy:
            return OrderBy(field_name=field_name, sort_order=sort_order or sort_order_default)

        param_name = dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[OrderBy, Depends(provide_order_by)],
            )
        )
        annotations[param_name] = Annotated[OrderBy, Depends(provide_order_by)]

    # Add not_in filter providers
    if not_in_fields := config.get("not_in_fields"):
        not_in_fields = {not_in_fields} if isinstance(not_in_fields, (str, FieldNameType)) else not_in_fields
        for field_def in not_in_fields:

            def create_not_in_filter_provider(  # pyright: ignore
                local_field_name: str,
                local_field_type: type[Any],
            ) -> Callable[..., Optional[NotInCollectionFilter[field_def.type_hint]]]:  # type: ignore
                def provide_not_in_filter(  # pyright: ignore
                    values: Annotated[  # type: ignore
                        Optional[set[local_field_type]],  # pyright: ignore
                        Query(
                            alias=camelize(f"{local_field_name}_not_in"),
                            description=f"Filter {local_field_name} not in values",
                        ),
                    ] = None,
                ) -> Optional[NotInCollectionFilter[local_field_type]]:  # type: ignore
                    return NotInCollectionFilter(field_name=local_field_name, values=values) if values else None  # pyright: ignore

                return provide_not_in_filter  # pyright: ignore

            provider = create_not_in_filter_provider(field_def.name, field_def.type_hint)  # pyright: ignore
            param_name = f"{field_def.name}_not_in_filter"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=Annotated[Optional[NotInCollectionFilter[field_def.type_hint]], Depends(provider)],  # type: ignore
                )
            )
            annotations[param_name] = Annotated[Optional[NotInCollectionFilter[field_def.type_hint]], Depends(provider)]  # type: ignore

    # Add in filter providers
    if in_fields := config.get("in_fields"):
        in_fields = {in_fields} if isinstance(in_fields, (str, FieldNameType)) else in_fields
        for field_def in in_fields:

            def create_in_filter_provider(  # pyright: ignore
                local_field_name: str,
                local_field_type: type[Any],
            ) -> Callable[..., Optional[CollectionFilter[field_def.type_hint]]]:  # type: ignore
                def provide_in_filter(  # pyright: ignore
                    values: Annotated[  # type: ignore
                        Optional[set[local_field_type]],  # pyright: ignore
                        Query(
                            alias=camelize(f"{local_field_name}_in"),
                            description=f"Filter {local_field_name} in values",
                        ),
                    ] = None,
                ) -> Optional[CollectionFilter[local_field_type]]:  # type: ignore
                    return CollectionFilter(field_name=local_field_name, values=values) if values else None  # pyright: ignore

                return provide_in_filter  # pyright: ignore

            provider = create_in_filter_provider(field_def.name, field_def.type_hint)  # type: ignore
            param_name = f"{field_def.name}_in_filter"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=Annotated[Optional[CollectionFilter[field_def.type_hint]], Depends(provider)],  # type: ignore
                )
            )
            annotations[param_name] = Annotated[Optional[CollectionFilter[field_def.type_hint]], Depends(provider)]  # type: ignore

    _aggregate_filter_function.__signature__ = inspect.Signature(  # type: ignore
        parameters=params,
        return_annotation=Annotated[list[FilterTypes], Depends(_aggregate_filter_function)],
    )

    return _aggregate_filter_function


def _aggregate_filter_function(**kwargs: Any) -> list[FilterTypes]:
    filters: list[FilterTypes] = []
    for filter_value in kwargs.values():
        if filter_value is None:
            continue
        if isinstance(filter_value, list):
            filters.extend(cast("list[FilterTypes]", filter_value))
        elif isinstance(filter_value, SearchFilter) and filter_value.value is None:  # pyright: ignore # noqa: SIM114
            continue  # type: ignore
        elif isinstance(filter_value, OrderBy) and filter_value.field_name is None:  # pyright: ignore
            continue  # type: ignore
        else:
            filters.append(cast("FilterTypes", filter_value))
    return filters

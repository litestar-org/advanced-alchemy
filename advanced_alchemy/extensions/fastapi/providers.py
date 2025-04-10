# ruff: noqa: B008, C901
"""Application dependency providers generators for FastAPI.

This module contains functions to create dependency providers for filters,
similar to the Litestar extension, but tailored for FastAPI.
"""

import datetime
import inspect
from typing import Any, Callable, Literal, NamedTuple, Optional, TypeVar, Union, cast

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from typing_extensions import NotRequired, TypedDict

from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    FilterTypes,
    LimitOffset,
    NotInCollectionFilter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.utils.singleton import SingletonMeta

# Type aliases
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


class FieldNameType(NamedTuple):
    """Type for field name and associated type information.

    This allows for specifying both the field name and the expected type for filter values.
    """

    name: str
    """Name of the field to filter on."""
    type_hint: type[Any] = str
    """Type of the filter value. Defaults to str."""


HashableValue = Union[str, int, float, bool, None]
HashableType = Union[HashableValue, tuple[Any, ...], tuple[tuple[str, Any], ...], tuple[HashableValue, ...]]

T = TypeVar("T")


class DependencyDefaults:
    """Default values for dependency generation."""

    FILTERS_DEPENDENCY_KEY: str = "filters"
    CREATED_FILTER_DEPENDENCY_KEY: str = "created_filter"
    ID_FILTER_DEPENDENCY_KEY: str = "id_filter"
    LIMIT_OFFSET_DEPENDENCY_KEY: str = "limit_offset"
    UPDATED_FILTER_DEPENDENCY_KEY: str = "updated_filter"
    ORDER_BY_DEPENDENCY_KEY: str = "order_by"
    SEARCH_FILTER_DEPENDENCY_KEY: str = "search_filter"
    DEFAULT_PAGINATION_SIZE: int = 20


DEPENDENCY_DEFAULTS = DependencyDefaults()


class DependencyCache(metaclass=SingletonMeta):
    """Simple dependency cache for the application.  This is used to help memoize dependencies that are generated dynamically."""

    def __init__(self) -> None:
        self.dependencies: dict[int, dict[str, Any]] = {}

    def add_dependencies(self, key: int, dependencies: dict[str, Any]) -> None:
        self.dependencies[key] = dependencies

    def get_dependencies(self, key: int) -> Optional[dict[str, Any]]:
        return self.dependencies.get(key)


dep_cache = DependencyCache()


class FilterConfig(TypedDict):
    """Configuration for generating dynamic filters for FastAPI."""

    id_filter: NotRequired[FilterConfigValues]
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
    created_at: NotRequired[FilterConfigValues]
    """When set, created_at filter is enabled. Defaults to 'created_at' field."""
    updated_at: NotRequired[FilterConfigValues]
    """When set, updated_at filter is enabled. Defaults to 'updated_at' field."""
    not_in_fields: NotRequired[Union[FieldNameType, set[FieldNameType]]]
    """Fields that support not-in collection filters. Can be a single field or a set of fields with type information."""
    in_fields: NotRequired[Union[FieldNameType, set[FieldNameType]]]
    """Fields that support in-collection filters. Can be a single field or a set of fields with type information."""


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
        return tuple(sorted(filtered_items, key=lambda x: str(x)))  # pyright: ignore
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(value)


def _create_filter_aggregate_function_fastapi(  # noqa: PLR0915
    config: FilterConfig, dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS
) -> Callable[..., list[FilterTypes]]:
    """Create a function that aggregates multiple filter dependencies.

    Args:
        config: Configuration dictionary specifying which fields to create filters for.
        dep_defaults: Dependency defaults instance.

    Returns:
        A function that combines multiple filter dependencies into a list.
    """
    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}

    # Add id filter providers
    if config.get("id_filter", False):
        field_name = config.get("id_field", "id")

        def provide_id_filter(
            ids: Optional[set[str]] = Query(
                default=None,
                alias="ids",
                description="IDs to filter by.",
            ),
        ) -> Optional[CollectionFilter[Any]]:
            return CollectionFilter(field_name=field_name, values=ids) if ids else None

        param_name = dep_defaults.ID_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Depends(provide_id_filter),
                annotation=Optional[CollectionFilter[Any]],
            )
        )
        annotations[param_name] = Optional[CollectionFilter[Any]]

    # Add created_at filter providers
    if config.get("created_at", False):
        field_name = "created_at" if isinstance(config.get("created_at"), bool) else str(config.get("created_at"))

        def provide_created_at_filter(
            before: Optional[str] = Query(
                default=None,
                alias="createdBefore",
                description="Filter by created date before this timestamp.",
                json_schema_extra={"format": "date-time"},
            ),
            after: Optional[str] = Query(
                default=None,
                alias="createdAfter",
                description="Filter by created date after this timestamp.",
                json_schema_extra={"format": "date-time"},
            ),
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
                BeforeAfter(field_name=field_name, before=before_dt, after=after_dt) if before_dt or after_dt else None
            )

        param_name = dep_defaults.CREATED_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Depends(provide_created_at_filter),
                annotation=Optional[BeforeAfter],
            )
        )
        annotations[param_name] = Optional[BeforeAfter]

    # Add updated_at filter providers
    if config.get("updated_at", False):
        field_name = "updated_at" if isinstance(config.get("updated_at"), bool) else str(config.get("updated_at"))

        def provide_updated_at_filter(
            before: Optional[str] = Query(
                default=None,
                alias="updatedBefore",
                description="Filter by updated date before this timestamp.",
                json_schema_extra={"format": "date-time"},
            ),
            after: Optional[str] = Query(
                default=None,
                alias="updatedAfter",
                description="Filter by updated date after this timestamp.",
                json_schema_extra={"format": "date-time"},
            ),
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
                BeforeAfter(field_name=field_name, before=before_dt, after=after_dt) if before_dt or after_dt else None
            )

        param_name = dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Depends(provide_updated_at_filter),
                annotation=Optional[BeforeAfter],
            )
        )
        annotations[param_name] = Optional[BeforeAfter]

    # Add pagination filter providers
    if config.get("pagination_type") == "limit_offset":
        page_size_default = config.get("pagination_size", dep_defaults.DEFAULT_PAGINATION_SIZE)

        def provide_limit_offset_pagination(
            current_page: int = Query(
                default=1,
                ge=1,
                alias="currentPage",
                description="Page number for pagination.",
            ),
            page_size: int = Query(
                default=page_size_default,
                ge=1,
                le=1000,  # Add an upper limit
                alias="pageSize",
                description="Number of items per page.",
            ),
        ) -> LimitOffset:
            return LimitOffset(limit=page_size, offset=page_size * (current_page - 1))

        param_name = dep_defaults.LIMIT_OFFSET_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Depends(provide_limit_offset_pagination),
                annotation=LimitOffset,
            )
        )
        annotations[param_name] = LimitOffset

    # Add search filter providers
    if search_fields := config.get("search"):
        ignore_case_default = config.get("search_ignore_case", False)

        # Handle both string and set input types for search fields
        if isinstance(search_fields, str):
            field_names = {field.strip() for field in search_fields.split(",") if field.strip()}
        else:
            field_names = search_fields

        def provide_search_filter(
            search_string: Optional[str] = Query(
                default=None,
                alias="searchString",
                description="Search term.",
            ),
            ignore_case: Optional[bool] = Query(
                default=ignore_case_default,
                alias="searchIgnoreCase",
                description="Whether search should be case-insensitive.",
            ),
        ) -> Optional[SearchFilter]:
            if not search_string:
                return None
            return SearchFilter(field_name=field_names, value=search_string, ignore_case=ignore_case or False)

        param_name = dep_defaults.SEARCH_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Depends(provide_search_filter),
                annotation=Optional[SearchFilter],
            )
        )
        annotations[param_name] = Optional[SearchFilter]

    # Add sort filter providers
    if sort_field := config.get("sort_field"):
        sort_order_default = config.get("sort_order", "desc")

        # Handle both string and set values for sort_field
        # If it's a set, pick an arbitrary element as the default.
        default_sort_field = sort_field if isinstance(sort_field, str) else next(iter(sort_field))

        def provide_order_by(
            field_name: str = Query(
                default=default_sort_field,
                alias="orderBy",
                description="Field to order by.",
            ),
            sort_order: Optional[SortOrder] = Query(
                default=None,  # Set to None to ensure anyOf schema in OpenAPI
                alias="sortOrder",
                description="Sort order ('asc' or 'desc').",
            ),
        ) -> OrderBy:
            return OrderBy(field_name=field_name, sort_order=sort_order or sort_order_default)

        param_name = dep_defaults.ORDER_BY_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=Depends(provide_order_by),
                annotation=OrderBy,
            )
        )
        annotations[param_name] = OrderBy

    # Add not_in filter providers
    if not_in_fields := config.get("not_in_fields"):
        # Handle both string items and FieldNameType objects for backward compatibility
        for field_item in not_in_fields:
            # Handle both string and FieldNameType
            field_name = field_item.name if isinstance(field_item, FieldNameType) else field_item

            def create_not_in_filter_provider(
                local_field_name: str,
            ) -> Callable[..., Optional[NotInCollectionFilter[Any]]]:
                def provide_not_in_filter(
                    values: Optional[set[str]] = Query(
                        default=None,
                        alias=f"{local_field_name}NotIn",
                        description=f"Filter {local_field_name} not in values",
                    ),
                ) -> Optional[NotInCollectionFilter[Any]]:
                    return NotInCollectionFilter(field_name=local_field_name, values=values) if values else None

                return provide_not_in_filter

            provider = create_not_in_filter_provider(cast("str", field_name))
            param_name = f"{field_name}_not_in"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=Depends(provider),
                    annotation=Optional[NotInCollectionFilter[Any]],
                )
            )
            annotations[param_name] = Optional[NotInCollectionFilter[Any]]

    # Add in filter providers
    if in_fields := config.get("in_fields"):
        # Handle both string items and FieldNameType objects for backward compatibility
        for field_item in in_fields:
            # Handle both string and FieldNameType
            field_name = field_item.name if isinstance(field_item, FieldNameType) else field_item

            def create_in_filter_provider(local_field_name: str) -> Callable[..., Optional[CollectionFilter[Any]]]:
                def provide_in_filter(
                    values: Optional[set[str]] = Query(
                        default=None,
                        alias=f"{local_field_name}In",
                        description=f"Filter {local_field_name} in values",
                    ),
                ) -> Optional[CollectionFilter[Any]]:
                    return CollectionFilter(field_name=local_field_name, values=values) if values else None

                return provide_in_filter

            provider = create_in_filter_provider(cast("str", field_name))
            param_name = f"{field_name}_in"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=Depends(provider),
                    annotation=Optional[CollectionFilter[Any]],
                )
            )
            annotations[param_name] = Optional[CollectionFilter[Any]]

    # Define our aggregate function with the correct FilterTypes
    def aggregate_filter_function(**kwargs: Any) -> list[FilterTypes]:
        filters: list[FilterTypes] = []
        for filter_value in kwargs.values():
            if filter_value is None:
                continue
            if isinstance(filter_value, list):
                filters.extend(cast("list[FilterTypes]", filter_value))
            elif isinstance(filter_value, SearchFilter) and filter_value.value is None:  # type: ignore[misc]
                continue  # Skip SearchFilter if value is None
            elif isinstance(filter_value, OrderBy) and filter_value.field_name is None:  # type: ignore[misc]
                continue  # Skip OrderBy if field_name is None
            else:
                filters.append(cast("FilterTypes", filter_value))
        return filters

    # Set the function's annotations
    annotations["return"] = list[FilterTypes]
    aggregate_filter_function.__annotations__ = annotations

    # Create a new signature with the correct return annotation - explicitly use list[FilterTypes]
    # to ensure proper type checking in tests without monkey patching
    aggregate_filter_function.__signature__ = inspect.Signature(  # type: ignore
        parameters=params,
        return_annotation=list[FilterTypes],
    )

    return aggregate_filter_function


def create_filter_dependencies(
    config: FilterConfig, dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS
) -> dict[str, Any]:
    """Create FastAPI dependency providers for filters based on config.

    Returns a dictionary containing a single key 'filters' mapped to a
    FastAPI `Depends` object wrapping the dynamically generated aggregate
    filter function. Uses caching to avoid recreating the function for the
    same configuration.

    Args:
        config: Configuration dictionary with desired settings.
        dep_defaults: Dependency defaults instance.

    Returns:
        A dictionary e.g., {"filters": Depends(dynamic_aggregate_func)}
        or an empty dict if no filters are configured.
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
        return {}

    # Calculate cache key using hashable version of config
    cache_key = hash(_make_hashable(config))

    # Check cache first
    cached_deps = dep_cache.get_dependencies(cache_key)
    if cached_deps is not None:
        return cached_deps

    # Create new dependencies if not in cache
    aggregate_func = _create_filter_aggregate_function_fastapi(config, dep_defaults)
    dependencies = {dep_defaults.FILTERS_DEPENDENCY_KEY: Depends(aggregate_func)}

    # Cache the result
    dep_cache.add_dependencies(cache_key, dependencies)
    return dependencies

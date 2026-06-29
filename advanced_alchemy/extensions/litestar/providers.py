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
    Annotated,
    Any,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)
from uuid import UUID

from litestar.di import NamedDependency, Provide
from litestar.params import FromQuery, QueryParameter, SkipValidation

from advanced_alchemy.filters import (
    BeforeAfter,
    BooleanFilter,
    ChoicesFilter,
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
from advanced_alchemy.utils.dependencies import (
    ChoiceField,
    DependencyCache,
    FieldNameType,
    FilterConfig,
    make_hashable,
    normalize_choice_field_types,
    normalize_field_name_types,
    normalize_sort_field,
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
AsyncServiceT_co = TypeVar("AsyncServiceT_co", bound=SQLAlchemyAsyncRepositoryService[Any, Any], covariant=True)
SyncServiceT_co = TypeVar("SyncServiceT_co", bound=SQLAlchemySyncRepositoryService[Any, Any], covariant=True)

__all__ = (
    "DEPENDENCY_DEFAULTS",
    "ChoiceField",
    "DependencyCache",
    "DependencyDefaults",
    "FieldNameType",
    "FilterConfig",
    "SingletonMeta",
    "create_filter_dependencies",
    "create_service_dependencies",
    "create_service_provider",
    "dep_cache",
)

_CACHE_NAMESPACE = "advanced_alchemy.extensions.litestar.providers"


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
        async_session_type_annotation = NamedDependency[SkipValidation[Optional["AsyncSession"]]]
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
            annotation=async_session_type_annotation,
        )

        provider_signature = inspect.Signature(
            parameters=[session_param],
            return_annotation=return_type_annotation,
        )
        provide_service_async.__signature__ = provider_signature  # type: ignore[attr-defined]
        provide_service_async.__annotations__ = {
            session_dependency_key: async_session_type_annotation,
            "return": return_type_annotation,
        }
        return provide_service_async

    sync_session_type_annotation = NamedDependency[SkipValidation[Optional["Session"]]]
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
        annotation=sync_session_type_annotation,
    )

    provider_signature = inspect.Signature(
        parameters=[session_param],
        return_annotation=return_type_annotation,
    )
    provide_service_sync.__signature__ = provider_signature  # type: ignore[attr-defined]
    provide_service_sync.__annotations__ = {
        session_dependency_key: sync_session_type_annotation,
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
    cache_key = hash((_CACHE_NAMESPACE, make_hashable(config)))
    deps = cast("Optional[dict[str, Provide]]", dep_cache.get_dependencies(cache_key))
    if deps is not None:
        return deps
    deps = _create_statement_filters(config, dep_defaults)
    dep_cache.add_dependencies(cache_key, deps)
    return deps


def _create_order_by_filter_provider(
    sort_field: Union[str, set[str], list[str]],
    sort_order_default: SortOrder = "desc",
) -> Callable[..., OrderBy]:
    sort_field_default = normalize_sort_field(sort_field)

    def provide_order_by(
        field_name: Annotated[
            StringOrNone,
            QueryParameter(
                title="Order by field",
                name="orderBy",
            ),
        ] = sort_field_default,
        sort_order: Annotated[
            SortOrderOrNone,
            QueryParameter(
                title="Field to search",
                name="sortOrder",
            ),
        ] = sort_order_default,
    ) -> OrderBy:
        return OrderBy(field_name=field_name, sort_order=sort_order or sort_order_default)  # type: ignore[arg-type]

    return provide_order_by


def _create_not_in_filter_providers(
    config: FilterConfig,
) -> dict[str, Provide]:
    """Create not-in filter providers based on configuration."""
    filters: dict[str, Provide] = {}
    if not_in_fields := config.get("not_in_fields"):
        # Get all field names, handling both strings and FieldNameType objects
        not_in_fields = {not_in_fields} if isinstance(not_in_fields, (str, FieldNameType)) else not_in_fields

        for field_def in not_in_fields:
            field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def

            # Capture field_def by value to avoid Python closure late binding gotcha
            # Without default parameter, all closures would reference the loop variable's final value
            def create_not_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType = field_def,  # type: ignore[assignment]
            ) -> Callable[..., Optional[NotInCollectionFilter[Any]]]:
                param_name = f"{field_name.name}_not_in"

                def provide_not_in_filter(  # pyright: ignore
                    **kwargs: Any,
                ) -> Optional[NotInCollectionFilter[field_name.type_hint]]:  # type: ignore
                    values = kwargs.get(param_name)
                    return (
                        NotInCollectionFilter[field_name.type_hint](field_name=field_name.name, values=values)  # type: ignore
                        if values
                        else None
                    )

                annotation = Annotated[
                    Optional[list[field_name.type_hint]],  # type: ignore
                    QueryParameter(name=camelize(param_name)),
                ]
                provide_not_in_filter.__name__ = f"provide_not_in_filter_{field_name.name}"
                provide_not_in_filter.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
                    parameters=[
                        inspect.Parameter(
                            name=param_name,
                            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            default=None,
                            annotation=annotation,
                        )
                    ],
                    return_annotation=Optional[NotInCollectionFilter[field_name.type_hint]],  # type: ignore
                )
                provide_not_in_filter.__annotations__ = {
                    param_name: annotation,
                    "return": Optional[NotInCollectionFilter[field_name.type_hint]],  # type: ignore
                }
                return provide_not_in_filter  # pyright: ignore

            provider = create_not_in_filter_provider(field_def)  # pyright: ignore
            filters[f"{field_def.name}_not_in_filter"] = Provide(provider, sync_to_thread=False)  # pyright: ignore
    return filters


def _create_in_filter_providers(
    config: FilterConfig,
) -> dict[str, Provide]:
    """Create in-filter providers based on configuration."""
    filters: dict[str, Provide] = {}
    if in_fields := config.get("in_fields"):
        # Get all field names, handling both strings and FieldNameType objects
        in_fields = {in_fields} if isinstance(in_fields, (str, FieldNameType)) else in_fields

        for field_def in in_fields:
            field_def = FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def

            # Capture field_def by value to avoid Python closure late binding gotcha
            # Without default parameter, all closures would reference the loop variable's final value
            def create_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType = field_def,  # type: ignore[assignment]
            ) -> Callable[..., Optional[CollectionFilter[Any]]]:
                param_name = f"{field_name.name}_in"

                def provide_in_filter(  # pyright: ignore
                    **kwargs: Any,
                ) -> Optional[CollectionFilter[field_name.type_hint]]:  # type: ignore # pyright: ignore
                    values = kwargs.get(param_name)
                    return (
                        CollectionFilter[field_name.type_hint](field_name=field_name.name, values=values)  # type: ignore  # pyright: ignore
                        if values
                        else None
                    )

                provide_in_filter.__name__ = f"provide_in_filter_{field_name.name}"
                annotation = Annotated[
                    Optional[list[field_name.type_hint]],  # type: ignore
                    QueryParameter(
                        name=camelize(param_name),
                    ),
                ]
                provide_in_filter.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
                    parameters=[
                        inspect.Parameter(
                            name=param_name,
                            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            default=None,
                            annotation=annotation,
                        )
                    ],
                    return_annotation=Optional[CollectionFilter[field_name.type_hint]],  # type: ignore
                )
                provide_in_filter.__annotations__ = {
                    param_name: annotation,
                    "return": Optional[CollectionFilter[field_name.type_hint]],  # type: ignore
                }
                return provide_in_filter  # pyright: ignore

            provider = create_in_filter_provider(field_def)
            filters[f"{field_def.name}_in_filter"] = Provide(provider, sync_to_thread=False)  # pyright: ignore
    return filters


def _create_boolean_filter_providers(
    config: FilterConfig,
) -> dict[str, Provide]:
    """Create boolean filter providers based on configuration."""
    filters: dict[str, Provide] = {}
    if boolean_fields := config.get("boolean_fields"):
        for boolean_field_def in normalize_field_name_types(boolean_fields):

            def create_boolean_filter_provider(
                field_name: FieldNameType = boolean_field_def,
            ) -> Callable[..., Optional[BooleanFilter]]:
                param_name = f"{field_name.name}_boolean"

                def provide_boolean_filter(**kwargs: Any) -> Optional[BooleanFilter]:
                    value = kwargs.get(param_name)
                    return BooleanFilter(field_name=field_name.name, value=value) if value is not None else None

                annotation = Annotated[
                    BooleanOrNone,
                    QueryParameter(name=camelize(field_name.name)),
                ]
                provide_boolean_filter.__name__ = f"provide_boolean_filter_{field_name.name}"
                provide_boolean_filter.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
                    parameters=[
                        inspect.Parameter(
                            name=param_name,
                            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            default=None,
                            annotation=annotation,
                        )
                    ],
                    return_annotation=Optional[BooleanFilter],
                )
                provide_boolean_filter.__annotations__ = {
                    param_name: annotation,
                    "return": Optional[BooleanFilter],
                }
                return provide_boolean_filter

            boolean_provider = create_boolean_filter_provider(boolean_field_def)
            filters[f"{boolean_field_def.name}_boolean_filter"] = Provide(boolean_provider, sync_to_thread=False)
    return filters


def _create_choices_filter_providers(
    config: FilterConfig,
) -> dict[str, Provide]:
    """Create choices filter providers based on configuration."""
    filters: dict[str, Provide] = {}
    if choice_fields := config.get("choice_fields"):
        for choice_field_def in normalize_choice_field_types(choice_fields):

            def create_choices_filter_provider(
                field_name: FieldNameType = choice_field_def,
            ) -> Callable[..., Optional[ChoicesFilter[Any]]]:
                param_name = f"{field_name.name}_choices"

                def provide_choices_filter(**kwargs: Any) -> Optional[ChoicesFilter[Any]]:
                    values = kwargs.get(param_name)
                    return (
                        ChoicesFilter[field_name.type_hint](field_name=field_name.name, values=values)  # type: ignore
                        if values
                        else None
                    )

                annotation = Annotated[
                    Optional[list[field_name.type_hint]],  # type: ignore
                    QueryParameter(name=camelize(field_name.name)),
                ]
                provide_choices_filter.__name__ = f"provide_choices_filter_{field_name.name}"
                provide_choices_filter.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
                    parameters=[
                        inspect.Parameter(
                            name=param_name,
                            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            default=None,
                            annotation=annotation,
                        )
                    ],
                    return_annotation=Optional[ChoicesFilter[Any]],
                )
                provide_choices_filter.__annotations__ = {
                    param_name: annotation,
                    "return": Optional[ChoicesFilter[Any]],
                }
                return provide_choices_filter

            choices_provider = create_choices_filter_provider(choice_field_def)
            filters[f"{choice_field_def.name}_choices_filter"] = Provide(choices_provider, sync_to_thread=False)
    return filters


def _create_statement_filters(
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
            ids: FromQuery[Optional[list[str]]] = None,
        ) -> CollectionFilter:  # pyright: ignore[reportMissingTypeArgument]
            return CollectionFilter(field_name=config.get("id_field", "id"), values=ids)

        filters[dep_defaults.ID_FILTER_DEPENDENCY_KEY] = Provide(provide_id_filter, sync_to_thread=False)  # pyright: ignore[reportUnknownArgumentType]

    if config.get("created_at", False):

        def provide_created_filter(
            before: Annotated[DTorNone, QueryParameter(name="createdBefore")] = None,
            after: Annotated[DTorNone, QueryParameter(name="createdAfter")] = None,
        ) -> BeforeAfter:
            return BeforeAfter("created_at", before, after)

        filters[dep_defaults.CREATED_FILTER_DEPENDENCY_KEY] = Provide(provide_created_filter, sync_to_thread=False)

    if config.get("updated_at", False):

        def provide_updated_filter(
            before: Annotated[DTorNone, QueryParameter(name="updatedBefore")] = None,
            after: Annotated[DTorNone, QueryParameter(name="updatedAfter")] = None,
        ) -> BeforeAfter:
            return BeforeAfter("updated_at", before, after)

        filters[dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY] = Provide(provide_updated_filter, sync_to_thread=False)

    if config.get("pagination_type") == "limit_offset":

        def provide_limit_offset_pagination(
            current_page: Annotated[int, QueryParameter(ge=1, name="currentPage")] = 1,
            page_size: Annotated[
                int,
                QueryParameter(
                    name="pageSize",
                    ge=1,
                ),
            ] = config.get("pagination_size", dep_defaults.DEFAULT_PAGINATION_SIZE),
        ) -> LimitOffset:
            return LimitOffset(page_size, page_size * (current_page - 1))

        filters[dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY] = Provide(
            provide_limit_offset_pagination, sync_to_thread=False
        )

    if search_fields := config.get("search"):

        def provide_search_filter(
            search_string: Annotated[
                StringOrNone,
                QueryParameter(
                    name="searchString",
                    title="Field to search",
                ),
            ] = None,
            ignore_case: Annotated[
                BooleanOrNone,
                QueryParameter(
                    name="searchIgnoreCase",
                    title="Search should be case sensitive",
                ),
            ] = config.get("search_ignore_case", False),
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
        filters[dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY] = Provide(
            _create_order_by_filter_provider(sort_field, config.get("sort_order", "desc")),
            sync_to_thread=False,
        )

    filters.update(_create_not_in_filter_providers(config))
    filters.update(_create_in_filter_providers(config))
    filters.update(_create_boolean_filter_providers(config))
    filters.update(_create_choices_filter_providers(config))

    if filters:
        filters[dep_defaults.FILTERS_DEPENDENCY_KEY] = Provide(
            _create_filter_aggregate_function(config), sync_to_thread=False
        )

    return filters


def _build_parameter(
    parameters: dict[str, inspect.Parameter],
    annotations: dict[str, Any],
    name: str,
    annotation_type: Any,
    *,
    use_named_dependency: bool = True,
) -> None:
    annotation: Any = (
        NamedDependency[SkipValidation[annotation_type]]  # type: ignore[misc]
        if use_named_dependency
        else annotation_type
    )
    parameters[name] = inspect.Parameter(
        name=name,
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=annotation,
    )
    annotations[name] = annotation_type


def _collect_builtin_filters(kwargs: dict[str, FilterTypes]) -> list[FilterTypes]:
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
    return filters


def _collect_field_filters(config: FilterConfig, kwargs: dict[str, FilterTypes]) -> list[FilterTypes]:
    filters: list[FilterTypes] = []
    if not_in_fields := config.get("not_in_fields"):
        filters.extend(
            filter_
            for field_def in normalize_field_name_types(not_in_fields)
            if (filter_ := kwargs.get(f"{field_def.name}_not_in_filter")) is not None
        )
    if in_fields := config.get("in_fields"):
        filters.extend(
            filter_
            for field_def in normalize_field_name_types(in_fields)
            if (filter_ := kwargs.get(f"{field_def.name}_in_filter")) is not None
        )
    if boolean_fields := config.get("boolean_fields"):
        filters.extend(
            filter_
            for field_def in normalize_field_name_types(boolean_fields)
            if (filter_ := kwargs.get(f"{field_def.name}_boolean_filter")) is not None
        )
    if choice_fields := config.get("choice_fields"):
        filters.extend(
            filter_
            for field_def in normalize_choice_field_types(choice_fields)
            if (filter_ := kwargs.get(f"{field_def.name}_choices_filter")) is not None
        )
    return filters


def _collect_filters(config: FilterConfig, **kwargs: FilterTypes) -> list[FilterTypes]:
    return _collect_builtin_filters(kwargs) + _collect_field_filters(config, kwargs)


def _build_builtin_parameters(
    config: FilterConfig,
    parameters: dict[str, inspect.Parameter],
    annotations: dict[str, Any],
) -> None:
    if cls := config.get("id_filter"):
        _build_parameter(parameters, annotations, "id_filter", CollectionFilter[cls])  # type: ignore[valid-type]

    if config.get("created_at"):
        _build_parameter(parameters, annotations, "created_filter", BeforeAfter)

    if config.get("updated_at"):
        _build_parameter(parameters, annotations, "updated_filter", BeforeAfter)

    if config.get("search"):
        _build_parameter(parameters, annotations, "search_filter", SearchFilter)

    if config.get("pagination_type") == "limit_offset":
        _build_parameter(parameters, annotations, "limit_offset_filter", LimitOffset)

    if config.get("sort_field"):
        _build_parameter(parameters, annotations, "order_by_filter", OrderBy)


def _build_field_parameters(
    config: FilterConfig,
    parameters: dict[str, inspect.Parameter],
    annotations: dict[str, Any],
) -> None:
    if not_in_fields := config.get("not_in_fields"):
        for field_def in normalize_field_name_types(not_in_fields):
            _build_parameter(
                parameters,
                annotations,
                f"{field_def.name}_not_in_filter",
                NotInCollectionFilter[field_def.type_hint],  # type: ignore[name-defined]
            )

    if in_fields := config.get("in_fields"):
        for field_def in normalize_field_name_types(in_fields):
            _build_parameter(
                parameters,
                annotations,
                f"{field_def.name}_in_filter",
                CollectionFilter[field_def.type_hint],  # type: ignore[name-defined]
                use_named_dependency=False,
            )

    if boolean_fields := config.get("boolean_fields"):
        for boolean_field_def in normalize_field_name_types(boolean_fields):
            _build_parameter(parameters, annotations, f"{boolean_field_def.name}_boolean_filter", BooleanFilter)

    if choice_fields := config.get("choice_fields"):
        for choice_field_def in normalize_choice_field_types(choice_fields):
            _build_parameter(
                parameters,
                annotations,
                f"{choice_field_def.name}_choices_filter",
                ChoicesFilter[choice_field_def.type_hint],  # type: ignore[name-defined]
            )


def _create_filter_aggregate_function(config: FilterConfig) -> Callable[..., list[FilterTypes]]:
    """Create a filter function based on the provided configuration.

    Args:
        config: The filter configuration.

    Returns:
        A function that returns a list of filters based on the configuration.
    """

    parameters: dict[str, inspect.Parameter] = {}
    annotations: dict[str, Any] = {}

    _build_builtin_parameters(config, parameters, annotations)
    _build_field_parameters(config, parameters, annotations)

    def provide_filters(**kwargs: FilterTypes) -> list[FilterTypes]:
        return _collect_filters(config, **kwargs)

    # Set both signature and annotations
    provide_filters.__signature__ = inspect.Signature(  # type: ignore
        parameters=list(parameters.values()),
        return_annotation=list[FilterTypes],
    )
    provide_filters.__annotations__ = annotations
    provide_filters.__annotations__["return"] = list[FilterTypes]

    return provide_filters

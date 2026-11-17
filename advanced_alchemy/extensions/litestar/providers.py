# ruff: noqa: B008
"""Application dependency providers generators.

This module contains functions to create dependency providers for services and filters.

You should not have modify this module very often and should only be invoked under normal usage.
"""

import datetime as dt
import inspect
import re
from collections.abc import AsyncGenerator, Callable, Generator, Mapping
from functools import partial
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

from litestar import Request
from litestar.di import NamedDependency, Provide
from litestar.exceptions import ValidationException
from litestar.params import QueryParameter, SkipValidation
from litestar.utils.signature import ParsedSignature

from advanced_alchemy.config import SQLAlchemyAsyncConfig as BaseAsyncConfig
from advanced_alchemy.config import SQLAlchemySyncConfig as BaseSyncConfig
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import (
    BeforeAfterFilter,
    BooleanFilter,
    ChoicesFilter,
    CursorFilter,
    FilterSet,
    FilterTypes,
    InCollectionFilter,
    LimitOffsetFilter,
    NotInCollectionFilter,
    OrderByFilter,
    SearchFilter,
)
from advanced_alchemy.service import (
    Empty,
    EmptyType,
    ErrorMessages,
    LoadSpec,
    ServiceGroup,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.utils.dependencies import (
    ChoiceField,
    CursorDefaults,
    CursorSettings,
    DependencyCache,
    FieldNameType,
    FilterConfig,
    FilterFieldSpec,
    FilterFieldsSpec,
    FilterOperator,
    build_order_by_filters,
    create_field_filter_provider,
    filter_cache_key,
    filter_parameter_type,
    group_filter_fields,
    normalize_choice_field_types,
    normalize_field_name_types,
    normalize_sort_field,
    normalize_sort_fields,
    resolve_cursor_settings,
    resolve_filter_aliases,
    resolve_filter_fields,
    resolve_pagination_bounds,
)
from advanced_alchemy.utils.singleton import SingletonMeta
from advanced_alchemy.utils.text import camelize

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.extensions.litestar.plugins.init.config.sync import SQLAlchemySyncConfig

DTorNone = Optional[dt.datetime]
StringOrNone = Optional[str]
UuidOrNone = Optional[UUID]
IntOrNone = Optional[int]
BooleanOrNone = Optional[bool]
SortOrder = Literal["asc", "desc"]
SortOrderOrNone = Optional[SortOrder]
AsyncServiceT_co = TypeVar("AsyncServiceT_co", bound=SQLAlchemyAsyncRepositoryService[Any, Any], covariant=True)
SyncServiceT_co = TypeVar("SyncServiceT_co", bound=SQLAlchemySyncRepositoryService[Any, Any], covariant=True)
ServiceGroupT = TypeVar("ServiceGroupT", bound=ServiceGroup)

__all__ = (
    "DEPENDENCY_DEFAULTS",
    "ChoiceField",
    "DependencyCache",
    "DependencyDefaults",
    "FieldNameType",
    "FilterConfig",
    "FilterFieldsSpec",
    "FilterOperator",
    "ServiceGroup",
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
    CURSOR_FILTER_DEPENDENCY_KEY: str = "cursor_filter"
    """Key for the cursor pagination dependency."""
    DEFAULT_PAGINATION_SIZE: int = 20
    """Default pagination size."""
    prefix: Optional[str] = None
    """Optional namespace prefix for dependency keys."""

    def __init__(
        self,
        filters_key: Optional[str] = None,
        created_filter_key: Optional[str] = None,
        id_filter_key: Optional[str] = None,
        limit_offset_filter_key: Optional[str] = None,
        updated_filter_key: Optional[str] = None,
        order_by_filter_key: Optional[str] = None,
        search_filter_key: Optional[str] = None,
        default_pagination_size: Optional[int] = None,
        prefix: Optional[str] = None,
        cursor_filter_key: Optional[str] = None,
    ) -> None:
        if prefix is not None:
            self.prefix = prefix
        clean_prefix = self.prefix.rstrip("_") if self.prefix else ""
        prefix_clean = f"{clean_prefix}_" if clean_prefix else ""
        has_prefix = bool(prefix_clean)
        cls = type(self)

        for attr, explicit_key in (
            ("FILTERS_DEPENDENCY_KEY", filters_key),
            ("CREATED_FILTER_DEPENDENCY_KEY", created_filter_key),
            ("ID_FILTER_DEPENDENCY_KEY", id_filter_key),
            ("LIMIT_OFFSET_FILTER_DEPENDENCY_KEY", limit_offset_filter_key),
            ("UPDATED_FILTER_DEPENDENCY_KEY", updated_filter_key),
            ("ORDER_BY_FILTER_DEPENDENCY_KEY", order_by_filter_key),
            ("SEARCH_FILTER_DEPENDENCY_KEY", search_filter_key),
            ("CURSOR_FILTER_DEPENDENCY_KEY", cursor_filter_key),
        ):
            if explicit_key is not None or has_prefix:
                base = explicit_key if explicit_key is not None else cast("str", getattr(cls, attr))
                object.__setattr__(self, attr, f"{prefix_clean}{base}" if has_prefix else base)

        if default_pagination_size is not None:
            object.__setattr__(self, "DEFAULT_PAGINATION_SIZE", default_pagination_size)


DEPENDENCY_DEFAULTS = DependencyDefaults()


dep_cache = DependencyCache()


def _attach_service_provider_signature(
    provider: Callable[..., Any],
    session_dependency_key: str,
    param_annotation: Any,
    return_annotation: Any,
) -> Callable[..., Any]:
    session_param = inspect.Parameter(
        name=session_dependency_key,
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=param_annotation,
    )
    provider.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters=[session_param],
        return_annotation=return_annotation,
    )
    provider.__annotations__ = {
        session_dependency_key: param_annotation,
        "return": return_annotation,
    }
    return provider


def _is_async_provider_target(
    service_class: type[Any],
    config: "Optional[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]",
) -> bool:
    if issubclass(service_class, ServiceGroup):
        group_async = service_class.is_async_group()
        if group_async is not None:
            return group_async
        if isinstance(config, BaseSyncConfig):
            return False
        if isinstance(config, BaseAsyncConfig):
            return True
        return True
    return (
        issubclass(service_class, SQLAlchemyAsyncRepositoryService) or service_class is SQLAlchemyAsyncRepositoryService
    )


def _with_dep_defaults_prefix(
    dep_defaults: Optional[DependencyDefaults],
    prefix: str,
) -> DependencyDefaults:
    if dep_defaults is None:
        return DependencyDefaults(prefix=prefix)
    cls = type(dep_defaults)
    old_prefix = f"{dep_defaults.prefix.rstrip('_')}_" if dep_defaults.prefix else ""
    cursor_key = dep_defaults.CURSOR_FILTER_DEPENDENCY_KEY.removeprefix(old_prefix)
    extra: dict[str, Any] = (
        {} if cursor_key == DependencyDefaults.CURSOR_FILTER_DEPENDENCY_KEY else {"cursor_filter_key": cursor_key}
    )
    return cls(
        filters_key=dep_defaults.FILTERS_DEPENDENCY_KEY.removeprefix(old_prefix),
        created_filter_key=dep_defaults.CREATED_FILTER_DEPENDENCY_KEY.removeprefix(old_prefix),
        id_filter_key=dep_defaults.ID_FILTER_DEPENDENCY_KEY.removeprefix(old_prefix),
        limit_offset_filter_key=dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY.removeprefix(old_prefix),
        updated_filter_key=dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY.removeprefix(old_prefix),
        order_by_filter_key=dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY.removeprefix(old_prefix),
        search_filter_key=dep_defaults.SEARCH_FILTER_DEPENDENCY_KEY.removeprefix(old_prefix),
        default_pagination_size=dep_defaults.DEFAULT_PAGINATION_SIZE,
        prefix=prefix,
        **extra,
    )


@overload
def create_service_provider(
    service_class: type["AsyncServiceT_co"],
    /,
    statement: "Optional[Select[Any]]" = None,
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
    statement: "Optional[Select[Any]]" = None,
    config: "Optional[SQLAlchemySyncConfig]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Generator[SyncServiceT_co, None, None]]: ...


@overload
def create_service_provider(
    service_class: type["ServiceGroupT"],
    /,
    statement: "Optional[Select[Any]]" = None,
    config: "Optional[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Union[AsyncGenerator[ServiceGroupT, None], Generator[ServiceGroupT, None, None]]]: ...


def create_service_provider(
    service_class: type[Union["AsyncServiceT_co", "SyncServiceT_co", "ServiceGroupT"]],
    /,
    statement: "Optional[Select[Any]]" = None,
    config: "Optional[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[
    ...,
    Union[
        "AsyncGenerator[Union[AsyncServiceT_co, ServiceGroupT], None]",
        "Generator[Union[SyncServiceT_co, ServiceGroupT], None, None]",
    ],
]:
    """Create a dependency provider for a service or ServiceGroup with a configurable session key.

    Args:
        service_class: The service or ServiceGroup class to instantiate per request.
        statement: An optional SQLAlchemy Select statement to scope a single service.
        config: An optional SQLAlchemy configuration object.
        error_messages: Optional custom error messages for the service.
        load: Optional LoadSpec for eager loading relationships on a single service.
        execution_options: Optional dictionary of execution options for SQLAlchemy.
        uniquify: Optional flag to uniquify results.
        count_with_window_function: Optional flag to use window function for counting.

    Returns:
        A dependency provider function suitable for Litestar's DI system.
    """
    is_group = issubclass(service_class, ServiceGroup)
    if is_group and (statement is not None or load is not None):
        msg = "Group-wide 'statement' and 'load' options are not supported for ServiceGroup; configure them on individual service classes."
        raise ImproperConfigurationError(msg)

    session_dependency_key = config.session_dependency_key if config else "db_session"
    is_async = _is_async_provider_target(service_class, config)

    def _enter_target(db_session: Any) -> Any:
        if is_group:
            group_cls = cast("type[ServiceGroup]", service_class)
            return group_cls.new(
                session=db_session,
                config=config,
                error_messages=error_messages,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
            )
        if is_async:
            async_svc_cls = cast("type[SQLAlchemyAsyncRepositoryService[Any, Any]]", service_class)
            return async_svc_cls.new(
                session=db_session,
                statement=statement,
                config=cast("Optional[SQLAlchemyAsyncConfig]", config),
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
            )
        sync_svc_cls = cast("type[SQLAlchemySyncRepositoryService[Any, Any]]", service_class)
        return sync_svc_cls.new(
            session=db_session,
            statement=statement,
            config=cast("Optional[SQLAlchemySyncConfig]", config),
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            count_with_window_function=count_with_window_function,
        )

    if is_async:
        async_session_type_annotation = NamedDependency[SkipValidation[Optional["AsyncSession"]]]
        return_type_annotation = AsyncGenerator[service_class, None]  # type: ignore[valid-type]

        async def provide_service_async(*args: Any, **kwargs: Any) -> "AsyncGenerator[Any, None]":
            db_session = cast("Optional[AsyncSession]", args[0] if args else kwargs.get(session_dependency_key))
            async with _enter_target(db_session) as service:
                yield service

        return _attach_service_provider_signature(
            provide_service_async,
            session_dependency_key,
            async_session_type_annotation,
            return_type_annotation,
        )

    sync_session_type_annotation = NamedDependency[SkipValidation[Optional["Session"]]]
    return_type_annotation = Generator[service_class, None, None]  # type: ignore[misc,assignment,valid-type]

    def provide_service_sync(*args: Any, **kwargs: Any) -> "Generator[Any, None, None]":
        db_session = cast("Optional[Session]", args[0] if args else kwargs.get(session_dependency_key))
        with _enter_target(db_session) as service:
            yield service

    return _attach_service_provider_signature(
        provide_service_sync,
        session_dependency_key,
        sync_session_type_annotation,
        return_type_annotation,
    )


def _resolve_single_service_dep_defaults(
    key: str,
    dep_defaults: "Optional[DependencyDefaults]",
    scoped_filters: bool,
) -> "DependencyDefaults":
    """Resolve effective filter dependency defaults for a single service provider."""
    if dep_defaults is None:
        return DependencyDefaults(prefix=key) if scoped_filters else DEPENDENCY_DEFAULTS
    if scoped_filters and not getattr(dep_defaults, "prefix", None):
        return _with_dep_defaults_prefix(dep_defaults, key)
    return dep_defaults


def _create_service_group_filter_dependencies(
    service_class: "type[ServiceGroup]",
    key: str,
    filters: "Union[FilterConfig, type[FilterSet[Any]], Mapping[str, Union[FilterConfig, type[FilterSet[Any]]]]]",
    dep_defaults: "Optional[DependencyDefaults]",
    scoped_filters: bool,
) -> dict[str, Provide]:
    """Create scoped filter dependencies for each configured service in a ServiceGroup."""
    if not isinstance(cast("Any", filters), Mapping):
        msg = f"ServiceGroup filters must map service attribute names to FilterConfig dictionaries on {service_class.__name__}."
        raise ImproperConfigurationError(msg)
    group_fields = service_class.service_fields()
    base_prefix = ""
    if dep_defaults is not None and getattr(dep_defaults, "prefix", None):
        base_prefix = cast("str", dep_defaults.prefix).rstrip("_")
    elif scoped_filters:
        base_prefix = key.rstrip("_")
    deps: dict[str, Provide] = {}
    for attr_name, attr_filter_config in cast(
        "Mapping[str, Union[FilterConfig, type[FilterSet[Any]]]]", filters
    ).items():
        if attr_name not in group_fields:
            msg = f"Filter configuration key {attr_name!r} does not match any service attribute on {service_class.__name__}."
            raise ImproperConfigurationError(msg)
        if not attr_filter_config:
            continue
        scoped_prefix = f"{base_prefix}_{attr_name}" if base_prefix else attr_name
        attr_defaults = _with_dep_defaults_prefix(dep_defaults, scoped_prefix)
        if isinstance(attr_filter_config, type):
            deps.update(create_filter_dependencies(attr_filter_config, attr_defaults))
            continue
        if attr_filter_config.get("filter_fields") is not None or attr_filter_config.get("sort_fields") is not None:
            member_class = group_fields[attr_name]
            model = getattr(getattr(member_class, "repository_type", None), "model_type", None)
            deps.update(create_filter_dependencies(attr_filter_config, attr_defaults, model=model))
        else:
            deps.update(create_filter_dependencies(attr_filter_config, attr_defaults))
    return deps


def create_service_dependencies(
    service_class: type[Union["AsyncServiceT_co", "SyncServiceT_co", "ServiceGroupT"]],
    /,
    key: str,
    statement: "Optional[Select[Any]]" = None,
    config: "Optional[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]" = None,
    error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
    load: "Optional[LoadSpec]" = None,
    execution_options: "Optional[dict[str, Any]]" = None,
    filters: "Optional[Union[FilterConfig, type[FilterSet[Any]], Mapping[str, Union[FilterConfig, type[FilterSet[Any]]]]]]" = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
    dep_defaults: "Optional[DependencyDefaults]" = None,
    scoped_filters: bool = False,
) -> dict[str, Provide]:
    """Create dependency providers for a service or ServiceGroup and optional filters.

    Args:
        key: The key to use for the dependency provider.
        service_class: The service or ServiceGroup class to create a dependency provider for.
        statement: The statement to use for a single service.
        config: The configuration to use for the service.
        error_messages: The error messages to use for the service.
        load: The load spec to use for a single service.
        execution_options: The execution options to use for the service.
        filters: Filter configuration for a single service, or mapping of service attribute name to FilterConfig for a ServiceGroup.
        uniquify: Whether to uniquify the service.
        count_with_window_function: Whether to count with a window function.
        dep_defaults: The dependency defaults to use for the service.
        scoped_filters: Whether to scope the filter dependency keys to the service key.

    Returns:
        A dictionary of dependency providers for the service or ServiceGroup.
    """
    is_group = issubclass(service_class, ServiceGroup)
    is_async = _is_async_provider_target(service_class, config)
    if is_group:
        group_cls = cast("type[ServiceGroup]", service_class)
        svc: Callable[..., Any] = create_service_provider(
            group_cls,
            statement,
            config,
            error_messages,
            load,
            execution_options,
            uniquify,
            count_with_window_function,
        )
    else:
        svc_cls = cast("type[SQLAlchemyAsyncRepositoryService[Any, Any]]", service_class)
        svc = create_service_provider(
            svc_cls,
            statement,
            cast("Optional[SQLAlchemyAsyncConfig]", config),
            error_messages,
            load,
            execution_options,
            uniquify,
            count_with_window_function,
        )
    deps: dict[str, Provide] = {key: Provide(svc) if is_async else Provide(svc, sync_to_thread=False)}
    if not filters:
        return deps

    if is_group:
        deps.update(
            _create_service_group_filter_dependencies(
                cast("type[ServiceGroup]", service_class),
                key,
                filters,
                dep_defaults,
                scoped_filters,
            )
        )
        return deps

    effective_dep_defaults = _resolve_single_service_dep_defaults(key, dep_defaults, scoped_filters)
    if isinstance(filters, type):
        deps.update(create_filter_dependencies(filters, effective_dep_defaults))
        return deps
    filter_config = cast("FilterConfig", filters)
    if filter_config.get("filter_fields") is not None or filter_config.get("sort_fields") is not None:
        model = getattr(getattr(service_class, "repository_type", None), "model_type", None)
        deps.update(create_filter_dependencies(filter_config, effective_dep_defaults, model=model))
    else:
        deps.update(create_filter_dependencies(filter_config, effective_dep_defaults))
    return deps


def _create_filterset_dependency(
    filterset_type: type[FilterSet[Any]], dep_defaults: DependencyDefaults
) -> Callable[..., list[FilterSet[Any]]]:
    config = filterset_type.filter_config()
    _, max_pagination_size = resolve_pagination_bounds(config)
    standard_config = dict(config)
    standard_config.pop("filter_fields", None)
    prefix = getattr(dep_defaults, "prefix", None)
    aliases = resolve_filter_aliases(
        cast("FilterConfig", standard_config), prefix=prefix, model=filterset_type.model_type
    )
    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    entries: list[tuple[str, Any, QueryParameter]] = []
    for spec in filterset_type.parameter_specs():
        alias = f"{prefix.rstrip('_')}_{spec.param_name}" if prefix else spec.param_name
        entries.append((spec.param_name, filter_parameter_type(spec), QueryParameter(name=alias)))
    pagination_type = config.get("pagination_type")
    if pagination_type:
        entries.extend(
            [
                ("cursor", Optional[str], QueryParameter(name=aliases.get("cursor", "cursor")))
                if pagination_type == "cursor"
                else ("page", Optional[int], QueryParameter(name=aliases.get("current_page", "currentPage"), ge=1)),
                (
                    "pageSize",
                    Optional[int],
                    QueryParameter(name=aliases.get("page_size", "pageSize"), ge=1, le=max_pagination_size),
                ),
            ]
        )
    if config.get("sort_fields") or config.get("sort_field"):
        entries.extend(
            [
                ("orderBy", Optional[list[str]], QueryParameter(name=aliases.get("order_by", "orderBy"))),
                (
                    "sortOrder",
                    Optional[Literal["asc", "desc"]],
                    QueryParameter(name=aliases.get("sort_order", "sortOrder")),
                ),
            ]
        )
    if config.get("search"):
        entries.append(
            ("searchString", Optional[str], QueryParameter(name=aliases.get("search_string", "searchString")))
        )
    for name, annotation, query_param in entries:
        annotated = cast("Any", Annotated)[annotation, query_param]
        annotations[name] = annotated
        parameters.append(inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=annotated, default=None))
    annotations["request"] = Request[Any, Any, Any]
    parameters.append(inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY, annotation=Request[Any, Any, Any]))

    def provide_filterset(*, request: Request[Any, Any, Any], **kwargs: Any) -> list[FilterSet[Any]]:
        try:
            instance = filterset_type(
                cursor_defaults=_cursor_defaults(request),
                require_cursor_secret=True,
                **{key: value for key, value in kwargs.items() if value is not None},
            )
            return [instance]  # noqa: TRY300
        except (ValueError, TypeError) as exc:
            raise ValidationException(detail=str(exc)) from exc

    provide_filterset.__name__ = f"provide_{filterset_type.__name__}"
    provide_filterset.__annotations__ = {**annotations, "return": list[FilterSet[Any]]}
    provide_filterset.__signature__ = inspect.Signature(parameters, return_annotation=list[FilterSet[Any]])  # type: ignore[attr-defined]
    return provide_filterset


def create_filter_dependencies(
    config: Union[FilterConfig, type[FilterSet[Any]]],
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
    model: Optional[type[Any]] = None,
) -> dict[str, Provide]:
    """Create a dependency provider for the combined filter function.

    Args:
        config: FilterConfig instance with desired settings.
        dep_defaults: Dependency defaults to use for the filter dependencies
        model: Optional SQLAlchemy model class for inferring ``filter_fields`` and validating ``sort_fields``.

    Returns:
        A dependency provider function for the combined filter function.
    """
    if isinstance(config, type):
        return {
            dep_defaults.FILTERS_DEPENDENCY_KEY: Provide(
                _create_filterset_dependency(config, dep_defaults), sync_to_thread=False
            )
        }
    prefix = getattr(dep_defaults, "prefix", None)
    aliases = resolve_filter_aliases(config, prefix=prefix, model=model)
    cache_key = filter_cache_key(_CACHE_NAMESPACE, config, dep_defaults, aliases, model=model)
    deps = cast("Optional[dict[str, Provide]]", dep_cache.get_dependencies(cache_key))
    if deps is not None:
        return deps
    deps = _create_statement_filters(config, dep_defaults, aliases=aliases, model=model)
    dep_cache.add_dependencies(cache_key, deps)
    return deps


def _create_repeatable_order_by_filter_provider(
    allowed_fields: frozenset[str],
    default_field: Optional[str],
    sort_order_default: SortOrder = "desc",
    alias_for: Callable[[str], str] = camelize,
    nulls_default: Optional[Literal["first", "last"]] = None,
) -> Callable[..., list[OrderByFilter]]:
    allowed_display = ", ".join(sorted(allowed_fields))

    def provide_order_by(
        field_name: Annotated[
            Optional[list[str]],
            QueryParameter(
                title="Order by fields",
                description=f"Repeatable sort fields (prefix '-' for descending). Allowed: {allowed_display}",
                name=alias_for("order_by"),
            ),
        ] = None,
        sort_order: Annotated[
            SortOrderOrNone,
            QueryParameter(
                title="Sort order",
                name=alias_for("sort_order"),
            ),
        ] = None,
    ) -> list[OrderByFilter]:
        try:
            return build_order_by_filters(
                field_name,
                sort_order,
                allowed_fields=allowed_fields,
                default_field=default_field,
                default_order=sort_order_default,
                nulls=nulls_default,
            )
        except ValueError as exc:
            raise ValidationException(detail=str(exc)) from exc

    return provide_order_by


def _create_order_by_filter_provider(
    sort_field: Union[str, set[str], list[str]],
    sort_order_default: SortOrder = "desc",
    alias_for: Callable[[str], str] = camelize,
    nulls_default: Optional[Literal["first", "last"]] = None,
) -> Callable[..., OrderByFilter]:
    sort_field_default = normalize_sort_field(sort_field)

    def provide_order_by(
        field_name: Annotated[
            StringOrNone,
            QueryParameter(
                title="Order by field",
                name=alias_for("order_by"),
            ),
        ] = sort_field_default,
        sort_order: Annotated[
            SortOrderOrNone,
            QueryParameter(
                title="Field to search",
                name=alias_for("sort_order"),
            ),
        ] = sort_order_default,
    ) -> OrderByFilter:
        return OrderByFilter(field_name=field_name, sort_order=sort_order or sort_order_default, nulls=nulls_default)  # type: ignore[arg-type]

    return provide_order_by


def _create_cursor_filter_provider(
    settings: CursorSettings,
    alias_for: Callable[[str], str],
    default_size: int,
    max_size: Optional[int],
    *,
    repeatable_order: bool,
) -> Callable[..., CursorFilter]:
    """Build the cursor pagination dependency; ordering parameters appear only when sorting is configured."""
    cursor_param = QueryParameter(name=alias_for("cursor"), description="Token from a previous page's cursor.")
    size_param = QueryParameter(name=alias_for("page_size"), ge=1, le=max_size)

    def build(
        request: Request[Any, Any, Any],
        cursor: Optional[str],
        page_size: int,
        order_by: Union[str, list[str], None],
        sort_order: Optional[SortOrder],
    ) -> CursorFilter:
        try:
            return settings.build(
                cursor=cursor,
                page_size=page_size,
                order_by=order_by,
                sort_order=sort_order,
                defaults=_cursor_defaults(request),
                require_secret=True,
            )
        except ValueError as exc:
            raise ValidationException(detail=str(exc)) from exc

    def provide_cursor_pagination(
        request: Request[Any, Any, Any],
        cursor: Annotated[StringOrNone, cursor_param] = None,
        page_size: Annotated[int, size_param] = default_size,
    ) -> CursorFilter:
        return build(request, cursor, page_size, None, None)

    if not settings.allowed_fields:
        return provide_cursor_pagination

    order_param = QueryParameter(
        name=alias_for("order_by"),
        description=f"Sort fields (prefix '-' for descending). Allowed: {', '.join(sorted(settings.allowed_fields))}",
    )
    sort_order_param = QueryParameter(name=alias_for("sort_order"), title="Sort order")

    def provide_cursor_pagination_ordered(
        request: Request[Any, Any, Any],
        cursor: Annotated[StringOrNone, cursor_param] = None,
        page_size: Annotated[int, size_param] = default_size,
        order_by: Annotated[StringOrNone, order_param] = None,
        sort_order: Annotated[SortOrderOrNone, sort_order_param] = None,
    ) -> CursorFilter:
        return build(request, cursor, page_size, order_by, sort_order)

    def provide_cursor_pagination_multi_ordered(
        request: Request[Any, Any, Any],
        cursor: Annotated[StringOrNone, cursor_param] = None,
        page_size: Annotated[int, size_param] = default_size,
        order_by: Annotated[Optional[list[str]], order_param] = None,
        sort_order: Annotated[SortOrderOrNone, sort_order_param] = None,
    ) -> CursorFilter:
        return build(request, cursor, page_size, order_by, sort_order)

    return provide_cursor_pagination_multi_ordered if repeatable_order else provide_cursor_pagination_ordered


def _cursor_defaults(request: Request[Any, Any, Any]) -> Optional[CursorDefaults]:
    """Return the cursor token options of the application's SQLAlchemy plugin, if one is registered."""
    from advanced_alchemy.extensions.litestar.plugins.init.plugin import SQLAlchemyInitPlugin

    try:
        return request.app.plugins.get(SQLAlchemyInitPlugin).cursor_defaults
    except KeyError:
        return None


def _create_statement_filters(  # noqa: C901, PLR0915
    config: FilterConfig,
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
    *,
    include_aggregate: bool = True,
    aliases: Optional[dict[str, str]] = None,
    model: Optional[type[Any]] = None,
) -> dict[str, Provide]:
    """Create filter dependencies based on configuration.

    Args:
        config (FilterConfig): Configuration dictionary specifying which filters to enable
        dep_defaults (DependencyDefaults): Dependency defaults to use for the filter dependencies
        include_aggregate: Include the combined dependency in the result.
        aliases: Previously resolved public query names.
        model: Optional SQLAlchemy model class for inferring ``filter_fields`` and validating ``sort_fields``.

    Returns:
        dict[str, Provide]: Dictionary of filter provider functions
    """
    filters: dict[str, Provide] = {}
    prefix = getattr(dep_defaults, "prefix", None)
    clean_prefix = prefix.rstrip("_") if isinstance(prefix, str) else ""
    prefix_str = f"{clean_prefix}_" if clean_prefix else ""
    alias_for = (
        resolve_filter_aliases(config, prefix=clean_prefix or None, model=model) if aliases is None else aliases
    ).__getitem__

    if config.get("id_filter", False):

        def provide_id_filter(  # pyright: ignore[reportUnknownParameterType]
            ids: Annotated[Optional[list[str]], QueryParameter(name=alias_for("ids"))] = None,
        ) -> InCollectionFilter:  # pyright: ignore[reportMissingTypeArgument]
            return InCollectionFilter(field_name=config.get("id_field", "id"), values=ids)

        filters[dep_defaults.ID_FILTER_DEPENDENCY_KEY] = Provide(provide_id_filter, sync_to_thread=False)  # pyright: ignore[reportUnknownArgumentType]

    if config.get("created_at", False):

        def provide_created_filter(
            created_at_before: Annotated[DTorNone, QueryParameter(name=alias_for("created_before"))] = None,
            created_at_after: Annotated[DTorNone, QueryParameter(name=alias_for("created_after"))] = None,
        ) -> BeforeAfterFilter:
            return BeforeAfterFilter("created_at", created_at_before, created_at_after)

        filters[dep_defaults.CREATED_FILTER_DEPENDENCY_KEY] = Provide(provide_created_filter, sync_to_thread=False)

    if config.get("updated_at", False):

        def provide_updated_filter(
            updated_at_before: Annotated[DTorNone, QueryParameter(name=alias_for("updated_before"))] = None,
            updated_at_after: Annotated[DTorNone, QueryParameter(name=alias_for("updated_after"))] = None,
        ) -> BeforeAfterFilter:
            return BeforeAfterFilter("updated_at", updated_at_before, updated_at_after)

        filters[dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY] = Provide(provide_updated_filter, sync_to_thread=False)

    default_pagination_size, max_pagination_size = resolve_pagination_bounds(
        config, default_size=dep_defaults.DEFAULT_PAGINATION_SIZE
    )
    if config.get("pagination_type") == "limit_offset":

        def provide_limit_offset_pagination(
            current_page: Annotated[int, QueryParameter(ge=1, name=alias_for("current_page"))] = 1,
            page_size: Annotated[
                int,
                QueryParameter(
                    name=alias_for("page_size"),
                    ge=1,
                    le=max_pagination_size,
                ),
            ] = default_pagination_size,
        ) -> LimitOffsetFilter:
            return LimitOffsetFilter(page_size, page_size * (current_page - 1))

        filters[dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY] = Provide(
            provide_limit_offset_pagination, sync_to_thread=False
        )
    elif config.get("pagination_type") == "cursor":
        filters[dep_defaults.CURSOR_FILTER_DEPENDENCY_KEY] = Provide(
            _create_cursor_filter_provider(
                resolve_cursor_settings(config, model),
                alias_for,
                default_pagination_size,
                max_pagination_size,
                repeatable_order=bool(config.get("sort_fields")),
            ),
            sync_to_thread=False,
        )

    if search_fields := config.get("search"):
        parsed_field_names = set(search_fields.split(",")) if isinstance(search_fields, str) else set(search_fields)

        def provide_search_filter(
            search_string: Annotated[
                StringOrNone,
                QueryParameter(
                    name=alias_for("search_string"),
                    title="Field to search",
                ),
            ] = None,
            ignore_case: Annotated[
                BooleanOrNone,
                QueryParameter(
                    name=alias_for("search_ignore_case"),
                    title="Search should be case sensitive",
                ),
            ] = config.get("search_ignore_case", False),
        ) -> SearchFilter:
            return SearchFilter(
                field_name=parsed_field_names,
                value=search_string,  # type: ignore[arg-type]
                ignore_case=ignore_case or False,
                escape_wildcards=config.get("search_escape_wildcards", False),
            )

        filters[dep_defaults.SEARCH_FILTER_DEPENDENCY_KEY] = Provide(provide_search_filter, sync_to_thread=False)

    order_by_provided = config.get("pagination_type") != "cursor"
    if order_by_provided and (sort_fields_cfg := config.get("sort_fields")):
        allowed_sort_fields = frozenset(normalize_sort_fields(sort_fields_cfg, model=model))
        raw_default_sort = config.get("sort_field")
        default_sort_field = normalize_sort_field(raw_default_sort) if raw_default_sort else None
        if default_sort_field is not None and default_sort_field not in allowed_sort_fields:
            msg = f"Default sort_field {default_sort_field!r} must be included in sort_fields"
            raise ImproperConfigurationError(msg)
        filters[dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY] = Provide(
            _create_repeatable_order_by_filter_provider(
                allowed_sort_fields,
                default_sort_field,
                config.get("sort_order", "desc"),
                alias_for,
                config.get("sort_nulls"),
            ),
            sync_to_thread=False,
        )
    elif order_by_provided and (sort_field := config.get("sort_field")):
        filters[dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY] = Provide(
            _create_order_by_filter_provider(
                sort_field, config.get("sort_order", "desc"), alias_for, config.get("sort_nulls")
            ),
            sync_to_thread=False,
        )

    # Add not_in filter providers
    if not_in_fields := config.get("not_in_fields"):
        # Get all field names, handling both strings and FieldNameType objects
        not_in_fields = {not_in_fields} if isinstance(not_in_fields, (str, FieldNameType)) else not_in_fields

        for field_def in not_in_fields:
            resolved_field_def = (
                FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def
            )

            def create_not_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType = resolved_field_def,
            ) -> Callable[..., Optional[NotInCollectionFilter[Any]]]:
                param_name = f"{field_name.name}_not_in"
                filter_return_type: Any = cast("Any", Optional)[
                    cast("Any", NotInCollectionFilter)[field_name.type_hint]
                ]
                annotation: Any = cast("Any", Annotated)[
                    cast("Any", Optional)[cast("Any", list)[field_name.type_hint]],
                    QueryParameter(name=alias_for(param_name)),
                ]

                def provide_not_in_filter(**kwargs: Any) -> Optional[NotInCollectionFilter[Any]]:
                    values = kwargs.get(param_name)
                    return NotInCollectionFilter(field_name=field_name.name, values=values) if values else None

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
                    return_annotation=filter_return_type,
                )
                provide_not_in_filter.__annotations__ = {
                    param_name: annotation,
                    "return": filter_return_type,
                }
                return provide_not_in_filter  # pyright: ignore

            not_in_provider = create_not_in_filter_provider(resolved_field_def)  # pyright: ignore
            filters[f"{prefix_str}{resolved_field_def.name}_not_in_filter"] = Provide(
                not_in_provider, sync_to_thread=False
            )  # pyright: ignore

    # Add in filter providers
    if in_fields := config.get("in_fields"):
        # Get all field names, handling both strings and FieldNameType objects
        in_fields = {in_fields} if isinstance(in_fields, (str, FieldNameType)) else in_fields

        for field_def in in_fields:
            resolved_field_def = (
                FieldNameType(name=field_def, type_hint=str) if isinstance(field_def, str) else field_def
            )

            def create_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType = resolved_field_def,
            ) -> Callable[..., Optional[InCollectionFilter[Any]]]:
                param_name = f"{field_name.name}_in"
                filter_return_type: Any = cast("Any", Optional)[cast("Any", InCollectionFilter)[field_name.type_hint]]
                annotation: Any = cast("Any", Annotated)[
                    cast("Any", Optional)[cast("Any", list)[field_name.type_hint]],
                    QueryParameter(name=alias_for(param_name)),
                ]

                def provide_in_filter(**kwargs: Any) -> Optional[InCollectionFilter[Any]]:
                    values = kwargs.get(param_name)
                    return InCollectionFilter(field_name=field_name.name, values=values) if values else None

                provide_in_filter.__name__ = f"provide_in_filter_{field_name.name}"
                provide_in_filter.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
                    parameters=[
                        inspect.Parameter(
                            name=param_name,
                            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                            default=None,
                            annotation=annotation,
                        )
                    ],
                    return_annotation=filter_return_type,
                )
                provide_in_filter.__annotations__ = {
                    param_name: annotation,
                    "return": filter_return_type,
                }
                return provide_in_filter  # pyright: ignore

            in_provider = create_in_filter_provider(resolved_field_def)
            filters[f"{prefix_str}{resolved_field_def.name}_in_filter"] = Provide(in_provider, sync_to_thread=False)  # pyright: ignore

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
                    QueryParameter(name=alias_for(field_name.name)),
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
            filters[f"{prefix_str}{boolean_field_def.name}_boolean_filter"] = Provide(
                boolean_provider, sync_to_thread=False
            )

    if choice_fields := config.get("choice_fields"):
        for choice_field_def in normalize_choice_field_types(choice_fields):

            def create_choices_filter_provider(
                field_name: FieldNameType = choice_field_def,
            ) -> Callable[..., Optional[ChoicesFilter[Any]]]:
                param_name = f"{field_name.name}_choices"
                annotation: Any = cast("Any", Annotated)[
                    cast("Any", Optional)[cast("Any", list)[field_name.type_hint]],
                    QueryParameter(name=alias_for(field_name.name)),
                ]

                def provide_choices_filter(**kwargs: Any) -> Optional[ChoicesFilter[Any]]:
                    values = kwargs.get(param_name)
                    return ChoicesFilter(field_name=field_name.name, values=values) if values else None

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
            filters[f"{prefix_str}{choice_field_def.name}_choices_filter"] = Provide(
                choices_provider, sync_to_thread=False
            )

    if filter_fields_cfg := config.get("filter_fields"):
        field_specs = resolve_filter_fields(filter_fields_cfg, model)
        field_ignore_case = bool(config["search_ignore_case"]) if "search_ignore_case" in config else True
        field_escape_wildcards = bool(config.get("search_escape_wildcards", False))

        def _litestar_field_annotation(spec: FilterFieldSpec, alias: str) -> Any:
            return Annotated[
                filter_parameter_type(spec),
                QueryParameter(name=alias),
            ]

        for rel_path, local_field, group_specs in group_filter_fields(field_specs):
            # Length-prefix each hop so underscores cannot merge distinct paths.
            group_slug = (
                "rel_" + "_".join(f"{len(part)}_{part}" for part in rel_path) if rel_path else f"col_{local_field}"
            )
            field_provider = create_field_filter_provider(
                group_specs,
                rel_path=rel_path,
                alias_for=alias_for,
                annotation_factory=_litestar_field_annotation,
                name=f"provide_field_filter_{group_slug}",
                ignore_case=field_ignore_case,
                escape_wildcards=field_escape_wildcards,
            )
            filters[f"{prefix_str}field_{group_slug}_filter"] = Provide(field_provider, sync_to_thread=False)

    if clean_prefix and filters:
        ident = re.sub(r"\W+", "_", clean_prefix).strip("_")
        param_prefix = f"p_{ident}_" if ident and ident[0].isdigit() else (f"{ident}_" if ident else "scoped_")
        filters = {dep_key: _scope_filter_provider(provide, param_prefix) for dep_key, provide in filters.items()}

    if filters and include_aggregate:
        aggregate = _create_filter_aggregate_function(config, dep_defaults, filters)
        dependency = Provide(aggregate, sync_to_thread=False)
        dependency.parsed_fn_signature = ParsedSignature.from_signature(
            inspect.signature(aggregate), aggregate.__annotations__
        )
        filters[dep_defaults.FILTERS_DEPENDENCY_KEY] = dependency

    return filters


def _scope_filter_provider(provide: Provide, param_prefix: str) -> Provide:
    """Namespace a filter dependency callable's parameter names to avoid DI collisions."""
    dependency = provide.dependency
    signature = inspect.signature(dependency)
    annotations = getattr(dependency, "__annotations__", {})
    param_map: list[tuple[str, str]] = []
    parameters: list[inspect.Parameter] = []
    scoped_annotations: dict[str, Any] = {}
    for parameter in signature.parameters.values():
        scoped_name = parameter.name if parameter.name == "request" else f"{param_prefix}{parameter.name}"
        param_map.append((parameter.name, scoped_name))
        parameters.append(parameter.replace(name=scoped_name))
        if parameter.name in annotations:
            scoped_annotations[scoped_name] = annotations[parameter.name]
    if "return" in annotations:
        scoped_annotations["return"] = annotations["return"]

    def scoped_dependency(**kwargs: Any) -> Any:
        return dependency(**{orig: kwargs[scoped] for orig, scoped in param_map})

    scoped_dependency.__name__ = f"{param_prefix}{dependency.__name__}"
    scoped_signature = inspect.Signature(parameters, return_annotation=signature.return_annotation)
    scoped_dependency.__signature__ = scoped_signature  # type: ignore[attr-defined]
    scoped_dependency.__annotations__ = scoped_annotations
    scoped_provide = Provide(scoped_dependency, sync_to_thread=False)
    scoped_provide.parsed_fn_signature = ParsedSignature.from_signature(scoped_signature, scoped_annotations)
    return scoped_provide


def _create_filter_aggregate_function(
    config: FilterConfig,
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
    providers: Optional[dict[str, Provide]] = None,
) -> Callable[..., list[FilterTypes]]:
    """Build aggregate metadata from the registered dependencies themselves.

    Preserves historical filter output order by placing pagination before ``updated_at``.
    """
    if providers is None:
        providers = _create_statement_filters(config, dep_defaults, include_aggregate=False)
    keys = list(providers)
    pagination = dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY
    updated = dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY
    if pagination in keys and updated in keys:
        keys.remove(pagination)
        keys.insert(keys.index(updated), pagination)
    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    for key in keys:
        annotation = NamedDependency[SkipValidation[Any]]
        parameters.append(inspect.Parameter(key, inspect.Parameter.KEYWORD_ONLY, annotation=annotation))
        annotations[key] = annotation
    aggregate = partial(_aggregate_filters, tuple(keys))
    aggregate.__signature__ = inspect.Signature(parameters, return_annotation=list[FilterTypes])  # type: ignore[attr-defined]
    aggregate.__annotations__ = {**annotations, "return": list[FilterTypes]}
    return aggregate


def _aggregate_filters(keys: tuple[str, ...], **kwargs: Any) -> list[FilterTypes]:
    filters: list[FilterTypes] = []
    for key in keys:
        value = kwargs.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            filters.extend(cast("list[FilterTypes]", value))
            continue
        if isinstance(value, SearchFilter) and (value.field_name is None or value.value is None):  # pyright: ignore[reportUnnecessaryComparison]
            continue  # type: ignore[unreachable]
        if isinstance(value, OrderByFilter) and value.field_name is None:
            continue  # type: ignore[unreachable]
        filters.append(value)
    return filters

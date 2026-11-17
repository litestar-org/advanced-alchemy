# pyright: ignore
"""Application dependency providers generators for FastAPI.

This module contains functions to create dependency providers for filters,
similar to the Litestar extension, but tailored for FastAPI.
"""

import contextlib
import datetime as dt
import inspect
import logging
from collections.abc import AsyncGenerator, Generator
from functools import partial
from typing import (
    Annotated,
    Any,
    Callable,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)

from fastapi import Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.exceptions import ImproperConfigurationError, InvalidCursorError
from advanced_alchemy.extensions.fastapi.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.fastapi.extension import AdvancedAlchemy
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
    RelationshipFilter,
    SearchFilter,
    StatementFilter,
)
from advanced_alchemy.service import (
    Empty,
    EmptyType,
    ErrorMessages,
    LoadSpec,
    ServiceGroup,
    SQLAlchemyAsyncQueryService,
    SQLAlchemyAsyncRepositoryReadService,
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

logger = logging.getLogger("advanced_alchemy.extensions.fastapi")

T = TypeVar("T")
DTorNone = Optional[dt.datetime]
StringOrNone = Optional[str]
UuidOrNone = Optional[str]  # FastAPI doesn't automatically parse UUIDs from query params like Litestar
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
    "dep_cache",
    "provide_filters",
    "provide_service",
)

_CACHE_NAMESPACE = "advanced_alchemy.extensions.fastapi.providers"


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
    CURSOR_FILTER_DEPENDENCY_KEY: str = "cursor_filter"
    """Key for the cursor pagination dependency."""
    DEFAULT_PAGINATION_SIZE: int = 20
    """Default pagination size."""


DEPENDENCY_DEFAULTS = DependencyDefaults()


dep_cache = DependencyCache()


def _should_commit_for_status(status_code: int, commit_mode: str) -> bool:
    """Determine if we should commit based on status code and commit mode.

    Args:
        status_code: The HTTP response status code.
        commit_mode: The configured commit mode.

    Returns:
        True if the transaction should be committed, False otherwise.
    """
    if commit_mode == "manual":
        return False
    if commit_mode == "autocommit":
        return 200 <= status_code < 300  # noqa: PLR2004
    if commit_mode == "autocommit_include_redirect":
        return 200 <= status_code < 400  # noqa: PLR2004
    return False


_ASYNC_SERVICE_BASES: tuple[type[Any], ...] = (
    SQLAlchemyAsyncQueryService,
    SQLAlchemyAsyncRepositoryReadService,
    SQLAlchemyAsyncRepositoryService,
)


def _clear_request_state(request: Request, session_key: str) -> None:
    """Clear managed session attributes from FastAPI request state."""
    for attr in (
        session_key,
        f"{session_key}_generator_managed",
        f"{session_key}_response_status",
    ):
        with contextlib.suppress(Exception):
            delattr(request.state, attr)


def _is_async_service_target(
    service_class: type[Any],
    extension: AdvancedAlchemy,
    key: Optional[str],
) -> bool:
    """Return whether a service or ServiceGroup targets async sessions."""
    if issubclass(service_class, ServiceGroup):
        is_async = service_class.is_async_group()
        if is_async is not None:
            return is_async
        config: Any = extension.get_config(key)
        if isinstance(config, SQLAlchemyAsyncConfig):
            return True
        if isinstance(config, SQLAlchemySyncConfig):
            return False
        return inspect.isasyncgenfunction(extension.provide_session(key))
    return issubclass(service_class, _ASYNC_SERVICE_BASES)


@overload
def provide_service(
    service_class: type["AsyncServiceT_co"],
    /,
    extension: AdvancedAlchemy,
    key: Optional[str] = None,
    statement: Optional[Select[Any]] = None,
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
    statement: Optional[Select[Any]] = None,
    error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
    load: Optional[LoadSpec] = None,
    execution_options: Optional[dict[str, Any]] = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Generator[SyncServiceT_co, None, None]]: ...


@overload
def provide_service(
    service_class: type["ServiceGroupT"],
    /,
    extension: AdvancedAlchemy,
    key: Optional[str] = None,
    statement: Optional[Select[Any]] = None,
    error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
    load: Optional[LoadSpec] = None,
    execution_options: Optional[dict[str, Any]] = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[..., Union[AsyncGenerator[ServiceGroupT, None], Generator[ServiceGroupT, None, None]]]: ...


def provide_service(  # noqa: C901, PLR0915
    service_class: type[Union["AsyncServiceT_co", "SyncServiceT_co", "ServiceGroupT"]],
    /,
    extension: AdvancedAlchemy,
    key: Optional[str] = None,
    statement: Optional[Select[Any]] = None,
    error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
    load: Optional[LoadSpec] = None,
    execution_options: Optional[dict[str, Any]] = None,
    uniquify: Optional[bool] = None,
    count_with_window_function: Optional[bool] = None,
) -> Callable[
    ...,
    Union[
        AsyncGenerator[AsyncServiceT_co, None],
        Generator[SyncServiceT_co, None, None],
        AsyncGenerator[ServiceGroupT, None],
        Generator[ServiceGroupT, None, None],
    ],
]:
    """Create a FastAPI dependency provider for a service or ServiceGroup.

    Returns:
        A generator-based FastAPI dependency provider managing service and session lifecycle.
    """
    is_group = issubclass(service_class, ServiceGroup)
    if is_group and (statement is not None or load is not None):
        msg = "ServiceGroup does not support group-level 'statement' or 'load'; set them on each service class."
        raise ImproperConfigurationError(msg)

    if _is_async_service_target(service_class, extension, key):
        async_config = cast("Optional[SQLAlchemyAsyncConfig]", extension.get_config(key))

        async def provide_async_service(
            request: Request,
            db_session: AsyncSession = Depends(extension.provide_session(key)),  # noqa: B008
        ) -> AsyncGenerator[Union[AsyncServiceT_co, ServiceGroupT], None]:
            session_key = async_config.session_key if async_config else "db_session"
            setattr(request.state, f"{session_key}_generator_managed", True)

            exc_info: Optional[BaseException] = None
            try:
                context_manager: Any = (
                    cast("type[ServiceGroup]", service_class).new(
                        session=db_session,
                        error_messages=error_messages,
                        execution_options=execution_options,
                        uniquify=uniquify,
                        count_with_window_function=count_with_window_function,
                    )
                    if is_group
                    else cast("type[SQLAlchemyAsyncRepositoryService[Any, Any]]", service_class).new(
                        session=db_session,
                        statement=statement,
                        config=async_config,
                        error_messages=error_messages,
                        load=load,
                        execution_options=execution_options,
                        uniquify=uniquify,
                        count_with_window_function=count_with_window_function,
                    )
                )
                async with context_manager as service:
                    yield cast("Union[AsyncServiceT_co, ServiceGroupT]", service)
            except BaseException as e:
                exc_info = e
                raise
            finally:
                response_status = getattr(request.state, f"{session_key}_response_status", None)
                commit_mode = async_config.commit_mode if async_config else "manual"
                should_commit = (
                    exc_info is None
                    and response_status is not None
                    and _should_commit_for_status(response_status, commit_mode)
                )

                try:
                    if should_commit:
                        await db_session.commit()
                    else:
                        await db_session.rollback()
                except Exception:
                    if exc_info is not None:
                        logger.debug("Session commit/rollback failed during cleanup", exc_info=True)
                    else:
                        raise

                try:
                    await db_session.close()
                except Exception:
                    if exc_info is not None:
                        logger.debug("Session close failed during cleanup", exc_info=True)
                    else:
                        raise

                _clear_request_state(request, session_key)

        return cast(
            "Callable[..., Union[AsyncGenerator[AsyncServiceT_co, None], Generator[SyncServiceT_co, None, None], AsyncGenerator[ServiceGroupT, None], Generator[ServiceGroupT, None, None]]]",
            provide_async_service,
        )

    sync_config = cast("Optional[SQLAlchemySyncConfig]", extension.get_config(key))

    def provide_sync_service(
        request: Request,
        db_session: Session = Depends(extension.provide_session(key)),  # noqa: B008
    ) -> Generator[Union[SyncServiceT_co, ServiceGroupT], None, None]:
        session_key = sync_config.session_key if sync_config else "db_session"
        setattr(request.state, f"{session_key}_generator_managed", True)

        exc_info: Optional[BaseException] = None
        try:
            context_manager: Any = (
                cast("type[ServiceGroup]", service_class).new(
                    session=db_session,
                    error_messages=error_messages,
                    execution_options=execution_options,
                    uniquify=uniquify,
                    count_with_window_function=count_with_window_function,
                )
                if is_group
                else cast("type[SQLAlchemySyncRepositoryService[Any, Any]]", service_class).new(
                    session=db_session,
                    statement=statement,
                    config=sync_config,
                    error_messages=error_messages,
                    load=load,
                    execution_options=execution_options,
                    uniquify=uniquify,
                    count_with_window_function=count_with_window_function,
                )
            )
            with context_manager as service:
                yield cast("Union[SyncServiceT_co, ServiceGroupT]", service)
        except BaseException as e:
            exc_info = e
            raise
        finally:
            response_status = getattr(request.state, f"{session_key}_response_status", None)
            commit_mode = sync_config.commit_mode if sync_config else "manual"
            should_commit = (
                exc_info is None
                and response_status is not None
                and _should_commit_for_status(response_status, commit_mode)
            )

            try:
                if should_commit:
                    db_session.commit()
                else:
                    db_session.rollback()
            except Exception:
                if exc_info is not None:
                    logger.debug("Session commit/rollback failed during cleanup", exc_info=True)
                else:
                    raise

            try:
                db_session.close()
            except Exception:
                if exc_info is not None:
                    logger.debug("Session close failed during cleanup", exc_info=True)
                else:
                    raise

            _clear_request_state(request, session_key)

    return cast(
        "Callable[..., Union[AsyncGenerator[AsyncServiceT_co, None], Generator[SyncServiceT_co, None, None], AsyncGenerator[ServiceGroupT, None], Generator[ServiceGroupT, None, None]]]",
        provide_sync_service,
    )


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
    entries: list[tuple[str, Any, Any]] = []
    for spec in filterset_type.parameter_specs():
        alias = f"{prefix.rstrip('_')}_{spec.param_name}" if prefix else spec.param_name
        entries.append((spec.param_name, filter_parameter_type(spec), Query(alias=alias)))
    pagination_type = config.get("pagination_type")
    if pagination_type:
        entries.extend(
            [
                ("cursor", Optional[str], Query(alias=aliases.get("cursor", "cursor")))
                if pagination_type == "cursor"
                else ("page", Optional[int], Query(alias=aliases.get("current_page", "currentPage"), ge=1)),
                (
                    "pageSize",
                    Optional[int],
                    Query(alias=aliases.get("page_size", "pageSize"), ge=1, le=max_pagination_size),
                ),
            ]
        )
    if config.get("sort_fields") or config.get("sort_field"):
        entries.extend(
            [
                ("orderBy", Optional[list[str]], Query(alias=aliases.get("order_by", "orderBy"))),
                ("sortOrder", Optional[Literal["asc", "desc"]], Query(alias=aliases.get("sort_order", "sortOrder"))),
            ]
        )
    if config.get("search"):
        entries.append(("searchString", Optional[str], Query(alias=aliases.get("search_string", "searchString"))))
    for name, annotation, query_param in entries:
        annotated = cast("Any", Annotated)[annotation, query_param]
        annotations[name] = annotated
        parameters.append(inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=annotated, default=None))
    annotations["request"] = Request
    parameters.append(inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY, annotation=Request))

    def provide_filterset(*, request: Request, **kwargs: Any) -> list[FilterSet[Any]]:
        try:
            instance = filterset_type(
                cursor_defaults=_cursor_defaults(request),
                require_cursor_secret=True,
                **{key: value for key, value in kwargs.items() if value is not None},
            )
            return [instance]  # noqa: TRY300
        except (ValueError, TypeError) as exc:
            raise RequestValidationError(errors=[{"loc": ["query"], "msg": str(exc), "type": "value_error"}]) from exc

    provide_filterset.__name__ = f"provide_{filterset_type.__name__}"
    provide_filterset.__annotations__ = {**annotations, "return": list[FilterSet[Any]]}
    provide_filterset.__signature__ = inspect.Signature(parameters, return_annotation=list[FilterSet[Any]])  # type: ignore[attr-defined]
    return provide_filterset


@overload
def provide_filters(
    config: FilterConfig, dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS, model: Optional[type[Any]] = None
) -> Callable[..., list[FilterTypes]]: ...


@overload
def provide_filters(
    config: type[FilterSet[Any]],
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
    model: Optional[type[Any]] = None,
) -> Callable[..., list[FilterSet[Any]]]: ...


def provide_filters(
    config: Union[FilterConfig, type[FilterSet[Any]]],
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
    model: Optional[type[Any]] = None,
) -> Union[Callable[..., list[FilterTypes]], Callable[..., list[FilterSet[Any]]]]:
    """Create FastAPI dependency providers for filters based on the provided configuration.

    Returns:
        A FastAPI dependency provider function that aggregates multiple filter dependencies.
    """
    if isinstance(config, type):
        return _create_filterset_dependency(config, dep_defaults)
    resolve_pagination_bounds(config, default_size=dep_defaults.DEFAULT_PAGINATION_SIZE)
    filter_keys = {
        "id_filter",
        "created_at",
        "updated_at",
        "pagination_type",
        "search",
        "sort_field",
        "sort_fields",
        "not_in_fields",
        "in_fields",
        "boolean_fields",
        "choice_fields",
        "filter_fields",
    }

    has_filters = False
    for key in filter_keys:
        value = config.get(key)
        if value is not None and value is not False and value != []:
            has_filters = True
            break

    if not has_filters:
        return list

    aliases = resolve_filter_aliases(config, model=model)
    cache_key = filter_cache_key(_CACHE_NAMESPACE, config, dep_defaults, aliases, model=model)

    cached_dep = cast("Optional[Callable[..., list[FilterTypes]]]", dep_cache.get_dependencies(cache_key))
    if cached_dep is not None:
        return cached_dep

    dep = _create_filter_aggregate_function_fastapi(config, dep_defaults, aliases=aliases, model=model)
    dep_cache.add_dependencies(cache_key, dep)
    return dep


_CollectionFilterType = Union[InCollectionFilter[Any], NotInCollectionFilter[Any], ChoicesFilter[Any]]


def _build_collection_filter_provider(
    *,
    filter_cls: type[_CollectionFilterType],
    field_name: str,
    item_type: Any,
    collection_cls: Union[type[list[Any]], type[set[Any]]],
    param_name: str,
    query_alias: str,
    query_description: str,
    provider_name: str,
) -> Any:
    """Build the ``Annotated[Optional[Filter[item_type]], Depends(...)]`` annotation for a collection filter.

    Args:
        filter_cls: The collection filter class the dependency produces.
        field_name: Model field the filter applies to.
        item_type: Element type of the collection query parameter.
        collection_cls: Container the query parameter values are collected into.
        param_name: Name of the dependency callable's query parameter.
        query_alias: Query string alias for the parameter.
        query_description: OpenAPI description for the parameter.
        provider_name: ``__name__`` assigned to the dependency callable.

    Returns:
        The annotation to attach to the aggregate filter dependency parameter.
    """
    collection_type: Any = cast("Any", collection_cls)[item_type]
    param_type: Any = cast("Any", Optional)[collection_type]
    query_annotation: Any = cast("Any", Annotated)[param_type, Query(alias=query_alias, description=query_description)]
    filter_type: Any = cast("Any", filter_cls)[item_type]
    return_annotation: Any = cast("Any", Optional)[filter_type]

    def provide_filter(*args: Any, **kwargs: Any) -> Optional[_CollectionFilterType]:
        values = args[0] if args else kwargs.get(param_name)
        return filter_cls(field_name=field_name, values=values) if values else None

    provide_filter.__name__ = provider_name
    provide_filter.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters=[
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=query_annotation,
            )
        ],
        return_annotation=return_annotation,
    )
    provide_filter.__annotations__ = {
        param_name: query_annotation,
        "return": return_annotation,
    }
    return cast("Any", Annotated)[return_annotation, Depends(provide_filter)]


def _create_cursor_filter_provider(
    settings: CursorSettings,
    alias_for: Callable[[str], str],
    default_size: int,
    max_size: Optional[int],
    *,
    repeatable_order: bool,
) -> Callable[..., CursorFilter]:
    """Build the cursor pagination dependency; ordering parameters appear only when sorting is configured."""
    cursor_alias = alias_for("cursor")
    size_alias = alias_for("page_size")
    cursor_query = Query(alias=cursor_alias, description="Token from a previous page's cursor.")
    size_query = Query(ge=1, le=max_size, alias=size_alias, description="Number of items per page.")

    def build(
        request: Request,
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
        except InvalidCursorError as exc:
            raise RequestValidationError(
                errors=[{"loc": ["query", cursor_alias], "msg": str(exc), "type": "value_error"}]
            ) from exc
        except ValueError as exc:
            order_alias = alias_for("order_by")
            raise RequestValidationError(
                errors=[{"loc": ["query", order_alias], "msg": str(exc), "type": "value_error"}]
            ) from exc

    def provide_cursor_pagination(
        request: Request,
        cursor: Annotated[Optional[str], cursor_query] = None,
        page_size: Annotated[int, size_query] = default_size,
    ) -> CursorFilter:
        return build(request, cursor, page_size, None, None)

    if not settings.allowed_fields:
        return provide_cursor_pagination

    order_query = Query(
        alias=alias_for("order_by"),
        description=f"Sort fields (prefix '-' for descending). Allowed: {', '.join(sorted(settings.allowed_fields))}",
    )
    sort_order_query = Query(alias=alias_for("sort_order"), description="Sort order ('asc' or 'desc').")

    def provide_cursor_pagination_ordered(
        request: Request,
        cursor: Annotated[Optional[str], cursor_query] = None,
        page_size: Annotated[int, size_query] = default_size,
        order_by: Annotated[Optional[str], order_query] = None,
        sort_order: Annotated[Optional[SortOrder], sort_order_query] = None,
    ) -> CursorFilter:
        return build(request, cursor, page_size, order_by, sort_order)

    def provide_cursor_pagination_multi_ordered(
        request: Request,
        cursor: Annotated[Optional[str], cursor_query] = None,
        page_size: Annotated[int, size_query] = default_size,
        order_by: Annotated[Optional[list[str]], order_query] = None,
        sort_order: Annotated[Optional[SortOrder], sort_order_query] = None,
    ) -> CursorFilter:
        return build(request, cursor, page_size, order_by, sort_order)

    return provide_cursor_pagination_multi_ordered if repeatable_order else provide_cursor_pagination_ordered


def _cursor_defaults(request: Request) -> Optional[CursorDefaults]:
    """Return the cursor token options of the application's Advanced Alchemy extension, if one is registered."""
    extension = getattr(request.app.state, "advanced_alchemy", None)
    return extension.cursor_defaults if extension is not None else None


def _create_filter_aggregate_function_fastapi(  # noqa: C901, PLR0915
    config: FilterConfig,
    dep_defaults: DependencyDefaults = DEPENDENCY_DEFAULTS,
    *,
    aliases: Optional[dict[str, str]] = None,
    model: Optional[type[Any]] = None,
) -> Callable[..., list[FilterTypes]]:
    """Create a FastAPI dependency provider function that aggregates multiple filter dependencies.

    Returns a fresh ``partial(_aggregate_filter_function)`` per configuration so assigning
    ``__signature__`` and ``__annotations__`` does not mutate previously constructed
    dependencies.

    Returns:
        A FastAPI dependency provider function that aggregates multiple filter dependencies.
    """
    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}
    alias_for = (resolve_filter_aliases(config, model=model) if aliases is None else aliases).__getitem__

    if (id_filter := config.get("id_filter", False)) is not False:
        id_dep_annotation = _build_collection_filter_provider(
            filter_cls=InCollectionFilter,
            field_name=config.get("id_field", "id"),
            item_type=id_filter,
            collection_cls=list,
            param_name="ids",
            query_alias=alias_for("ids"),
            query_description="IDs to filter by.",
            provider_name="provide_id_filter",
        )
        params.append(
            inspect.Parameter(
                name=dep_defaults.ID_FILTER_DEPENDENCY_KEY,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=id_dep_annotation,
            )
        )
        annotations[dep_defaults.ID_FILTER_DEPENDENCY_KEY] = id_dep_annotation

    # Add created_at filter providers
    if config.get("created_at", False):
        created_before_alias = alias_for("created_before")
        created_after_alias = alias_for("created_after")

        def provide_created_at_filter(
            created_at_before: Annotated[
                Optional[str],
                Query(
                    alias=created_before_alias,
                    description="Filter by created date before this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
            created_at_after: Annotated[
                Optional[str],
                Query(
                    alias=created_after_alias,
                    description="Filter by created date after this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
        ) -> Optional[BeforeAfterFilter]:
            before_dt = None
            after_dt = None

            # Validate both parameters regardless of endpoint path
            if created_at_before is not None:
                try:
                    before_dt = dt.datetime.fromisoformat(created_at_before.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", created_before_alias], "msg": "Invalid date format"}]
                    ) from e

            if created_at_after is not None:
                try:
                    after_dt = dt.datetime.fromisoformat(created_at_after.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", created_after_alias], "msg": "Invalid date format"}]
                    ) from e

            return (
                BeforeAfterFilter(field_name="created_at", before=before_dt, after=after_dt)
                if before_dt or after_dt
                else None  # pyright: ignore
            )

        param_name = dep_defaults.CREATED_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[Optional[BeforeAfterFilter], Depends(provide_created_at_filter)],
            )
        )
        annotations[param_name] = Annotated[Optional[BeforeAfterFilter], Depends(provide_created_at_filter)]

    # Add updated_at filter providers
    if config.get("updated_at", False):
        updated_before_alias = alias_for("updated_before")
        updated_after_alias = alias_for("updated_after")

        def provide_updated_at_filter(
            updated_at_before: Annotated[
                Optional[str],
                Query(
                    alias=updated_before_alias,
                    description="Filter by updated date before this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
            updated_at_after: Annotated[
                Optional[str],
                Query(
                    alias=updated_after_alias,
                    description="Filter by updated date after this timestamp.",
                    json_schema_extra={"format": "date-time"},
                ),
            ] = None,
        ) -> Optional[BeforeAfterFilter]:
            before_dt = None
            after_dt = None

            # Validate both parameters regardless of endpoint path
            if updated_at_before is not None:
                try:
                    before_dt = dt.datetime.fromisoformat(updated_at_before.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", updated_before_alias], "msg": "Invalid date format"}]
                    ) from e

            if updated_at_after is not None:
                try:
                    after_dt = dt.datetime.fromisoformat(updated_at_after.replace("Z", "+00:00"))
                except (ValueError, TypeError, AttributeError) as e:
                    raise RequestValidationError(
                        errors=[{"loc": ["query", updated_after_alias], "msg": "Invalid date format"}]
                    ) from e

            return (
                BeforeAfterFilter(field_name="updated_at", before=before_dt, after=after_dt)
                if before_dt or after_dt
                else None  # pyright: ignore
            )

        param_name = dep_defaults.UPDATED_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[Optional[BeforeAfterFilter], Depends(provide_updated_at_filter)],
            )
        )
        annotations[param_name] = Annotated[Optional[BeforeAfterFilter], Depends(provide_updated_at_filter)]

    # Add pagination filter providers
    default_pagination_size, max_pagination_size = resolve_pagination_bounds(
        config, default_size=dep_defaults.DEFAULT_PAGINATION_SIZE
    )
    if config.get("pagination_type") == "limit_offset":

        def provide_limit_offset_pagination(
            current_page: Annotated[
                int,
                Query(
                    ge=1,
                    alias=alias_for("current_page"),
                    description="Page number for pagination.",
                ),
            ] = 1,
            page_size: Annotated[
                int,
                Query(
                    ge=1,
                    le=max_pagination_size,
                    alias=alias_for("page_size"),
                    description="Number of items per page.",
                ),
            ] = default_pagination_size,
        ) -> LimitOffsetFilter:
            return LimitOffsetFilter(limit=page_size, offset=page_size * (current_page - 1))

        param_name = dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[LimitOffsetFilter, Depends(provide_limit_offset_pagination)],
            )
        )
        annotations[param_name] = Annotated[LimitOffsetFilter, Depends(provide_limit_offset_pagination)]
    elif config.get("pagination_type") == "cursor":
        cursor_provider = _create_cursor_filter_provider(
            resolve_cursor_settings(config, model),
            alias_for,
            default_pagination_size,
            max_pagination_size,
            repeatable_order=bool(config.get("sort_fields")),
        )
        param_name = dep_defaults.CURSOR_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[CursorFilter, Depends(cursor_provider)],
            )
        )
        annotations[param_name] = Annotated[CursorFilter, Depends(cursor_provider)]

    if search_fields := config.get("search"):
        parsed_field_names = set(search_fields.split(",")) if isinstance(search_fields, str) else set(search_fields)

        def provide_search_filter(
            search_string: Annotated[
                Optional[str],
                Query(
                    alias=alias_for("search_string"),
                    description="Search term.",
                ),
            ] = None,
            ignore_case: Annotated[
                Optional[bool],
                Query(
                    alias=alias_for("search_ignore_case"),
                    description="Whether search should be case-insensitive.",
                ),
            ] = config.get("search_ignore_case", False),
        ) -> SearchFilter:
            return SearchFilter(
                field_name=parsed_field_names,
                value=search_string,  # type: ignore[arg-type]
                ignore_case=ignore_case or False,
                escape_wildcards=config.get("search_escape_wildcards", False),
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
    order_by_provided = config.get("pagination_type") != "cursor"
    if order_by_provided and (sort_fields_cfg := config.get("sort_fields")):
        allowed_sort_fields = frozenset(normalize_sort_fields(sort_fields_cfg, model=model))
        raw_default_sort = config.get("sort_field")
        default_sort_field = normalize_sort_field(raw_default_sort) if raw_default_sort else None
        if default_sort_field is not None and default_sort_field not in allowed_sort_fields:
            msg = f"Default sort_field {default_sort_field!r} must be included in sort_fields"
            raise ImproperConfigurationError(msg)
        sort_order_default = config.get("sort_order", "desc")
        sort_nulls_default = config.get("sort_nulls")
        order_by_alias = alias_for("order_by")
        sort_order_alias = alias_for("sort_order")
        allowed_display = ", ".join(sorted(allowed_sort_fields))

        def provide_order_by_multi(
            field_name: Annotated[
                Optional[list[str]],
                Query(
                    alias=order_by_alias,
                    description=f"Repeatable sort fields (prefix '-' for descending). Allowed: {allowed_display}",
                ),
            ] = None,
            sort_order: Annotated[
                Optional[SortOrder],
                Query(
                    alias=sort_order_alias,
                    description="Sort order ('asc' or 'desc').",
                ),
            ] = None,
        ) -> list[OrderByFilter]:
            try:
                return build_order_by_filters(
                    field_name,
                    sort_order,
                    allowed_fields=allowed_sort_fields,
                    default_field=default_sort_field,
                    default_order=sort_order_default,
                    nulls=sort_nulls_default,
                )
            except ValueError as exc:
                raise RequestValidationError(errors=[{"loc": ["query", order_by_alias], "msg": str(exc)}]) from exc

        param_name = dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[list[OrderByFilter], Depends(provide_order_by_multi)],
            )
        )
        annotations[param_name] = Annotated[list[OrderByFilter], Depends(provide_order_by_multi)]
    elif order_by_provided and (sort_field := config.get("sort_field")):
        sort_field_default = normalize_sort_field(sort_field)
        sort_order_default = config.get("sort_order", "desc")
        sort_nulls_default = config.get("sort_nulls")

        def provide_order_by(
            field_name: Annotated[
                str,
                Query(
                    alias=alias_for("order_by"),
                    description="Field to order by.",
                ),
            ] = sort_field_default,
            sort_order: Annotated[
                Optional[SortOrder],
                Query(
                    alias=alias_for("sort_order"),
                    description="Sort order ('asc' or 'desc').",
                ),
            ] = sort_order_default,
        ) -> OrderByFilter:
            return OrderByFilter(
                field_name=field_name, sort_order=sort_order or sort_order_default, nulls=sort_nulls_default
            )

        param_name = dep_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY
        params.append(
            inspect.Parameter(
                name=param_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[OrderByFilter, Depends(provide_order_by)],
            )
        )
        annotations[param_name] = Annotated[OrderByFilter, Depends(provide_order_by)]

    if not_in_fields := config.get("not_in_fields"):
        for field_def in normalize_field_name_types(not_in_fields):
            not_in_dep_annotation = _build_collection_filter_provider(
                filter_cls=NotInCollectionFilter,
                field_name=field_def.name,
                item_type=field_def.type_hint,
                collection_cls=set,
                param_name="values",
                query_alias=alias_for(f"{field_def.name}_not_in"),
                query_description=f"Filter {field_def.name} not in values",
                provider_name=f"provide_not_in_filter_{field_def.name}",
            )
            param_name = f"{field_def.name}_not_in_filter"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=not_in_dep_annotation,
                )
            )
            annotations[param_name] = not_in_dep_annotation

    if in_fields := config.get("in_fields"):
        for field_def in normalize_field_name_types(in_fields):
            in_dep_annotation = _build_collection_filter_provider(
                filter_cls=InCollectionFilter,
                field_name=field_def.name,
                item_type=field_def.type_hint,
                collection_cls=set,
                param_name="values",
                query_alias=alias_for(f"{field_def.name}_in"),
                query_description=f"Filter {field_def.name} in values",
                provider_name=f"provide_in_filter_{field_def.name}",
            )
            param_name = f"{field_def.name}_in_filter"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=in_dep_annotation,
                )
            )
            annotations[param_name] = in_dep_annotation

    if boolean_fields := config.get("boolean_fields"):
        for boolean_field_def in normalize_field_name_types(boolean_fields):

            def create_boolean_filter_provider(
                field_name: FieldNameType = boolean_field_def,
            ) -> Callable[..., Optional[BooleanFilter]]:
                def provide_boolean_filter(
                    value: Annotated[
                        Optional[bool],
                        Query(
                            alias=alias_for(field_name.name),
                            description=f"Filter {field_name.name} by boolean value",
                        ),
                    ] = None,
                ) -> Optional[BooleanFilter]:
                    return BooleanFilter(field_name=field_name.name, value=value) if value is not None else None

                return provide_boolean_filter

            boolean_provider = create_boolean_filter_provider()
            param_name = f"{boolean_field_def.name}_boolean_filter"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=Annotated[Optional[BooleanFilter], Depends(boolean_provider)],
                )
            )
            annotations[param_name] = Annotated[Optional[BooleanFilter], Depends(boolean_provider)]

    if choice_fields := config.get("choice_fields"):
        for choice_field_def in normalize_choice_field_types(choice_fields):
            choices_dep_annotation = _build_collection_filter_provider(
                filter_cls=ChoicesFilter,
                field_name=choice_field_def.name,
                item_type=choice_field_def.type_hint,
                collection_cls=list,
                param_name="values",
                query_alias=alias_for(choice_field_def.name),
                query_description=f"Filter {choice_field_def.name} by allowed choices",
                provider_name=f"provide_choices_filter_{choice_field_def.name}",
            )
            param_name = f"{choice_field_def.name}_choices_filter"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=choices_dep_annotation,
                )
            )
            annotations[param_name] = choices_dep_annotation

    if filter_fields_cfg := config.get("filter_fields"):
        field_specs = resolve_filter_fields(filter_fields_cfg, model)
        field_ignore_case = bool(config["search_ignore_case"]) if "search_ignore_case" in config else True
        field_escape_wildcards = bool(config.get("search_escape_wildcards", False))

        def _fastapi_field_annotation(spec: FilterFieldSpec, alias: str) -> Any:
            return Annotated[
                filter_parameter_type(spec),
                Query(
                    alias=alias,
                    description=f"Filter {spec.field_path} ({spec.operator}).",
                ),
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
                annotation_factory=_fastapi_field_annotation,
                name=f"provide_field_filter_{group_slug}",
                ignore_case=field_ignore_case,
                escape_wildcards=field_escape_wildcards,
            )
            dep_return_type: Any = Optional[RelationshipFilter] if rel_path else Optional[list[StatementFilter]]
            param_name = f"field_{group_slug}_filter"
            params.append(
                inspect.Parameter(
                    name=param_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=Annotated[dep_return_type, Depends(field_provider)],
                )
            )
            annotations[param_name] = Annotated[dep_return_type, Depends(field_provider)]

    aggregate_filters = partial(_aggregate_filter_function)

    aggregate_filters.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters=params,
        return_annotation=list[FilterTypes],
    )

    aggregate_filters.__annotations__ = {**annotations, "return": list[FilterTypes]}
    return aggregate_filters


def _aggregate_filter_function(**kwargs: Any) -> list[FilterTypes]:
    filters: list[FilterTypes] = []
    for filter_value in kwargs.values():
        if filter_value is None:
            continue
        if isinstance(filter_value, list):
            filters.extend(cast("list[FilterTypes]", filter_value))
        elif isinstance(filter_value, SearchFilter) and filter_value.value is None:  # pyright: ignore # noqa: SIM114
            continue  # type: ignore
        elif isinstance(filter_value, OrderByFilter) and filter_value.field_name is None:  # pyright: ignore
            continue  # type: ignore
        else:
            filters.append(cast("FilterTypes", filter_value))
    return filters

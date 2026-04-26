# pyright: ignore
"""Application dependency providers generators for FastAPI.

This module contains functions to create dependency providers for filters,
similar to the Litestar extension, but tailored for FastAPI.
"""

import contextlib
import datetime
import inspect
import logging
from collections.abc import AsyncGenerator, Generator
from typing import (
    TYPE_CHECKING,
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
from advanced_alchemy.utils.dependencies import DependencyCache, FieldNameType, FilterConfig, make_hashable
from advanced_alchemy.utils.text import camelize

logger = logging.getLogger("advanced_alchemy.extensions.fastapi")

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
AsyncServiceT_co = TypeVar("AsyncServiceT_co", bound=SQLAlchemyAsyncRepositoryService[Any, Any], covariant=True)
SyncServiceT_co = TypeVar("SyncServiceT_co", bound=SQLAlchemySyncRepositoryService[Any, Any], covariant=True)

__all__ = (
    "DEPENDENCY_DEFAULTS",
    "DependencyCache",
    "DependencyDefaults",
    "FieldNameType",
    "FilterConfig",
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


def _normalize_field_name_types(
    field_definitions: Union[str, FieldNameType, set[FieldNameType], list[Union[str, FieldNameType]]],
) -> set[FieldNameType]:
    raw_fields = {field_definitions} if isinstance(field_definitions, (str, FieldNameType)) else set(field_definitions)
    return {
        FieldNameType(name=field_definition, type_hint=str) if isinstance(field_definition, str) else field_definition
        for field_definition in raw_fields
    }


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


def provide_service(  # noqa: C901, PLR0915
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

    This function creates a generator-based dependency that manages
    the service lifecycle. The generator owns the session lifecycle
    and handles commit/rollback/close operations to ensure proper
    connection pool management (especially important for asyncpg).

    Returns:
        A dependency provider for the service.
    """
    if issubclass(service_class, SQLAlchemyAsyncRepositoryService) or service_class is SQLAlchemyAsyncRepositoryService:  # type: ignore[comparison-overlap]
        async_config = cast("Optional[SQLAlchemyAsyncConfig]", extension.get_config(key))

        async def provide_async_service(
            request: Request,
            db_session: AsyncSession = Depends(extension.provide_session(key)),  # noqa: B008
        ) -> AsyncGenerator[AsyncServiceT_co, None]:  # type: ignore[union-attr,unused-ignore]
            session_key = async_config.session_key if async_config else "db_session"

            # Mark session as generator-managed to prevent middleware cleanup
            setattr(request.state, f"{session_key}_generator_managed", True)

            exc_info: Optional[BaseException] = None
            try:
                async with service_class.new(  # type: ignore[union-attr,unused-ignore]
                    session=db_session,  # type: ignore[arg-type, unused-ignore]
                    statement=statement,
                    config=async_config,  # type: ignore[arg-type]
                    error_messages=error_messages,
                    load=load,
                    execution_options=execution_options,
                    uniquify=uniquify,
                    count_with_window_function=count_with_window_function,
                ) as service:
                    yield service
            except BaseException as e:
                exc_info = e
                raise
            finally:
                # Get response status stored by middleware
                response_status = getattr(request.state, f"{session_key}_response_status", None)
                commit_mode = async_config.commit_mode if async_config else "manual"

                should_commit = (
                    exc_info is None
                    and response_status is not None
                    and _should_commit_for_status(response_status, commit_mode)
                )

                # Each cleanup operation is individually protected so that failures
                # in one step do not prevent subsequent steps or mask the original exception.
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

                # Clean up request state
                for attr in [
                    session_key,
                    f"{session_key}_generator_managed",
                    f"{session_key}_response_status",
                ]:
                    with contextlib.suppress(Exception):
                        delattr(request.state, attr)

        return provide_async_service

    sync_config = cast("Optional[SQLAlchemySyncConfig]", extension.get_config(key))

    def provide_sync_service(
        request: Request,
        db_session: Session = Depends(extension.provide_session(key)),  # noqa: B008
    ) -> Generator[SyncServiceT_co, None, None]:
        session_key = sync_config.session_key if sync_config else "db_session"

        # Mark session as generator-managed to prevent middleware cleanup
        setattr(request.state, f"{session_key}_generator_managed", True)

        exc_info: Optional[BaseException] = None
        try:
            with service_class.new(
                session=db_session,  # type: ignore[arg-type, unused-ignore]
                statement=statement,
                config=sync_config,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
            ) as service:
                yield service
        except BaseException as e:
            exc_info = e
            raise
        finally:
            # Get response status stored by middleware
            response_status = getattr(request.state, f"{session_key}_response_status", None)
            commit_mode = sync_config.commit_mode if sync_config else "manual"

            should_commit = (
                exc_info is None
                and response_status is not None
                and _should_commit_for_status(response_status, commit_mode)
            )

            # Each cleanup operation is individually protected so that failures
            # in one step do not prevent subsequent steps or mask the original exception.
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

            # Clean up request state
            for attr in [
                session_key,
                f"{session_key}_generator_managed",
                f"{session_key}_response_status",
            ]:
                with contextlib.suppress(Exception):
                    delattr(request.state, attr)

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
    cache_key = hash((_CACHE_NAMESPACE, make_hashable(config)))

    # Check cache first
    cached_dep = cast("Optional[Callable[..., list[FilterTypes]]]", dep_cache.get_dependencies(cache_key))
    if cached_dep is not None:
        return cached_dep

    dep = _create_filter_aggregate_function_fastapi(config, dep_defaults)
    dep_cache.add_dependencies(cache_key, dep)
    return dep


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
            field_names = set(search_fields.split(",")) if isinstance(search_fields, str) else set(search_fields)

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
        for field_def in _normalize_field_name_types(not_in_fields):
            # Capture field_def by value to avoid Python closure late binding gotcha
            # Without default parameter, all closures would reference the loop variable's final value
            def create_not_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType = field_def,
            ) -> Callable[..., Optional[NotInCollectionFilter[Any]]]:
                def provide_not_in_filter(  # pyright: ignore
                    values: Annotated[  # type: ignore
                        Optional[set[field_name.type_hint]],  # pyright: ignore
                        Query(
                            alias=camelize(f"{field_name.name}_not_in"),
                            description=f"Filter {field_name.name} not in values",
                        ),
                    ] = None,
                ) -> Optional[NotInCollectionFilter[field_name.type_hint]]:  # type: ignore
                    return NotInCollectionFilter(field_name=field_name.name, values=values) if values else None  # pyright: ignore

                return provide_not_in_filter  # pyright: ignore

            provider = create_not_in_filter_provider()  # pyright: ignore
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
        for field_def in _normalize_field_name_types(in_fields):
            # Capture field_def by value to avoid Python closure late binding gotcha
            # Without default parameter, all closures would reference the loop variable's final value
            def create_in_filter_provider(  # pyright: ignore
                field_name: FieldNameType = field_def,
            ) -> Callable[..., Optional[CollectionFilter[Any]]]:
                def provide_in_filter(  # pyright: ignore
                    values: Annotated[  # type: ignore
                        Optional[set[field_name.type_hint]],  # pyright: ignore
                        Query(
                            alias=camelize(f"{field_name.name}_in"),
                            description=f"Filter {field_name.name} in values",
                        ),
                    ] = None,
                ) -> Optional[CollectionFilter[field_name.type_hint]]:  # type: ignore
                    return CollectionFilter(field_name=field_name.name, values=values) if values else None  # pyright: ignore

                return provide_in_filter  # pyright: ignore

            provider = create_in_filter_provider()  # type: ignore
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

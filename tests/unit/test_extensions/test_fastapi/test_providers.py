"""Tests for the FastAPI DI module."""

import inspect
import sys
import typing
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from typing import Annotated, Any, Optional, Union, cast
from unittest.mock import MagicMock, patch
from uuid import UUID

import anyio
import pytest
from fastapi import Depends, FastAPI, Request, params
from fastapi.testclient import TestClient
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.fastapi.providers import (
    DEPENDENCY_DEFAULTS,
    ChoiceField,
    DependencyCache,
    DependencyDefaults,
    FieldNameType,
    FilterConfig,
    FilterFieldsSpec,
    FilterOperator,
    _clear_request_state,  # pyright: ignore[reportPrivateUsage]
    _create_filter_aggregate_function_fastapi,  # pyright: ignore[reportPrivateUsage]
    _is_async_service_target,  # pyright: ignore[reportPrivateUsage]
    _should_commit_for_status,  # pyright: ignore[reportPrivateUsage]
    dep_cache,  # Import the global cache instance
    provide_filters,
)
from advanced_alchemy.filters import (
    BeforeAfterFilter,
    BooleanFilter,
    ChoicesFilter,
    ComparisonFilter,
    FilterTypes,
    InCollectionFilter,
    LimitOffsetFilter,
    NotNullFilter,
    NullFilter,
    OrderByFilter,
    RelationshipFilter,
    SearchFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import ServiceGroup, SQLAlchemyAsyncRepositoryService
from advanced_alchemy.utils.dependencies import filter_cache_key, resolve_filter_aliases
from advanced_alchemy.utils.singleton import SingletonMeta

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Compatibility shim for testing string enum behavior on Python < 3.11."""


class StatusChoice(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"


class PriorityChoice(IntEnum):
    LOW = 1
    HIGH = 2


def test_dependency_cache_singleton() -> None:
    """Test that the global dep_cache instance is a singleton."""
    # Do not clear SingletonMeta._instances, so that dep_cache remains the global singleton
    new_cache = DependencyCache()
    assert new_cache is dep_cache


def test_add_get_dependencies_cache() -> None:
    """Test adding and retrieving dependencies from cache."""
    # Create a new instance to avoid test interference
    with patch.dict(SingletonMeta._instances, {}, clear=True):  # pyright: ignore[reportPrivateUsage]
        cache = DependencyCache()
        key = hash(tuple(sorted({"id_filter": True}.items())))
        deps1 = {"filters": Depends(lambda: "service")}
        cache.add_dependencies(key, deps1)  # type: ignore
        assert cache.get_dependencies(key) == deps1  # type: ignore

        # Test retrieving non-existent key
        assert cache.get_dependencies(hash("nonexistent")) is None  # type: ignore[unreachable]


def test_create_filter_dependencies_cache_hit() -> None:
    """Test create_filter_dependencies with cache hit."""
    # Setup cache with a pre-existing entry
    config = cast(FilterConfig, {"id_filter": UUID})
    mock_deps = lambda: "cached_dependency"  # type: ignore  # noqa: E731

    # Use a patch to capture the actual key
    with patch.object(dep_cache, "get_dependencies", return_value=mock_deps) as mock_get:
        with patch.object(dep_cache, "add_dependencies") as mock_add:
            with patch(
                "advanced_alchemy.extensions.fastapi.providers._create_filter_aggregate_function_fastapi"
            ) as mock_create:
                deps = provide_filters(config)

                # Verify cache was checked
                assert mock_get.call_count == 1, "Cache get_dependencies should be called exactly once"

                # Verify result is from cache
                assert deps == mock_deps  # type: ignore

                # Verify aggregate function builder was NOT called
                mock_create.assert_not_called()  # type: ignore[unreachable]

                # Verify cache wasn't updated again
                mock_add.assert_not_called()


def test_create_filter_dependencies_cache_miss() -> None:
    """Test create_filter_dependencies with cache miss."""
    config = cast(FilterConfig, {"created_at": True})
    cache_key = filter_cache_key(
        "advanced_alchemy.extensions.fastapi.providers", config, DEPENDENCY_DEFAULTS, resolve_filter_aliases(config)
    )
    mock_agg_func = lambda: [  # noqa: E731
        BeforeAfterFilter(field_name="created_at", before=None, after=None)
    ]  # Dummy aggregate function

    with patch.object(dep_cache, "get_dependencies", return_value=None) as mock_get:  # Simulate cache miss
        with patch.object(dep_cache, "add_dependencies") as mock_add:
            # Mock the builder to return our dummy aggregate function
            with patch(
                "advanced_alchemy.extensions.fastapi.providers._create_filter_aggregate_function_fastapi",
                return_value=mock_agg_func,
            ) as mock_create:
                deps = provide_filters(config)

                # Verify cache was checked
                mock_get.assert_called_once_with(cache_key)

                # Verify _create_filter_aggregate_function_fastapi was called
                mock_create.assert_called_once()

                # Verify cache was updated with the created dependencies
                # We need to compare the structure, not object identity of Depends(mock_agg_func)
                mock_add.assert_called_once()

                assert deps is mock_agg_func


# --- Aggregate Dependency Function Builder Tests --- #


def test_create_filter_aggregate_function_fastapi() -> None:
    """Test the signature and direct call of the aggregated dependency function."""

    aggregate_func = _create_filter_aggregate_function_fastapi(
        {
            "id_filter": UUID,
            "created_at": True,
            "pagination_type": "limit_offset",
            "search": "title",
            "sort_field": "id",
        },
        DEPENDENCY_DEFAULTS,
    )
    assert callable(aggregate_func)

    # Check signature has correct parameters and Depends defaults
    sig = inspect.signature(aggregate_func)
    assert DEPENDENCY_DEFAULTS.ID_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.CREATED_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.SEARCH_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.ORDER_BY_FILTER_DEPENDENCY_KEY in sig.parameters

    # Check return annotation origin type (list) and its argument (FilterTypes)
    assert sig.return_annotation == list[FilterTypes]

    for param_name, param in sig.parameters.items():
        # Check annotation (Optional[...] for filters that can return None)
        if param_name in (
            DEPENDENCY_DEFAULTS.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY,
            DEPENDENCY_DEFAULTS.ORDER_BY_FILTER_DEPENDENCY_KEY,
        ):
            # These parameters should not be Optional
            assert param.annotation is not None
            assert typing.get_origin(param.annotation) is Annotated
            inner_type = param.annotation.__args__[0]
            assert not (
                hasattr(inner_type, "__origin__")
                and inner_type.__origin__ is Union
                and type(None) in inner_type.__args__
            )
        else:
            # Other parameters should be Optional (Union[..., None])
            assert typing.get_origin(param.annotation) is Annotated
            inner_type = param.annotation.__args__[0]
            assert hasattr(inner_type, "__origin__")
            assert inner_type.__origin__ is Union
            assert type(None) in inner_type.__args__

    # Directly call the aggregate function with mock filter objects
    mock_id_filter = InCollectionFilter(field_name="id", values=["1"])
    mock_created_filter = BeforeAfterFilter(field_name="created_at", before=datetime.now(), after=None)
    mock_limit_offset = LimitOffsetFilter(limit=10, offset=0)
    mock_search_filter = SearchFilter(field_name={"title"}, value="test", ignore_case=False)
    mock_order_by = OrderByFilter(field_name="id", sort_order="asc")

    result = aggregate_func(
        id_filter=mock_id_filter,
        created_filter=mock_created_filter,
        limit_offset=mock_limit_offset,
        search_filter=mock_search_filter,
        order_by=mock_order_by,
    )

    assert isinstance(result, list)
    assert len(result) == 5
    assert mock_id_filter in result
    assert mock_created_filter in result
    assert mock_limit_offset in result
    assert mock_search_filter in result
    assert mock_order_by in result

    # Test with None values for filters that can return None
    mock_search_filter_none = SearchFilter(field_name={"title"}, value=None, ignore_case=False)  # type: ignore[arg-type]
    mock_order_by_none = OrderByFilter(field_name=None, sort_order="asc")  # type: ignore[arg-type]

    result_some_none = aggregate_func(
        id_filter=None,  # Simulate no 'ids' param provided
        created_filter=None,  # Simulate no date params provided
        limit_offset=mock_limit_offset,  # Always present
        search_filter=mock_search_filter_none,  # Aggregate func should filter this out based on value=None
        order_by=mock_order_by_none,  # Aggregate func should filter this out based on field_name=None
    )
    assert len(result_some_none) == 1  # Only LimitOffsetFilter should remain
    assert mock_limit_offset in result_some_none
    assert mock_id_filter not in result_some_none
    assert mock_created_filter not in result_some_none
    assert mock_search_filter not in result_some_none
    assert mock_order_by not in result_some_none


def test_date_filter_dependencies_have_distinct_python_parameter_names() -> None:
    """The created/updated sub-dependencies must not share `before`/`after` parameter names.

    Tools that recursively inspect a route dependency graph key on Python parameter names, so
    each provider needs distinct names even though the public query aliases
    (`createdBefore`/`createdAfter`/`updatedBefore`/`updatedAfter`) already differ.
    """
    dependency = provide_filters({"created_at": True, "updated_at": True})

    for key, expected in (
        ("created_filter", ["created_at_before", "created_at_after"]),
        ("updated_filter", ["updated_at_before", "updated_at_after"]),
    ):
        depends = next(
            metadata
            for metadata in typing.get_args(dependency.__annotations__[key])
            if isinstance(metadata, params.Depends)
        )
        assert depends.dependency is not None
        assert list(inspect.signature(depends.dependency).parameters) == expected


# --- Main create_filter_dependencies Tests --- #


def test_create_filter_dependencies_empty_config() -> None:
    """Test create_filter_dependencies with an empty config."""
    deps = provide_filters({})  # type: ignore
    assert callable(deps)


def test_create_filter_dependencies_all_filters() -> None:
    """Test create_filter_dependencies enabling all filters returns the aggregate."""

    dep_cache.dependencies.clear()
    deps = provide_filters(
        {
            "id_filter": UUID,
            "created_at": True,
            "updated_at": True,
            "pagination_type": "limit_offset",
            "search": "name, description",
            "sort_field": "created_at",
        }
    )
    assert callable(deps)

    sig = inspect.signature(deps)
    assert DEPENDENCY_DEFAULTS.ID_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.CREATED_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.UPDATED_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.SEARCH_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.ORDER_BY_FILTER_DEPENDENCY_KEY in sig.parameters


# --- Integration Test with OpenAPI Schema Check --- #


def test_create_filter_dependencies_integration_and_openapi() -> None:
    """Test integration with FastAPI using TestClient and check OpenAPI schema."""

    # Clear cache before test
    dep_cache.dependencies.clear()
    deps = provide_filters(
        {
            "id_filter": UUID,
            "pagination_type": "limit_offset",
            "search": "name",
            "sort_field": "name",  # Enables OrderByFilter
            "created_at": True,
            "boolean_fields": ["is_featured"],
            "choice_fields": [ChoiceField("status", ("active", "pending"))],
        }
    )

    app = FastAPI()

    @app.get("/items")
    async def get_items(filters: Annotated[list[FilterTypes], Depends(deps)]) -> list[str]:
        # Return simple representation for verification
        return [type(f).__name__ for f in filters]

    client = TestClient(app)

    # === Runtime Test ===
    # Restore original client.get call
    # Test case: Apply multiple filters
    response = client.get(
        "/items?ids=123e4567-e89b-12d3-a456-426614174000&ids=123e4567-e89b-12d3-a456-426614174001&currentPage=2&pageSize=5&searchString=apple&orderBy=name&sortOrder=asc&createdAfter=2023-01-01T00:00:00Z&isFeatured=true&status=active&status=pending"
    )
    assert response.status_code == 200
    data = cast(list[str], response.json())
    assert isinstance(data, list)
    # Check that all expected filter types were created and collected
    assert "InCollectionFilter" in data
    assert "LimitOffsetFilter" in data
    assert "SearchFilter" in data
    assert "OrderByFilter" in data
    assert "BeforeAfterFilter" in data
    assert "BooleanFilter" in data
    assert "ChoicesFilter" in data
    assert len(data) == 7

    # Test case: Only defaults (expect LimitOffsetFilter, OrderByFilter)
    response = client.get("/items")
    assert response.status_code == 200
    data = cast(list[str], response.json())
    assert isinstance(data, list)
    assert "LimitOffsetFilter" in data
    assert "OrderByFilter" in data
    assert "InCollectionFilter" not in data
    assert "BooleanFilter" not in data
    assert "ChoicesFilter" not in data
    assert "SearchFilter" not in data
    assert "BeforeAfterFilter" not in data
    assert len(data) == 2

    # === OpenAPI Schema Test ===
    schema = client.get("/openapi.json").json()

    # Check parameters for the /items endpoint
    path_item = schema.get("paths", {}).get("/items", {}).get("get", {})
    parameters = path_item.get("parameters", [])

    # Verify parameters from each configured filter type are present
    param_names = {p["name"] for p in parameters}

    # Expected params based on config:
    # id_filter -> ids
    # pagination -> currentPage, pageSize
    # search -> searchString, searchIgnoreCase
    # sort_field -> orderBy, sortOrder
    # created_at -> createdBefore, createdAfter
    # boolean_fields -> isFeatured
    # choice_fields -> status
    expected_params = {
        "ids",
        "currentPage",
        "pageSize",
        "searchString",
        "searchIgnoreCase",
        "orderBy",
        "sortOrder",
        "createdBefore",
        "createdAfter",
        "isFeatured",
        "status",
    }

    assert param_names == expected_params

    # Optionally, check details of a specific parameter
    ids_param = next((p for p in parameters if p["name"] == "ids"), None)
    assert ids_param is not None
    assert ids_param["in"] == "query"
    assert ids_param["required"] is False
    # Check schema structure for array type in anyOf
    assert "anyOf" in ids_param["schema"]
    array_schema = next(s for s in ids_param["schema"]["anyOf"] if s.get("type") == "array")
    assert array_schema["type"] == "array"
    assert array_schema["items"]["type"] == "string"

    page_size_param = next((p for p in parameters if p["name"] == "pageSize"), None)
    assert page_size_param is not None
    assert page_size_param["in"] == "query"
    assert page_size_param["required"] is False
    assert page_size_param["schema"]["type"] == "integer"
    assert page_size_param["schema"]["default"] == 20  # Default from DependencyDefaults

    is_featured_param = next((p for p in parameters if p["name"] == "isFeatured"), None)
    assert is_featured_param is not None
    assert is_featured_param["in"] == "query"
    assert is_featured_param["required"] is False
    assert any(
        schema.get("type") == "boolean"
        for schema in is_featured_param["schema"].get("anyOf", [is_featured_param["schema"]])
    )

    status_param = next((p for p in parameters if p["name"] == "status"), None)
    assert status_param is not None
    assert status_param["in"] == "query"
    assert status_param["required"] is False
    status_array_schema = next(
        schema
        for schema in status_param["schema"].get("anyOf", [status_param["schema"]])
        if schema.get("type") == "array"
    )
    assert status_array_schema["items"]["type"] == "string"
    assert status_array_schema["items"]["enum"] == ["active", "pending"]


def test_choice_filter_openapi_schema_supports_explicit_and_enum_choices() -> None:
    """Test choice filters expose explicit, StrEnum, and IntEnum values in OpenAPI."""
    deps = provide_filters(
        {
            "choice_fields": [
                ("visibility", ("public", "private")),
                ("status", StatusChoice),
                ("priority", PriorityChoice),
            ],
        }
    )

    app = FastAPI()

    @app.get("/items")
    async def get_items(filters: Annotated[list[FilterTypes], Depends(deps)]) -> list[str]:
        return [type(f).__name__ for f in filters]

    client = TestClient(app)

    response = client.get("/items?visibility=public&status=active&priority=1")
    assert response.status_code == 200
    assert response.json() == ["ChoicesFilter", "ChoicesFilter", "ChoicesFilter"]

    schema = client.get("/openapi.json").json()
    parameters = schema["paths"]["/items"]["get"]["parameters"]
    param_schemas = {parameter["name"]: parameter["schema"] for parameter in parameters}
    components = schema["components"]["schemas"]

    visibility_items = next(schema for schema in param_schemas["visibility"]["anyOf"] if schema.get("type") == "array")[
        "items"
    ]
    assert visibility_items == {"enum": ["public", "private"], "type": "string"}

    status_items = next(schema for schema in param_schemas["status"]["anyOf"] if schema.get("type") == "array")["items"]
    assert status_items == {"$ref": "#/components/schemas/StatusChoice"}
    assert components["StatusChoice"]["enum"] == ["active", "pending"]
    assert components["StatusChoice"]["type"] == "string"

    priority_items = next(schema for schema in param_schemas["priority"]["anyOf"] if schema.get("type") == "array")[
        "items"
    ]
    assert priority_items == {"$ref": "#/components/schemas/PriorityChoice"}
    assert components["PriorityChoice"]["enum"] == [1, 2]
    assert components["PriorityChoice"]["type"] == "integer"


# Custom Defaults Test (remains largely the same logic)
def test_custom_dependency_defaults_fastapi() -> None:
    """Test using custom dependency defaults with FastAPI provider."""

    class CustomDefaults(DependencyDefaults):
        LIMIT_OFFSET_FILTER_DEPENDENCY_KEY = "paging"
        ORDER_BY_FILTER_DEPENDENCY_KEY = "ordering"
        DEFAULT_PAGINATION_SIZE = 5

    custom_defaults = CustomDefaults()
    config = cast(
        FilterConfig,
        {
            "id_filter": UUID,
            "pagination_type": "limit_offset",
            "sort_field": "name",  # uses custom ORDER_BY_DEPENDENCY_KEY
        },
    )

    # Clear cache before test
    dep_cache.dependencies.clear()
    deps = provide_filters(config, dep_defaults=custom_defaults)

    sig = inspect.signature(deps)
    assert "id_filter" in sig.parameters  # Uses standard key if not overridden
    assert "paging" in sig.parameters  # Custom key used for limit/offset param name
    assert "ordering" in sig.parameters  # Custom key used for order by param name

    # Test integration and OpenAPI with custom defaults
    app = FastAPI()

    @app.get("/custom")
    async def get_custom(filters: Annotated[list[FilterTypes], Depends(deps)] = []) -> list[str]:
        return [type(f).__name__ for f in filters]

    client = TestClient(app)

    # Restore original client.get call
    response = client.get(
        "/custom?ids=123e4567-e89b-12d3-a456-426614174000&currentPage=3&orderBy=id"
    )  # pageSize defaults to 5 (CustomDefaults)

    assert response.status_code == 200
    data = cast(list[str], response.json())
    assert isinstance(data, list)
    assert "InCollectionFilter" in data
    assert "LimitOffsetFilter" in data
    assert "OrderByFilter" in data
    assert len(data) == 3

    # Check OpenAPI uses custom default page size
    schema = client.get("/openapi.json").json()
    custom_path_item = schema.get("paths", {}).get("/custom", {}).get("get", {})
    custom_parameters = custom_path_item.get("parameters", [])

    custom_page_size_param = next((p for p in custom_parameters if p["name"] == "pageSize"), None)
    assert custom_page_size_param is not None
    assert custom_page_size_param["schema"]["default"] == 5  # Custom default


def test_openapi_schema_comprehensive() -> None:
    """Test comprehensive filter generation with all filter types."""
    # Create a filter configuration with all supported filter types
    deps = provide_filters(
        {
            "id_filter": UUID,
            "created_at": True,
            "updated_at": True,
            "pagination_type": "limit_offset",
            "search": "name,description,email",  # Multiple search fields
            "sort_field": {"name", "created_at", "email"},  # Multiple sort fields (using set)
            "not_in_fields": {FieldNameType("status", str), FieldNameType("category", str)},  # Not-in fields
            "in_fields": {FieldNameType("tag", str), FieldNameType("author_id", str)},  # In fields
            "boolean_fields": ["is_featured"],
            "choice_fields": [FieldNameType("state", str)],
        }
    )

    # Check the signature of the generated function to ensure it has all required parameters
    sig = inspect.signature(deps)
    param_names = set(sig.parameters.keys())
    expected_param_names = {
        "id_filter",
        "created_filter",
        "updated_filter",
        "limit_offset_filter",
        "search_filter",
        "order_by_filter",
        "status_not_in_filter",
        "category_not_in_filter",
        "tag_in_filter",
        "author_id_in_filter",
        "is_featured_boolean_filter",
        "state_choices_filter",
    }
    assert param_names == expected_param_names

    # Test that function parameters have the correct types and defaults
    for name, param in sig.parameters.items():
        # Check types for known parameters
        if name == "id_filter":
            assert "UUID" in str(param.annotation), f"id_filter should have UUID type, got {param.annotation}"
        elif name in ("created_filter", "updated_filter"):
            assert "BeforeAfterFilter" in str(param.annotation), (
                f"{name} should have BeforeAfterFilter type, got {param.annotation}"
            )
        elif name == "limit_offset":
            assert "LimitOffsetFilter" in str(param.annotation), (
                f"limit_offset should have LimitOffsetFilter type, got {param.annotation}"
            )
        elif name == "search_filter":
            assert "SearchFilter" in str(param.annotation), (
                f"search_filter should have SearchFilter type, got {param.annotation}"
            )
        elif name == "order_by":
            assert "OrderByFilter" in str(param.annotation), (
                f"order_by should have OrderByFilter type, got {param.annotation}"
            )
        elif "not_in" in name:
            assert "NotInCollectionFilter" in str(param.annotation), (
                f"{name} should have NotInCollectionFilter type, got {param.annotation}"
            )
        elif "boolean_filter" in name:
            assert "BooleanFilter" in str(param.annotation), (
                f"{name} should have BooleanFilter type, got {param.annotation}"
            )
        elif "choices_filter" in name:
            assert "ChoicesFilter" in str(param.annotation), (
                f"{name} should have ChoicesFilter type, got {param.annotation}"
            )
        elif "in_filter" in name:
            assert "InCollectionFilter" in str(param.annotation), (
                f"{name} should have InCollectionFilter type, got {param.annotation}"
            )

    # Check that the return annotation is list[FilterTypes]
    assert deps.__annotations__["return"] == list[FilterTypes]

    # Test direct call with filter values
    mock_id_filter = InCollectionFilter(field_name="id", values=["123e4567-e89b-12d3-a456-426614174000"])
    mock_created_filter = BeforeAfterFilter(field_name="created_at", before=datetime.now(), after=None)
    mock_limit_offset = LimitOffsetFilter(limit=10, offset=0)
    mock_search_filter = SearchFilter(field_name={"name"}, value="test", ignore_case=False)
    mock_order_by = OrderByFilter(field_name="name", sort_order="asc")
    mock_boolean_filter = BooleanFilter(field_name="is_featured", value=True)
    mock_choices_filter = ChoicesFilter(field_name="state", values=["active"])

    result = deps(
        id_filter=mock_id_filter,
        created_filter=mock_created_filter,
        updated_filter=None,
        limit_offset=mock_limit_offset,
        search_filter=mock_search_filter,
        order_by=mock_order_by,
        status_not_in_filter=None,
        category_not_in_filter=None,
        tag_in_filter=None,
        author_id_in_filter=None,
        is_featured_boolean_filter=mock_boolean_filter,
        state_choices_filter=mock_choices_filter,
    )

    # Verify that the results contain the expected filter objects
    assert isinstance(result, list)
    assert len(result) == 7
    assert mock_id_filter in result
    assert mock_created_filter in result
    assert mock_limit_offset in result
    assert mock_search_filter in result
    assert mock_order_by in result
    assert mock_boolean_filter in result
    assert mock_choices_filter in result


def test_provide_filters_normalizes_list_field_config() -> None:
    """Test list-based shared FilterConfig values are normalized for FastAPI."""
    deps = provide_filters(
        {
            "search": ["name", "email"],
            "not_in_fields": ["status", FieldNameType("category", str)],
            "in_fields": ["tag"],
            "boolean_fields": ["is_active"],
            "choice_fields": ["state"],
        }
    )

    sig = inspect.signature(deps)
    assert set(sig.parameters) == {
        "search_filter",
        "status_not_in_filter",
        "category_not_in_filter",
        "tag_in_filter",
        "is_active_boolean_filter",
        "state_choices_filter",
    }


def test_provide_filters_uses_scalar_default_from_list_sort_field() -> None:
    """Test list-based sort fields produce a scalar default order field."""
    deps = provide_filters({"sort_field": ["name", "id"]})

    app = FastAPI()

    @app.get("/items")
    async def get_items(filters: Annotated[list[FilterTypes], Depends(deps)]) -> list[dict[str, str]]:
        return [
            {"field_name": cast(str, filter_.field_name), "sort_order": filter_.sort_order}
            for filter_ in filters
            if isinstance(filter_, OrderByFilter)
        ]

    client = TestClient(app)
    response = client.get("/items")
    overridden_response = client.get("/items?orderBy=id&sortOrder=asc")

    assert response.status_code == 200
    assert response.json() == [{"field_name": "name", "sort_order": "desc"}]
    assert overridden_response.status_code == 200
    assert overridden_response.json() == [{"field_name": "id", "sort_order": "asc"}]


def test_provide_filters_applies_configured_nulls_placement() -> None:
    """The `sort_nulls` config key pins NULL placement on every generated OrderByFilter."""
    deps = provide_filters({"sort_field": "name", "sort_nulls": "first"})

    app = FastAPI()

    @app.get("/items")
    async def get_items(filters: Annotated[list[FilterTypes], Depends(deps)]) -> list[Optional[str]]:
        return [filter_.nulls for filter_ in filters if isinstance(filter_, OrderByFilter)]

    client = TestClient(app)

    assert client.get("/items").json() == ["first"]
    assert client.get("/items?orderBy=id&sortOrder=asc").json() == ["first"]


def test_provide_filters_applies_configured_wildcard_escaping() -> None:
    """The `search_escape_wildcards` config key makes every generated SearchFilter match literally."""
    deps = provide_filters({"search": "name", "search_escape_wildcards": True})

    app = FastAPI()

    @app.get("/items")
    async def get_items(filters: Annotated[list[FilterTypes], Depends(deps)]) -> list[bool]:
        return [filter_.escape_wildcards for filter_ in filters if isinstance(filter_, SearchFilter)]

    client = TestClient(app)

    assert client.get("/items?searchString=50%25").json() == [True]


def test_openapi_schema_edge_cases() -> None:
    """Test OpenAPI schema generation for edge cases and special configurations."""
    # Test with minimal configuration

    app = FastAPI()

    @app.get("/minimal")
    async def get_minimal(
        filters: Annotated[list[FilterTypes], Depends(provide_filters({"pagination_type": "limit_offset"}))],
    ) -> list[str]:
        return [type(f).__name__ for f in filters]

    # Test with all optional filters disabled
    @app.get("/no-optionals")
    async def get_no_optionals(
        filters: Annotated[
            list[FilterTypes],
            Depends(
                provide_filters(
                    {
                        "pagination_type": "limit_offset",
                        "sort_field": "id",
                    },
                ),
            ),
        ],
    ) -> list[str]:
        return [type(f).__name__ for f in filters]

    # Test with custom validation
    @app.get("/custom-validation")
    async def get_custom_validation(
        filters: Annotated[
            list[FilterTypes],
            Depends(
                provide_filters(
                    {
                        "id_filter": UUID,
                        "pagination_type": "limit_offset",
                        "sort_field": "id",
                        "search": "email",
                        "created_at": True,
                    },
                )
            ),
        ],
    ) -> list[str]:
        return [type(f).__name__ for f in filters]

    client = TestClient(app)

    # Test minimal schema
    schema = client.get("/openapi.json").json()
    minimal_path_item = schema.get("paths", {}).get("/minimal", {}).get("get", {})
    minimal_parameters = minimal_path_item.get("parameters", [])
    assert len(minimal_parameters) == 2  # Only pagination params
    assert {p["name"] for p in minimal_parameters} == {"currentPage", "pageSize"}

    # Test no optionals schema
    no_optionals_path_item = schema.get("paths", {}).get("/no-optionals", {}).get("get", {})
    no_optionals_parameters = no_optionals_path_item.get("parameters", [])
    assert len(no_optionals_parameters) == 4  # Pagination + sort params
    assert {p["name"] for p in no_optionals_parameters} >= {"currentPage", "pageSize", "orderBy", "sortOrder"}

    # Test custom validation schema
    custom_validation_path_item = schema.get("paths", {}).get("/custom-validation", {}).get("get", {})
    custom_validation_parameters = custom_validation_path_item.get("parameters", [])
    assert len(custom_validation_parameters) == 9  # All configured params
    assert {p["name"] for p in custom_validation_parameters} >= {
        "ids",
        "currentPage",
        "pageSize",
        "orderBy",
        "sortOrder",
        "searchString",
        "searchIgnoreCase",
        "createdBefore",
        "createdAfter",
    }

    # Test runtime behavior for minimal config
    response = client.get("/minimal")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1  # type: ignore[arg-type]
    assert "LimitOffsetFilter" in data

    # Test runtime behavior for no optionals
    response = client.get("/no-optionals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2  # type: ignore[arg-type]
    assert "LimitOffsetFilter" in data
    assert "OrderByFilter" in data

    # Test runtime behavior for custom validation
    response = client.get(
        "/custom-validation?ids=123e4567-e89b-12d3-a456-426614174000&currentPage=2&pageSize=5&orderBy=id&searchString=test&createdAfter=2023-01-01T00:00:00Z"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5  # type: ignore[arg-type]
    assert "InCollectionFilter" in data
    assert "LimitOffsetFilter" in data
    assert "OrderByFilter" in data
    assert "SearchFilter" in data
    assert "BeforeAfterFilter" in data


class SimpleDishkaTable(UUIDBase):
    name: Mapped[str] = mapped_column(String(length=50), index=True)


class SimpleDishkaService(SQLAlchemyAsyncRepositoryService[SimpleDishkaTable]):
    class Repo(SQLAlchemyAsyncRepository[SimpleDishkaTable]):
        model_type = SimpleDishkaTable

    repository_type = Repo


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Dishka integration requires Python 3.10+")
async def test_provide_filters_with_dishka_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test provide_filters integration with FastAPI and Dishka."""
    from dishka import (  # type: ignore # pyright: ignore
        Provider,  # type: ignore
        Scope,  # type: ignore
        make_async_container,  # type: ignore
        provide,  # type: ignore
    )
    from dishka.integrations.fastapi import (  # type: ignore # pyright: ignore
        FastapiProvider,  # type: ignore
        FromDishka,  # type: ignore
        inject,  # type: ignore
        setup_dishka,  # type: ignore
    )

    # Clear cache before test
    dep_cache.dependencies.clear()
    sqlalchemy_config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")

    class SimpleDishkaProvider(Provider):  # type: ignore
        @provide(scope=Scope.REQUEST)  # type: ignore
        async def provide_session(self, request: Request) -> AsyncGenerator[AsyncSession, None]:
            async with sqlalchemy_config.get_session() as session:
                yield session

        @provide(scope=Scope.REQUEST)  # type: ignore
        async def provide_simple_dishka_service(self, db_session: FromDishka[AsyncSession]) -> SimpleDishkaService:  # type: ignore
            return SimpleDishkaService(session=db_session)  # type: ignore

    filter_deps = provide_filters(
        {
            "id_filter": UUID,
            "pagination_type": "limit_offset",
            "search": "name",
            "created_at": True,
        }
    )

    app = FastAPI()
    container = make_async_container(SimpleDishkaProvider(), FastapiProvider())  # type: ignore
    setup_dishka(container=container, app=app)

    @app.get("/diska-items")
    @inject  # pyright: ignore
    async def get_diska_items(
        filters: Annotated[list[FilterTypes], Depends(filter_deps)],
        simple_model_service: FromDishka[SimpleDishkaService],  # type: ignore
    ) -> dict[str, typing.Any]:
        # Return filter types and dummy service value for verification
        return {
            "filters": [type(f).__name__ for f in filters],
            "simple_model_table_name": simple_model_service.model_type.__tablename__,
        }

    client = TestClient(app)

    # Test case: Apply multiple filters
    response = client.get(
        "/diska-items?ids=123e4567-e89b-12d3-a456-426614174000&currentPage=1&pageSize=10&searchString=test&createdAfter=2023-01-01T00:00:00Z"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["simple_model_table_name"] == "simple_dishka_table"
    filter_types = data.get("filters", [])  # type: ignore
    assert isinstance(filter_types, list)
    assert "InCollectionFilter" in filter_types
    assert "LimitOffsetFilter" in filter_types
    assert "SearchFilter" in filter_types
    assert "BeforeAfterFilter" in filter_types
    # OrderByFilter is not explicitly configured but might have defaults, let's check if it's NOT there unless configured
    assert "OrderByFilter" not in filter_types  # OrderByFilter was not configured in this specific provide_filters call
    assert len(filter_types) == 4  # type: ignore

    # Test case: Only defaults (expect LimitOffsetFilter)
    response = client.get("/diska-items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["simple_model_table_name"] == "simple_dishka_table"
    filter_types = data.get("filters", [])  # type: ignore
    assert isinstance(filter_types, list)
    assert "LimitOffsetFilter" in filter_types  # Default pagination
    assert "InCollectionFilter" not in filter_types
    assert "SearchFilter" not in filter_types
    assert "BeforeAfterFilter" not in filter_types
    assert "OrderByFilter" not in filter_types
    assert len(filter_types) == 1  # type: ignore

    await container.close()


CONFIG: dict[str, Any] = {
    "pagination_type": "limit_offset",
    "search": "name",
    "sort_field": "created_at",
    "created_at": True,
    "boolean_fields": ["is_active"],
    "in_fields": ["status"],
}


def _parameter_names(config: dict[str, Any]) -> list[str]:
    app = FastAPI()
    dependency = provide_filters(cast(FilterConfig, config))

    @app.get("/things")
    async def list_things(filters: Annotated[list[Any], Depends(dependency)]) -> list[Any]:
        return filters

    return [parameter["name"] for parameter in app.openapi()["paths"]["/things"]["get"]["parameters"]]


def test_default_names_are_unchanged() -> None:
    """The default generator is `camelize`, which reproduces the previously hardcoded names."""
    assert _parameter_names(dict(CONFIG)) == [
        "createdBefore",
        "createdAfter",
        "currentPage",
        "pageSize",
        "searchString",
        "searchIgnoreCase",
        "orderBy",
        "sortOrder",
        "statusIn",
        "isActive",
    ]


def test_alias_generator_renames_every_parameter() -> None:
    """Including the per-field filters, which were camelized from the model's own field names."""
    assert _parameter_names({**CONFIG, "alias_generator": lambda name: name}) == [
        "created_before",
        "created_after",
        "current_page",
        "page_size",
        "search_string",
        "search_ignore_case",
        "order_by",
        "sort_order",
        "status_in",
        "is_active",
    ]


def test_distinct_generators_get_distinct_dependencies() -> None:
    """Two generators must not collide in the dependency cache.

    A function hashes by identity, and CPython reuses the address of a collected object — so a key
    that does not keep the generator alive can hand the second config the first one's providers.
    """
    snake = _parameter_names({**CONFIG, "alias_generator": lambda name: name})
    upper = _parameter_names({**CONFIG, "alias_generator": lambda name: name.upper()})

    assert snake[0] == "created_before"
    assert upper[0] == "CREATED_BEFORE"
    assert _parameter_names(dict(CONFIG))[0] == "createdBefore", "the default config must be unaffected"


def test_a_generator_that_collides_is_rejected() -> None:
    """Sharing a query parameter is silent and destructive, so it has to fail at build time.

    FastAPI binds the one value to both parameters, so a `created_before`/`created_after` pair
    collapsed onto a single name asks for `< x AND > x` and quietly matches nothing.
    """
    with pytest.raises(ImproperConfigurationError, match="duplicate query parameter 'created'"):
        _parameter_names({"created_at": True, "alias_generator": lambda name: name.split("_")[0]})


def test_default_alias_collisions_preserve_existing_configuration() -> None:
    assert _parameter_names({"boolean_fields": ["status_in"], "in_fields": ["status"]}) == ["statusIn"]


@pytest.mark.parametrize("field", ["created", "updated"])
@pytest.mark.parametrize("bound", ["before", "after"])
def test_custom_date_alias_validation_location(field: str, bound: str) -> None:
    app = FastAPI()
    dependency = provide_filters(cast(FilterConfig, {f"{field}_at": True, "alias_generator": str.upper}))

    @app.get("/things")
    async def list_things(filters: Annotated[list[Any], Depends(dependency)]) -> list[Any]:
        return filters

    alias = f"{field}_{bound}".upper()
    with TestClient(app) as client:
        response = client.get("/things", params={alias: "invalid"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", alias]


def test_unhashable_falsy_generators_keep_distinct_cached_aliases() -> None:
    @dataclass
    class Generator:
        prefix: str

        def __bool__(self) -> bool:
            return False

        def __str__(self) -> str:
            return "same"

        def __call__(self, name: str) -> str:
            return self.prefix + name

    first = Generator("first_")
    second = Generator("second_")
    assert _parameter_names({"pagination_type": "limit_offset", "alias_generator": first}) == [
        "first_current_page",
        "first_page_size",
    ]
    assert _parameter_names({"pagination_type": "limit_offset", "alias_generator": second}) == [
        "second_current_page",
        "second_page_size",
    ]
    config: FilterConfig = {"pagination_type": "limit_offset", "alias_generator": first}
    assert provide_filters(config) is provide_filters(config.copy())


def _query_parameter_names(app: FastAPI, path: str) -> list[str]:
    return [parameter["name"] for parameter in app.openapi()["paths"][path]["get"].get("parameters", [])]


def test_two_configs_do_not_share_one_signature() -> None:
    """Building a second dependency must not rewrite the first one's parameters.

    The aggregate function used to be a single module-level object whose `__signature__` was
    reassigned per config, so the last config built won and every earlier router silently served
    the wrong query parameters.
    """
    app = FastAPI()
    authors = provide_filters({"search": "name"})
    books = provide_filters({"created_at": True})

    @app.get("/authors")
    async def list_authors(filters: Annotated[list[Any], Depends(authors)]) -> list[Any]:
        return filters

    @app.get("/books")
    async def list_books(filters: Annotated[list[Any], Depends(books)]) -> list[Any]:
        return filters

    with TestClient(app) as client:
        response = client.get("/authors", params={"searchString": "needle"})
        assert response.status_code == 200
        assert response.json()[0]["value"] == "needle"
        response = client.get("/books", params={"createdAfter": "2025-01-01T00:00:00Z"})
        assert response.status_code == 200
        assert response.json()[0]["field_name"] == "created_at"
        assert response.json()[0]["after"].startswith("2025-01-01")

    assert authors is not books
    assert _query_parameter_names(app, "/authors") == ["searchString", "searchIgnoreCase"]
    assert _query_parameter_names(app, "/books") == ["createdBefore", "createdAfter"]


def _cached_config() -> FilterConfig:
    """A fresh, equal config each call, so the cache is exercised by value rather than by identity."""
    return {"search": "name", "pagination_type": "limit_offset"}


def test_the_same_config_is_still_cached() -> None:
    """The per-config cache is what keeps repeated identical configs cheap; it should still hit."""
    assert provide_filters(_cached_config()) is provide_filters(_cached_config())


class _BigPages(DependencyDefaults):
    DEFAULT_PAGINATION_SIZE = 100


def _page_size(dependency: Any, path: str) -> Any:
    app = FastAPI()

    @app.get(path)
    async def endpoint(filters: Annotated[list[Any], Depends(dependency)]) -> list[Any]:
        return filters

    with TestClient(app) as client:
        response = client.get(path, params={"currentPage": 2})
        assert response.status_code == 200
        result = response.json()[0]
        assert result["offset"] == result["limit"]

    parameters = app.openapi()["paths"][path]["get"]["parameters"]
    page_size = next(p["schema"]["default"] for p in parameters if p["name"] == "pageSize")
    assert result["limit"] == page_size
    return page_size


def test_one_config_with_two_dependency_defaults_does_not_share_a_dependency() -> None:
    """`dep_defaults` shapes the signature too, so it has to take part in the cache key.

    Keyed on the config alone, whichever defaults were built first won for the whole process, and
    the other caller silently served a page size it never asked for.
    """
    config: FilterConfig = {"pagination_type": "limit_offset"}

    default = provide_filters(config.copy())
    big = provide_filters(config.copy(), _BigPages())

    assert default is not big
    assert _page_size(default, "/default") == DEPENDENCY_DEFAULTS.DEFAULT_PAGINATION_SIZE
    assert _page_size(big, "/big") == _BigPages.DEFAULT_PAGINATION_SIZE


def test_equal_dependency_defaults_still_share_a_dependency() -> None:
    """Keying on the values rather than the instance is what keeps the cache useful here."""
    assert provide_filters(_cached_config(), DependencyDefaults()) is provide_filters(
        _cached_config(), DependencyDefaults()
    )


class _FastAPIPlainHelper:
    """Plain helper service whose async mode cannot be inferred without an extension config."""

    def __init__(self, session: Any) -> None:
        self.session = session


class _FastAPIUndeterminedGroup(ServiceGroup):
    """ServiceGroup composed strictly of plain helpers with undetermined execution mode."""

    helper: _FastAPIPlainHelper


@pytest.mark.parametrize(
    ("status_code", "commit_mode", "expected"),
    [
        (200, "manual", False),
        (200, "autocommit", True),
        (404, "autocommit", False),
        (307, "autocommit_include_redirect", True),
        (400, "autocommit_include_redirect", False),
        (200, "unknown", False),
    ],
)
def test_should_commit_for_status_modes(status_code: int, commit_mode: str, expected: bool) -> None:
    """Verify FastAPI auto-commit status code policy across all commit modes."""
    assert _should_commit_for_status(status_code, commit_mode) is expected


def test_clear_request_state_removes_present_key_safely() -> None:
    """Clear stored session state attributes whether present or already absent."""
    request = Request({"type": "http", "headers": []})
    request.state.db_session = "sentinel"
    _clear_request_state(request, "db_session")
    assert not hasattr(request.state, "db_session")
    _clear_request_state(request, "db_session")


def test_is_async_service_target_uses_extension_for_undetermined_group() -> None:
    """Inspect extension session provider when a ServiceGroup declares no SQLAlchemy services."""
    async_ext = AdvancedAlchemy(SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"), app=FastAPI())
    sync_ext = AdvancedAlchemy(SQLAlchemySyncConfig(connection_string="sqlite:///:memory:"), app=FastAPI())

    assert _is_async_service_target(_FastAPIUndeterminedGroup, async_ext, None) is True
    assert _is_async_service_target(_FastAPIUndeterminedGroup, sync_ext, None) is False

    async def _async_session_gen() -> AsyncGenerator[Any, None]:
        yield None

    custom_ext = MagicMock()
    custom_ext.get_config.return_value = object()
    custom_ext.provide_session.return_value = _async_session_gen
    assert _is_async_service_target(_FastAPIUndeterminedGroup, custom_ext, None) is True


def test_fastapi_aggregate_filter_flattens_list_values() -> None:
    """Extend aggregated filter output when a sub-dependency returns a list of filters."""
    agg = _create_filter_aggregate_function_fastapi({"id_filter": int})
    first = InCollectionFilter(field_name="id", values=[1])
    second = InCollectionFilter(field_name="id", values=[2])
    result = agg(id_filter=cast("Any", [first, second]))
    assert result == [first, second]


class _FastAPIGridBase(DeclarativeBase):
    """Isolated declarative base for FastAPI data-grid tests."""


class _FastAPIGridAuthor(_FastAPIGridBase):
    """Author model for FastAPI data-grid tests."""

    __tablename__ = "fastapi_grid_author"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    mentor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fastapi_grid_author.id"), nullable=True)
    mentor: Mapped[Optional["_FastAPIGridAuthor"]] = relationship(remote_side=[id])
    articles: Mapped[list["_FastAPIGridArticle"]] = relationship(back_populates="author")


class _FastAPIGridArticle(_FastAPIGridBase):
    """Article model for FastAPI data-grid tests."""

    __tablename__ = "fastapi_grid_article"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150))
    rel_author: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    views: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    published_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("fastapi_grid_author.id"))
    author: Mapped[_FastAPIGridAuthor] = relationship(back_populates="articles")
    author_mentor: Mapped[_FastAPIGridAuthor] = relationship(viewonly=True, foreign_keys=[author_id])


class _FastAPIGridArticleRepo(SQLAlchemyAsyncRepository[_FastAPIGridArticle]):
    model_type = _FastAPIGridArticle


class _FastAPIGridArticleService(SQLAlchemyAsyncRepositoryService[_FastAPIGridArticle, _FastAPIGridArticleRepo]):
    repository_type = _FastAPIGridArticleRepo


def _serialize_fastapi_grid_filters(filters: Sequence[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in filters:
        if isinstance(item, RelationshipFilter):
            serialized.append(
                {
                    "type": "RelationshipFilter",
                    "relationship": item.relationship,
                    "filters": _serialize_fastapi_grid_filters(item.filters),
                }
            )
        elif isinstance(item, ComparisonFilter):
            serialized.append(
                {
                    "type": "ComparisonFilter",
                    "field_name": item.field_name,
                    "operator": item.operator,
                    "value": item.value,
                }
            )
        elif isinstance(item, SearchFilter):
            serialized.append(
                {
                    "type": "SearchFilter",
                    "field_name": item.field_name,
                    "value": item.value,
                    "ignore_case": item.ignore_case,
                }
            )
        elif isinstance(item, InCollectionFilter):
            serialized.append(
                {
                    "type": "InCollectionFilter",
                    "field_name": item.field_name,
                    "values": list(item.values or ()),
                }
            )
        elif isinstance(item, OrderByFilter):
            serialized.append(
                {
                    "type": "OrderByFilter",
                    "field_name": item.field_name,
                    "sort_order": item.sort_order,
                }
            )
        elif isinstance(item, LimitOffsetFilter):
            serialized.append({"type": "LimitOffsetFilter", "limit": item.limit, "offset": item.offset})
        elif isinstance(item, (NullFilter, NotNullFilter)):
            serialized.append({"type": type(item).__name__, "field_name": item.field_name})
    return serialized


@pytest.mark.parametrize(
    ("field_spec", "parameters", "expected"),
    [
        (
            {"rel_author": {"eq"}, "author.name": {"eq"}},
            {"relAuthorEq": "editor", "authorNameEq": "Ada"},
            [
                {"type": "ComparisonFilter", "field_name": "rel_author", "operator": "eq", "value": "editor"},
                {
                    "type": "RelationshipFilter",
                    "relationship": "author",
                    "filters": [{"type": "ComparisonFilter", "field_name": "name", "operator": "eq", "value": "Ada"}],
                },
            ],
        ),
        (
            {"author_mentor.name": {"eq"}, "author.mentor.id": {"eq"}},
            {"authorMentorNameEq": "Ada", "authorMentorIdEq": "7"},
            [
                {
                    "type": "RelationshipFilter",
                    "relationship": "author_mentor",
                    "filters": [{"type": "ComparisonFilter", "field_name": "name", "operator": "eq", "value": "Ada"}],
                },
                {
                    "type": "RelationshipFilter",
                    "relationship": ["author", "mentor"],
                    "filters": [{"type": "ComparisonFilter", "field_name": "id", "operator": "eq", "value": 7}],
                },
            ],
        ),
    ],
)
def test_fastapi_field_filter_group_names_do_not_collide(
    field_spec: FilterFieldsSpec, parameters: dict[str, str], expected: list[dict[str, Any]]
) -> None:
    """Direct columns and distinct relationship paths retain their public parameters."""
    config: FilterConfig = {"filter_fields": field_spec}
    filter_dep = provide_filters(config, model=_FastAPIGridArticle)
    app = FastAPI()

    @app.get("/articles")
    def list_articles(filters: Annotated[list[FilterTypes], Depends(filter_dep)]) -> list[dict[str, Any]]:
        return _serialize_fastapi_grid_filters(filters)

    with TestClient(app) as client:
        response = client.get("/articles", params=parameters)
        assert response.status_code == 200, response.text
        assert response.json() == expected


def test_fastapi_field_filter_fields_and_sort_fields_openapi_and_parsing() -> None:
    """Verify grouped relationship filters, repeatable orderBy, 422 validation, and OpenAPI schema."""
    ops: set[FilterOperator] = {"contains", "eq"}
    field_spec: FilterFieldsSpec = {
        "title": ops,
        "views": {"ge", "le"},
        "status": {"in"},
        "published_at": {"is_null"},
        "author.name": ops,
    }
    config: FilterConfig = {
        "filter_fields": field_spec,
        "sort_fields": ["title", "views", "author.name"],
        "pagination_type": "limit_offset",
        "pagination_size": 10,
    }
    filter_dep = provide_filters(config, model=_FastAPIGridArticle)

    app = FastAPI()

    @app.get("/articles")
    def list_articles(filters: Annotated[list[FilterTypes], Depends(filter_dep)]) -> list[dict[str, Any]]:
        return _serialize_fastapi_grid_filters(filters)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        param_map = {p["name"]: p for p in schema["paths"]["/articles"]["get"]["parameters"]}
        assert {
            "titleContains",
            "titleEq",
            "viewsGe",
            "viewsLe",
            "statusIn",
            "publishedAtIsNull",
            "authorNameContains",
            "authorNameEq",
            "orderBy",
        }.issubset(param_map.keys())
        assert param_map["orderBy"]["schema"]["anyOf"][0]["type"] == "array"

        ok = client.get(
            "/articles",
            params=[
                ("titleContains", "sql"),
                ("viewsGe", "100"),
                ("viewsLe", "500"),
                ("statusIn", "draft"),
                ("authorNameContains", "cody"),
                ("authorNameEq", "Cody"),
                ("publishedAtIsNull", "true"),
                ("orderBy", "-views"),
                ("orderBy", "author.name"),
                ("currentPage", "2"),
                ("pageSize", "25"),
            ],
        )
        assert ok.status_code == 200, ok.text
        parsed = ok.json()
        assert {"type": "SearchFilter", "field_name": "title", "value": "sql", "ignore_case": True} in parsed
        assert {"type": "ComparisonFilter", "field_name": "views", "operator": "ge", "value": 100} in parsed
        assert {"type": "ComparisonFilter", "field_name": "views", "operator": "le", "value": 500} in parsed
        assert {"type": "InCollectionFilter", "field_name": "status", "values": ["draft"]} in parsed
        assert {"type": "NullFilter", "field_name": "published_at"} in parsed
        assert {"type": "LimitOffsetFilter", "limit": 25, "offset": 25} in parsed
        rel_filters = [item for item in parsed if item["type"] == "RelationshipFilter"]
        assert len(rel_filters) == 1
        assert rel_filters[0]["relationship"] == "author"
        assert rel_filters[0]["filters"] == [
            {"type": "ComparisonFilter", "field_name": "name", "operator": "eq", "value": "Cody"},
            {"type": "SearchFilter", "field_name": "name", "value": "cody", "ignore_case": True},
        ]
        order_filters = [item for item in parsed if item["type"] == "OrderByFilter"]
        assert order_filters == [
            {"type": "OrderByFilter", "field_name": "views", "sort_order": "desc"},
            {"type": "OrderByFilter", "field_name": "author.name", "sort_order": "asc"},
        ]

        invalid_sort = client.get("/articles", params=[("orderBy", "-secret")])
        assert invalid_sort.status_code == 422


def test_fastapi_grid_snake_case_and_e2e_async_sqlite_prototype() -> None:
    """Exercise FastAPI grid filtering + relationship OrderByFilter + pagination against async SQLite."""
    config: FilterConfig = {
        "filter_fields": {
            "title": {"contains", "eq"},
            "views": {"ge", "le"},
            "status": {"in"},
            "author.name": {"contains"},
        },
        "sort_fields": ["title", "views", "author.name"],
        "pagination_type": "limit_offset",
        "pagination_size": 10,
        "alias_generator": "snake_case",
    }
    aliases = resolve_filter_aliases(config, model=_FastAPIGridArticle)
    assert "title_contains" in aliases
    assert "order_by" in aliases

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    filter_dep = provide_filters(config, model=_FastAPIGridArticle)
    app = FastAPI()

    @app.get("/grid")
    async def list_grid(
        filters: Annotated[list[FilterTypes], Depends(filter_dep)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, Any]:
        service = _FastAPIGridArticleService(session=session)
        rows, total = await service.get_many_and_count(*filters)
        return {
            "total": total,
            "items": [{"title": row.title, "views": row.views, "status": row.status} for row in rows],
        }

    async def _seed() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(_FastAPIGridBase.metadata.create_all)
        async with session_factory() as session:
            ada = _FastAPIGridAuthor(name="Ada")
            cody = _FastAPIGridAuthor(name="Cody")
            session.add_all(
                [
                    _FastAPIGridArticle(title="SQL Basics", views=150, status="draft", author=cody),
                    _FastAPIGridArticle(title="SQL Tuning", views=450, status="draft", author=ada),
                    _FastAPIGridArticle(title="Python Hints", views=200, status="published", author=cody),
                ]
            )
            await session.commit()

    anyio.run(_seed)
    with TestClient(app) as client:
        resp = client.get(
            "/grid",
            params=[
                ("title_contains", "sql"),
                ("views_ge", "100"),
                ("views_le", "500"),
                ("status_in", "draft"),
                ("order_by", "author.name"),
                ("current_page", "1"),
                ("page_size", "5"),
            ],
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 2
        assert [item["title"] for item in data["items"]] == ["SQL Tuning", "SQL Basics"]
    anyio.run(engine.dispose)


def test_fastapi_pagination_max_size_validation_and_openapi() -> None:
    filter_dep = provide_filters(
        {"pagination_type": "limit_offset", "pagination_max_size": 15},
        DependencyDefaults(),
    )

    app = FastAPI()

    @app.get("/items")
    def list_items(filters: Annotated[list[FilterTypes], Depends(filter_dep)]) -> dict[str, int]:
        limit_offset = next(f for f in filters if isinstance(f, LimitOffsetFilter))
        return {"limit": limit_offset.limit, "offset": limit_offset.offset}

    with TestClient(app) as client:
        assert client.get("/items").json() == {"limit": 15, "offset": 0}
        assert client.get("/items", params={"pageSize": "15"}).json() == {"limit": 15, "offset": 0}
        assert client.get("/items", params={"pageSize": "16"}).status_code == 422
        params = {
            param["name"]: param["schema"]
            for param in client.get("/openapi.json").json()["paths"]["/items"]["get"]["parameters"]
        }
        assert params["pageSize"]["minimum"] == 1
        assert params["pageSize"]["maximum"] == 15

    capped_defaults = DependencyDefaults()
    capped_defaults.DEFAULT_PAGINATION_SIZE = 25
    clamped_dep = provide_filters({"pagination_type": "limit_offset", "pagination_max_size": 10}, capped_defaults)
    clamped_app = FastAPI()

    @clamped_app.get("/clamped")
    def list_clamped(filters: Annotated[list[FilterTypes], Depends(clamped_dep)]) -> dict[str, int]:
        limit_offset = next(f for f in filters if isinstance(f, LimitOffsetFilter))
        return {"limit": limit_offset.limit, "offset": limit_offset.offset}

    with TestClient(clamped_app) as client:
        assert client.get("/clamped").json() == {"limit": 10, "offset": 0}

    with pytest.raises(ImproperConfigurationError, match="cannot exceed"):
        provide_filters({"pagination_type": "limit_offset", "pagination_size": 30, "pagination_max_size": 15})
    with pytest.raises(ImproperConfigurationError, match="pagination_max_size"):
        provide_filters({"pagination_max_size": 0})

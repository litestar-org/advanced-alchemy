"""Tests for the FastAPI DI module."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Union, cast
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# Assuming necessary classes are importable from the new provider module
from advanced_alchemy.extensions.fastapi.providers import (
    DEPENDENCY_DEFAULTS,
    DependencyCache,
    DependencyDefaults,
    FilterConfig,
    _create_filter_aggregate_function_fastapi,  # pyright: ignore[reportPrivateUsage]
    create_filter_dependencies,
    dep_cache,  # Import the global cache instance
)
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    FilterTypes,
    LimitOffset,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.utils.singleton import SingletonMeta

# --- Test Helper Functions/Fixtures --- #

# No helper needed for these tests

# --- Individual Filter Provider Function Tests (Removed) ---
# These are now implementation details of the aggregate builder
# and tested via the aggregate function tests.

# --- Cache Tests --- #


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
        cache.add_dependencies(key, deps1)
        assert cache.get_dependencies(key) == deps1

        # Test retrieving non-existent key
        assert cache.get_dependencies(hash("nonexistent")) is None


def test_create_filter_dependencies_cache_hit() -> None:
    """Test create_filter_dependencies with cache hit."""
    # Setup cache with a pre-existing entry
    config = cast(FilterConfig, {"id_filter": True})
    cache_key = hash(tuple(sorted(config.items())))
    mock_deps = {"filters": Depends(lambda: "cached_dependency")}

    with patch.object(dep_cache, "get_dependencies", return_value=mock_deps) as mock_get:
        with patch.object(dep_cache, "add_dependencies") as mock_add:
            with patch(
                "advanced_alchemy.extensions.fastapi.providers._create_filter_aggregate_function_fastapi"
            ) as mock_create:
                deps = create_filter_dependencies(config)

                # Verify cache was checked
                mock_get.assert_called_once_with(cache_key)

                # Verify result is from cache
                assert deps == mock_deps

                # Verify aggregate function builder was NOT called
                mock_create.assert_not_called()

                # Verify cache wasn't updated again
                mock_add.assert_not_called()


def test_create_filter_dependencies_cache_miss() -> None:
    """Test create_filter_dependencies with cache miss."""
    config = cast(FilterConfig, {"created_at": True})
    cache_key = hash(tuple(sorted(config.items())))
    mock_agg_func = lambda: [  # noqa: E731
        BeforeAfter(field_name="created_at", before=None, after=None)
    ]  # Dummy aggregate function

    with patch.object(dep_cache, "get_dependencies", return_value=None) as mock_get:  # Simulate cache miss
        with patch.object(dep_cache, "add_dependencies") as mock_add:
            # Mock the builder to return our dummy aggregate function
            with patch(
                "advanced_alchemy.extensions.fastapi.providers._create_filter_aggregate_function_fastapi",
                return_value=mock_agg_func,
            ) as mock_create:
                deps = create_filter_dependencies(config)

                # Verify cache was checked
                mock_get.assert_called_once_with(cache_key)

                # Verify _create_filter_aggregate_function_fastapi was called
                mock_create.assert_called_once_with(config, DEPENDENCY_DEFAULTS)

                # Verify cache was updated with the created dependencies
                # We need to compare the structure, not object identity of Depends(mock_agg_func)
                mock_add.assert_called_once()
                added_key, added_deps = mock_add.call_args[0]
                assert added_key == cache_key
                assert "filters" in added_deps
                # Check that it's a Depends object by verifying it has the dependency attribute
                assert hasattr(added_deps["filters"], "dependency")
                assert added_deps["filters"].dependency is mock_agg_func

                # Verify return value matches the created dependency structure
                assert deps["filters"].dependency is mock_agg_func


# --- Aggregate Dependency Function Builder Tests --- #


def test_create_filter_aggregate_function_fastapi() -> None:
    """Test the signature and direct call of the aggregated dependency function."""
    config = cast(
        FilterConfig,
        {
            "id_filter": True,
            "created_at": True,
            "pagination_type": "limit_offset",
            "search": "title",
            "sort_field": "id",
        },
    )

    aggregate_func = _create_filter_aggregate_function_fastapi(config, DEPENDENCY_DEFAULTS)
    assert callable(aggregate_func)

    # Check signature has correct parameters and Depends defaults
    sig = inspect.signature(aggregate_func)
    assert DEPENDENCY_DEFAULTS.ID_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.CREATED_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.LIMIT_OFFSET_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.SEARCH_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.ORDER_BY_DEPENDENCY_KEY in sig.parameters
    # Check return annotation origin type (list) and its argument (FilterTypes)
    assert hasattr(sig.return_annotation, "__origin__")
    assert sig.return_annotation.__origin__ is list
    assert sig.return_annotation.__args__[0] is FilterTypes

    for param_name, param in sig.parameters.items():
        # Check that it's a Depends object by verifying it has the dependency attribute
        assert hasattr(param.default, "dependency")
        # Check annotation (Optional[...] for filters that can return None)
        if param_name in (DEPENDENCY_DEFAULTS.LIMIT_OFFSET_DEPENDENCY_KEY, DEPENDENCY_DEFAULTS.ORDER_BY_DEPENDENCY_KEY):
            # These parameters should not be Optional
            assert param.annotation is not None
            assert not (
                hasattr(param.annotation, "__origin__")
                and param.annotation.__origin__ is Union
                and type(None) in param.annotation.__args__
            )
        else:
            # Other parameters should be Optional (Union[..., None])
            assert hasattr(param.annotation, "__origin__")
            assert param.annotation.__origin__ is Union
            assert type(None) in param.annotation.__args__

    # Directly call the aggregate function with mock filter objects
    # This tests the body logic of the dynamically created function
    mock_id_filter = CollectionFilter(field_name="id", values=["1"])
    mock_created_filter = BeforeAfter(field_name="created_at", before=datetime.now(), after=None)
    mock_limit_offset = LimitOffset(limit=10, offset=0)
    mock_search_filter = SearchFilter(field_name={"title"}, value="test", ignore_case=False)
    mock_order_by = OrderBy(field_name="id", sort_order="asc")

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
    mock_order_by_none = OrderBy(field_name=None, sort_order="asc")  # type: ignore[arg-type]

    result_some_none = aggregate_func(
        id_filter=None,  # Simulate no 'ids' param provided
        created_filter=None,  # Simulate no date params provided
        limit_offset=mock_limit_offset,  # Always present
        search_filter=mock_search_filter_none,  # Aggregate func should filter this out based on value=None
        order_by=mock_order_by_none,  # Aggregate func should filter this out based on field_name=None
    )
    assert len(result_some_none) == 1  # Only LimitOffset should remain
    assert mock_limit_offset in result_some_none
    assert mock_id_filter not in result_some_none
    assert mock_created_filter not in result_some_none
    assert mock_search_filter not in result_some_none
    assert mock_order_by not in result_some_none


# --- Main create_filter_dependencies Tests --- #


def test_create_filter_dependencies_empty_config() -> None:
    """Test create_filter_dependencies with an empty config."""
    deps = create_filter_dependencies({})  # type: ignore
    assert deps == {}


def test_create_filter_dependencies_all_filters() -> None:
    """Test create_filter_dependencies enabling all filters returns the aggregate."""
    config = cast(
        FilterConfig,
        {
            "id_filter": True,
            "created_at": True,
            "updated_at": True,
            "pagination_type": "limit_offset",
            "search": "name, description",
            "sort_field": "created_at",
        },
    )

    # Clear cache before test
    dep_cache.dependencies.clear()
    deps = create_filter_dependencies(config)

    assert DEPENDENCY_DEFAULTS.FILTERS_DEPENDENCY_KEY in deps
    filters_dependency = deps[DEPENDENCY_DEFAULTS.FILTERS_DEPENDENCY_KEY]
    # Check that it's a Depends object by verifying it has the dependency attribute
    assert hasattr(filters_dependency, "dependency")

    aggregate_func = filters_dependency.dependency
    assert callable(aggregate_func)

    # Check signature of the final aggregate function matches expectations
    sig = inspect.signature(aggregate_func)
    assert DEPENDENCY_DEFAULTS.ID_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.CREATED_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.UPDATED_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.LIMIT_OFFSET_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.SEARCH_FILTER_DEPENDENCY_KEY in sig.parameters
    assert DEPENDENCY_DEFAULTS.ORDER_BY_DEPENDENCY_KEY in sig.parameters


# --- Integration Test with OpenAPI Schema Check --- #


def test_create_filter_dependencies_integration_and_openapi() -> None:
    """Test integration with FastAPI using TestClient and check OpenAPI schema."""
    config = cast(
        FilterConfig,
        {
            "id_filter": True,
            "pagination_type": "limit_offset",
            "search": "name",
            "sort_field": "name",  # Enables OrderBy
            "created_at": True,
        },
    )

    # Clear cache before test
    dep_cache.dependencies.clear()
    deps = create_filter_dependencies(config)
    filters_dependency = deps[DEPENDENCY_DEFAULTS.FILTERS_DEPENDENCY_KEY]

    app = FastAPI()

    @app.get("/items")
    async def get_items(filters: list[FilterTypes] = filters_dependency) -> list[str]:
        # Return simple representation for verification
        return [type(f).__name__ for f in filters]

    client = TestClient(app)

    # === Runtime Test ===
    # Test case: Apply multiple filters
    response = client.get(
        "/items?ids=1&ids=2&currentPage=2&pageSize=5&searchString=apple&orderBy=name&sortOrder=asc&createdAfter=2023-01-01T00:00:00Z"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Check that all expected filter types were created and collected
    # Note: OrderBy and LimitOffset are always created if configured
    # SearchFilter only if searchString provided, BeforeAfter only if date provided, CollectionFilter only if ids provided
    assert "CollectionFilter" in data
    assert "LimitOffset" in data
    assert "SearchFilter" in data
    assert "OrderBy" in data
    assert "BeforeAfter" in data  # For created_at
    assert len(data) == 5  # type: ignore[arg-type]

    # Test case: Only defaults (expect LimitOffset, OrderBy)
    response = client.get("/items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert "LimitOffset" in data
    assert "OrderBy" in data
    assert "CollectionFilter" not in data
    assert "SearchFilter" not in data
    assert "BeforeAfter" not in data
    assert len(data) == 2  # type: ignore[arg-type]

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


# Custom Defaults Test (remains largely the same logic)
def test_custom_dependency_defaults_fastapi() -> None:
    """Test using custom dependency defaults with FastAPI provider."""

    class CustomDefaults(DependencyDefaults):
        FILTERS_DEPENDENCY_KEY = "custom_filters"
        LIMIT_OFFSET_DEPENDENCY_KEY = "paging"
        ORDER_BY_DEPENDENCY_KEY = "ordering"
        DEFAULT_PAGINATION_SIZE = 5

    custom_defaults = CustomDefaults()
    config = cast(
        FilterConfig,
        {
            "id_filter": True,
            "pagination_type": "limit_offset",
            "sort_field": "name",  # uses custom ORDER_BY_DEPENDENCY_KEY
        },
    )

    # Clear cache before test
    dep_cache.dependencies.clear()
    deps = create_filter_dependencies(config, dep_defaults=custom_defaults)

    # Check the key uses the custom default
    assert "custom_filters" in deps
    filters_dependency = deps["custom_filters"]
    # Check that it's a Depends object by verifying it has the dependency attribute
    assert hasattr(filters_dependency, "dependency")

    aggregate_func = filters_dependency.dependency
    sig = inspect.signature(aggregate_func)
    assert "id_filter" in sig.parameters  # Uses standard key if not overridden
    assert "paging" in sig.parameters  # Custom key used for limit/offset param name
    assert "ordering" in sig.parameters  # Custom key used for order by param name

    # Test integration and OpenAPI with custom defaults
    app = FastAPI()

    @app.get("/custom")
    async def get_custom(filters: list[FilterTypes] = filters_dependency) -> list[str]:
        return [type(f).__name__ for f in filters]

    client = TestClient(app)
    response = client.get("/custom?ids=a&currentPage=3&orderBy=id")  # pageSize defaults to 5 (CustomDefaults)
    assert response.status_code == 200
    data = response.json()
    assert "CollectionFilter" in data
    assert "LimitOffset" in data
    assert "OrderBy" in data
    assert len(data) == 3  # type: ignore[arg-type]

    # Check OpenAPI uses custom default page size
    schema = client.get("/openapi.json").json()
    custom_path_item = schema.get("paths", {}).get("/custom", {}).get("get", {})
    custom_parameters = custom_path_item.get("parameters", [])

    custom_page_size_param = next((p for p in custom_parameters if p["name"] == "pageSize"), None)
    assert custom_page_size_param is not None
    assert custom_page_size_param["schema"]["default"] == 5  # Custom default


def test_openapi_schema_comprehensive() -> None:
    """Test OpenAPI schema generation for all filter types and edge cases."""
    config = cast(
        FilterConfig,
        {
            "id_filter": True,
            "created_at": True,
            "updated_at": True,
            "pagination_type": "limit_offset",
            "search": "name,description,email",  # Multiple search fields
            "sort_field": {"name", "created_at", "email"},  # Multiple sort fields (using set)
            "not_in_fields": ["status", "category"],  # Not-in fields
            "in_fields": ["tag", "author_id"],  # In fields
        },
    )

    deps = create_filter_dependencies(config)
    filters_dependency = deps[DEPENDENCY_DEFAULTS.FILTERS_DEPENDENCY_KEY]

    app = FastAPI()

    @app.get("/complex")
    async def get_complex(filters: list[FilterTypes] = filters_dependency) -> list[str]:
        return [type(f).__name__ for f in filters]

    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    path_item = schema.get("paths", {}).get("/complex", {}).get("get", {})
    parameters = path_item.get("parameters", [])

    # 1. Test all parameter names are present
    param_names = {p["name"] for p in parameters}
    expected_params = {
        # ID Filter params
        "ids",
        # Date Filter params
        "createdBefore",
        "createdAfter",
        "updatedBefore",
        "updatedAfter",
        # Pagination params
        "currentPage",
        "pageSize",
        # Search params (one set for each search field)
        "searchString",
        "searchIgnoreCase",
        # Sort params
        "orderBy",
        "sortOrder",
        # Not-in params
        "statusNotIn",
        "categoryNotIn",
        # In params
        "tagIn",
        "author_idIn",
    }
    assert param_names == expected_params

    # 2. Test array parameter schemas
    array_params = ["ids", "statusNotIn", "categoryNotIn", "tagIn", "author_idIn"]
    for param_name in array_params:
        param = next(p for p in parameters if p["name"] == param_name)
        assert "anyOf" in param["schema"]
        array_schema = next(s for s in param["schema"]["anyOf"] if s.get("type") == "array")
        assert array_schema["type"] == "array"
        assert array_schema["items"]["type"] in ["string", "number"]  # Depending on the field type

    # 3. Test date parameter schemas
    date_params = ["createdBefore", "createdAfter", "updatedBefore", "updatedAfter"]
    for param_name in date_params:
        param = next(p for p in parameters if p["name"] == param_name)
        # Check for 'format' at the top level first (FastAPI's behavior with json_schema_extra)
        # Then check within anyOf for broader compatibility if needed
        assert param["schema"].get("format") == "date-time" or any(
            cast(
                "Iterable[Any]",
                (s.get("format") == "date-time" for s in param["schema"].get("anyOf", []) if isinstance(s, dict)),
            )
        )

    # 4. Test numeric parameter schemas
    # Removed - relies on comparison_fields

    # 5. Test boolean parameter schemas
    bool_params = ["searchIgnoreCase"]  # Removed exists_fields params
    for param_name in bool_params:
        param = next(p for p in parameters if p["name"] == param_name)
        if param_name == "searchIgnoreCase":
            assert param["schema"]["default"] is False
        assert "anyOf" in param["schema"]
        bool_schema = next(s for s in param["schema"]["anyOf"] if s.get("type") == "boolean")
        assert bool_schema["type"] == "boolean"

    # 6. Test enum parameter schemas
    param = next(p for p in parameters if p["name"] == "sortOrder")
    assert "anyOf" in param["schema"]
    enum_schema = next(s for s in param["schema"]["anyOf"] if "enum" in s)
    assert set(enum_schema["enum"]) == {"asc", "desc"}

    # 7. Test default values
    param = next(p for p in parameters if p["name"] == "pageSize")
    assert param["schema"]["default"] == DEPENDENCY_DEFAULTS.DEFAULT_PAGINATION_SIZE
    param = next(p for p in parameters if p["name"] == "currentPage")
    assert param["schema"]["default"] == 1

    # 8. Test runtime behavior with complex query
    response = client.get(
        "/complex",
        params={
            "ids": ["1", "2"],
            "createdAfter": "2023-01-01T00:00:00Z",
            "updatedBefore": "2024-01-01T00:00:00Z",
            "currentPage": 2,
            "pageSize": 50,
            "searchString": "test",
            "searchIgnoreCase": True,
            "orderBy": "name",
            "sortOrder": "desc",
            "statusNotIn": ["pending", "rejected"],
            "categoryNotIn": ["spam"],
            "tagIn": ["python", "fastapi"],
            "author_idIn": ["user1", "user2"],
        },
    )
    assert response.status_code == 200
    data = response.json()

    # Verify all filter types are present
    expected_filter_types = {
        "CollectionFilter",  # For ids
        "BeforeAfter",  # For created_at and updated_at
        "LimitOffset",  # For pagination
        "SearchFilter",  # For search
        "OrderBy",  # For sorting
        "NotInCollectionFilter",  # For not-in checks
        "CollectionFilter",  # For in checks (and potentially id_filter)
    }
    assert set(data) == expected_filter_types


def test_openapi_schema_edge_cases() -> None:
    """Test OpenAPI schema generation for edge cases and special configurations."""
    # Test with minimal configuration
    min_config = cast(FilterConfig, {"pagination_type": "limit_offset"})
    deps = create_filter_dependencies(min_config)
    filters_dependency = deps[DEPENDENCY_DEFAULTS.FILTERS_DEPENDENCY_KEY]

    app = FastAPI()

    @app.get("/minimal")
    async def get_minimal(filters: list[FilterTypes] = filters_dependency):
        return [type(f).__name__ for f in filters]

    # Test with all optional filters disabled
    @app.get("/no-optionals")
    async def get_no_optionals(
        filters: list[FilterTypes] = create_filter_dependencies(
            cast(FilterConfig, {"pagination_type": "limit_offset", "sort_field": "id"})
        )[DEPENDENCY_DEFAULTS.FILTERS_DEPENDENCY_KEY],
    ):
        return [type(f).__name__ for f in filters]

    # Test with custom validation
    @app.get("/custom-validation")
    async def get_custom_validation(
        filters: list[FilterTypes] = create_filter_dependencies(
            cast(
                FilterConfig,
                {
                    "id_filter": True,
                    "pagination_type": "limit_offset",
                    "sort_field": "id",
                    "search": "email",  # Will have email format validation
                    "created_at": True,  # Add created_at filter
                },
            )
        )[DEPENDENCY_DEFAULTS.FILTERS_DEPENDENCY_KEY],
    ) -> list[str]:
        return [type(f).__name__ for f in filters]

    client = TestClient(app)

    # Test minimal schema
    schema = client.get("/openapi.json").json()
    min_params = schema["paths"]["/minimal"]["get"]["parameters"]
    assert len(min_params) == 2  # Only pageSize and currentPage
    assert {p["name"] for p in min_params} == {"pageSize", "currentPage"}

    # Test no-optionals schema
    no_opt_params = schema["paths"]["/no-optionals"]["get"]["parameters"]
    required_params = [p for p in no_opt_params if p["required"] is True]
    assert len(required_params) == 0  # All parameters should be optional

    # Test runtime with edge cases
    # 1. Test with empty query params
    response = client.get("/minimal")
    assert response.status_code == 200
    assert len(response.json()) == 1  # Only LimitOffset

    # 2. Test with invalid values
    response = client.get("/minimal", params={"pageSize": -1})
    assert response.status_code == 422  # Validation error

    # 3. Test with extremely large values
    response = client.get("/minimal", params={"pageSize": 1000000})
    assert response.status_code == 422  # Should fail validation

    # 4. Test with malformed date
    response = client.get(
        "/custom-validation",
        params={"createdAfter": "invalid-date"},
    )
    assert response.status_code == 422  # Should fail validation

    # 5. Test with special characters in search
    response = client.get(
        "/custom-validation",
        params={"searchString": "test@example.com<script>"},
    )
    assert response.status_code == 200  # Should handle special characters

    # 6. Test with multiple identical parameters
    response = client.get(
        "/custom-validation",
        params=[("orderBy", "id"), ("orderBy", "email")],
    )
    assert response.status_code == 200  # FastAPI uses the last value, so 200 OK

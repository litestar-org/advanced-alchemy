"""Tests for the FastAPI DI module."""

import inspect
import sys  # Import sys
import typing
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Annotated, Union, cast
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

# Assuming necessary classes are importable from the new provider module
from advanced_alchemy.base import UUIDBase
from advanced_alchemy.extensions.fastapi import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.fastapi.providers import (
    DEPENDENCY_DEFAULTS,
    DependencyCache,
    DependencyDefaults,
    FieldNameType,
    FilterConfig,
    _create_filter_aggregate_function_fastapi,  # pyright: ignore[reportPrivateUsage]
    dep_cache,  # Import the global cache instance
    provide_filters,
)
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    FilterTypes,
    LimitOffset,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.utils.singleton import SingletonMeta


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
        assert cache.get_dependencies(hash("nonexistent")) is None


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
                deps = provide_filters(config)

                # Verify cache was checked
                mock_get.assert_called_once_with(cache_key)

                # Verify _create_filter_aggregate_function_fastapi was called
                mock_create.assert_called_once_with(config, DEPENDENCY_DEFAULTS)

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
    assert hasattr(sig.return_annotation, "__origin__")
    assert typing.get_origin(sig.return_annotation) is Annotated
    assert sig.return_annotation.__args__[0] == list[FilterTypes]

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
            "sort_field": "name",  # Enables OrderBy
            "created_at": True,
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
        "/items?ids=123e4567-e89b-12d3-a456-426614174000&ids=123e4567-e89b-12d3-a456-426614174001&currentPage=2&pageSize=5&searchString=apple&orderBy=name&sortOrder=asc&createdAfter=2023-01-01T00:00:00Z"
    )
    assert response.status_code == 200
    data = cast(list[str], response.json())
    assert isinstance(data, list)
    # Check that all expected filter types were created and collected
    assert "CollectionFilter" in data
    assert "LimitOffset" in data
    assert "SearchFilter" in data
    assert "OrderBy" in data
    assert "BeforeAfter" in data
    assert len(data) == 5

    # Test case: Only defaults (expect LimitOffset, OrderBy)
    response = client.get("/items")
    assert response.status_code == 200
    data = cast(list[str], response.json())
    assert isinstance(data, list)
    assert "LimitOffset" in data
    assert "OrderBy" in data
    assert "CollectionFilter" not in data
    assert "SearchFilter" not in data
    assert "BeforeAfter" not in data
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
    assert "CollectionFilter" in data
    assert "LimitOffset" in data
    assert "OrderBy" in data
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
    }
    assert param_names == expected_param_names

    # Test that function parameters have the correct types and defaults
    for name, param in sig.parameters.items():
        # Check types for known parameters
        if name == "id_filter":
            assert "UUID" in str(param.annotation), f"id_filter should have UUID type, got {param.annotation}"
        elif name in ("created_filter", "updated_filter"):
            assert "BeforeAfter" in str(param.annotation), (
                f"{name} should have BeforeAfter type, got {param.annotation}"
            )
        elif name == "limit_offset":
            assert "LimitOffset" in str(param.annotation), (
                f"limit_offset should have LimitOffset type, got {param.annotation}"
            )
        elif name == "search_filter":
            assert "SearchFilter" in str(param.annotation), (
                f"search_filter should have SearchFilter type, got {param.annotation}"
            )
        elif name == "order_by":
            assert "OrderBy" in str(param.annotation), f"order_by should have OrderBy type, got {param.annotation}"
        elif "not_in" in name:
            assert "NotInCollectionFilter" in str(param.annotation), (
                f"{name} should have NotInCollectionFilter type, got {param.annotation}"
            )
        elif "in_filter" in name:
            assert "CollectionFilter" in str(param.annotation), (
                f"{name} should have CollectionFilter type, got {param.annotation}"
            )

    # Check that the return annotation is list[FilterTypes]
    assert deps.__annotations__["return"] == list[FilterTypes]

    # Test direct call with filter values
    mock_id_filter = CollectionFilter(field_name="id", values=["123e4567-e89b-12d3-a456-426614174000"])
    mock_created_filter = BeforeAfter(field_name="created_at", before=datetime.now(), after=None)
    mock_limit_offset = LimitOffset(limit=10, offset=0)
    mock_search_filter = SearchFilter(field_name={"name"}, value="test", ignore_case=False)
    mock_order_by = OrderBy(field_name="name", sort_order="asc")

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
    )

    # Verify that the results contain the expected filter objects
    assert isinstance(result, list)
    assert len(result) == 5
    assert mock_id_filter in result
    assert mock_created_filter in result
    assert mock_limit_offset in result
    assert mock_search_filter in result
    assert mock_order_by in result


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
    assert "LimitOffset" in data

    # Test runtime behavior for no optionals
    response = client.get("/no-optionals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2  # type: ignore[arg-type]
    assert "LimitOffset" in data
    assert "OrderBy" in data

    # Test runtime behavior for custom validation
    response = client.get(
        "/custom-validation?ids=123e4567-e89b-12d3-a456-426614174000&currentPage=2&pageSize=5&orderBy=id&searchString=test&createdAfter=2023-01-01T00:00:00Z"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5  # type: ignore[arg-type]
    assert "CollectionFilter" in data
    assert "LimitOffset" in data
    assert "OrderBy" in data
    assert "SearchFilter" in data
    assert "BeforeAfter" in data


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
    assert "CollectionFilter" in filter_types
    assert "LimitOffset" in filter_types
    assert "SearchFilter" in filter_types
    assert "BeforeAfter" in filter_types
    # OrderBy is not explicitly configured but might have defaults, let's check if it's NOT there unless configured
    assert "OrderBy" not in filter_types  # OrderBy was not configured in this specific provide_filters call
    assert len(filter_types) == 4  # type: ignore

    # Test case: Only defaults (expect LimitOffset)
    response = client.get("/diska-items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["simple_model_table_name"] == "simple_dishka_table"
    filter_types = data.get("filters", [])  # type: ignore
    assert isinstance(filter_types, list)
    assert "LimitOffset" in filter_types  # Default pagination
    assert "CollectionFilter" not in filter_types
    assert "SearchFilter" not in filter_types
    assert "BeforeAfter" not in filter_types
    assert "OrderBy" not in filter_types
    assert len(filter_types) == 1  # type: ignore

    await container.close()

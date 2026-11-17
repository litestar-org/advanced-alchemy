"""Tests for the DI module."""

from __future__ import annotations

import inspect
import sys
import unittest.mock
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import pytest
from litestar import Litestar, get
from litestar.di import NamedDependency, Provide
from litestar.openapi.config import OpenAPIConfig
from litestar.params import SkipValidation
from litestar.testing import TestClient
from sqlalchemy import ForeignKey, FromClause, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column, relationship

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin, SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.plugin import signature_namespace_values
from advanced_alchemy.extensions.litestar.providers import (
    DEPENDENCY_DEFAULTS,
    ChoiceField,
    DependencyCache,
    DependencyDefaults,
    FilterConfig,
    FilterFieldsSpec,
    FilterOperator,
    SingletonMeta,
    _create_filter_aggregate_function,  # pyright: ignore[reportPrivateUsage]
    _create_statement_filters,  # pyright: ignore[reportPrivateUsage]
    _is_async_provider_target,  # pyright: ignore[reportPrivateUsage]
    _with_dep_defaults_prefix,  # pyright: ignore[reportPrivateUsage]
    create_filter_dependencies,
    create_service_dependencies,
    create_service_provider,
    dep_cache,
)
from advanced_alchemy.filters import (
    BeforeAfterFilter,
    BooleanFilter,
    ChoicesFilter,
    ComparisonFilter,
    FilterTypes,
    InCollectionFilter,
    LimitOffsetFilter,
    NotInCollectionFilter,
    NotNullFilter,
    NullFilter,
    OrderByFilter,
    RelationshipFilter,
    SearchFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.service import (
    ServiceGroup,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.types.identity import BigIntIdentity
from advanced_alchemy.utils.dependencies import resolve_filter_aliases
from tests.helpers import anext_

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


class Base(DeclarativeBase):
    """Base class for models."""

    if TYPE_CHECKING:
        __name__: str  # type: ignore
        __table__: FromClause  # type: ignore
        __mapper__: Mapper[Any]  # type: ignore

    id: Mapped[int] = mapped_column(BigIntIdentity, primary_key=True)

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dict[str, Any]: A dict representation of the model
        """
        exclude = {"sa_orm_sentinel", "_sentinel"}.union(self._sa_instance_state.unloaded).union(exclude or [])  # type: ignore[attr-defined]
        return {field: getattr(self, field) for field in self.__mapper__.columns.keys() if field not in exclude}


class DITestModel(Base):
    """Test model for use in tests."""

    __tablename__ = "di_test_model"

    name: Mapped[str] = mapped_column(String)


class MockSyncService(SQLAlchemySyncRepositoryService[DITestModel]):
    """Mock sync service class for testing."""

    class Repo(SQLAlchemySyncRepository[DITestModel]):
        """Mock repo class."""

        model_type = DITestModel

    repository_type = Repo


class MockAsyncService(SQLAlchemyAsyncRepositoryService[DITestModel]):
    """Mock async service class for testing."""

    class Repo(SQLAlchemyAsyncRepository[DITestModel]):
        """Mock repo class."""

        model_type = DITestModel

    repository_type = Repo


def test_singleton_pattern() -> None:
    """Test that the SingletonMeta creates singletons."""

    class TestClass(metaclass=SingletonMeta):
        """Test class using SingletonMeta."""

        def __init__(self) -> None:
            self.value = uuid.uuid4().hex

    # Instances should be the same
    instance1 = TestClass()
    instance2 = TestClass()

    assert instance1 is instance2
    assert instance1.value == instance2.value


def test_multiple_classes() -> None:
    """Test that different classes using SingletonMeta have different instances."""

    class TestClass1(metaclass=SingletonMeta):
        """First test class using SingletonMeta."""

        def __init__(self) -> None:
            self.value = 1

    class TestClass2(metaclass=SingletonMeta):
        """Second test class using SingletonMeta."""

        def __init__(self) -> None:
            self.value = 2

    instance1 = TestClass1()
    instance2 = TestClass2()

    assert instance1 is not instance2  # type: ignore
    assert instance1.value != instance2.value


def test_add_get_dependencies() -> None:
    """Test adding and retrieving dependencies from cache."""
    # Create a new instance to avoid test interference
    with patch.dict(SingletonMeta._instances, {}, clear=True):  # pyright: ignore[reportPrivateUsage]
        cache = DependencyCache()

        # Test with string key
        deps1 = {"service": Provide(lambda: "service")}
        cache.add_dependencies("key1", deps1)
        assert cache.get_dependencies("key1") == deps1

        # Test with integer key
        deps2 = {"filter": Provide(lambda: "filter")}
        cache.add_dependencies(123, deps2)
        assert cache.get_dependencies(123) == deps2

        # Test retrieving non-existent key
        assert cache.get_dependencies("nonexistent") is None


def test_global_instance() -> None:
    """Test that the global dep_cache instance is a singleton."""
    # Do not clear SingletonMeta._instances, so that dep_cache remains the global singleton
    new_cache = DependencyCache()
    assert new_cache is dep_cache


def test_create_sync_service_provider() -> None:
    """Test creating a sync service provider."""
    provider = create_service_provider(MockSyncService)

    # Ensure the provider is callable
    assert callable(provider)
    svc = next(provider(db_session=MagicMock()))
    assert isinstance(svc, MockSyncService)


def test_create_sync_service_provider_custom() -> None:
    """Test creating a sync service provider."""
    provider = create_service_provider(MockSyncService, config=MagicMock(session_dependency_key="testing_session"))

    # Ensure the provider is callable
    assert callable(provider)
    svc = next(provider(testing_session=MagicMock()))
    assert isinstance(svc, MockSyncService)


def test_create_sync_service_provider_positional() -> None:
    """Test creating an async service provider."""
    provider = create_service_provider(MockSyncService, config=MagicMock(session_dependency_key="testing_session"))

    # Ensure the provider is callable
    assert callable(provider)
    svc = next(provider(MagicMock()))
    assert isinstance(svc, MockSyncService)


async def test_create_async_service_provider() -> None:
    """Test creating an async service provider."""
    provider = create_service_provider(MockAsyncService)

    # Ensure the provider is callable
    assert callable(provider)
    svc = await anext_(provider(db_session=MagicMock()))
    assert isinstance(svc, MockAsyncService)


async def test_create_async_service_provider_custom() -> None:
    """Test creating an async service provider."""
    provider = create_service_provider(MockAsyncService, config=MagicMock(session_dependency_key="testing_session"))

    # Ensure the provider is callable
    assert callable(provider)
    svc = await anext_(provider(testing_session=MagicMock()))
    assert isinstance(svc, MockAsyncService)


async def test_create_async_service_provider_positional() -> None:
    """Test creating an async service provider."""
    provider = create_service_provider(MockAsyncService, config=MagicMock(session_dependency_key="testing_session"))

    # Ensure the provider is callable
    assert callable(provider)
    svc = await anext_(provider(MagicMock()))
    assert isinstance(svc, MockAsyncService)


def test_create_async_service_dependencies() -> None:
    """Test creating async service dependencies."""
    with patch("advanced_alchemy.extensions.litestar.providers.create_service_provider") as mock_create_provider:
        mock_create_provider.return_value = lambda: "async_service"

        deps = create_service_dependencies(
            MockAsyncService,
            key="service",
            statement=select(DITestModel),
            config=MagicMock(),
        )

        assert "service" in deps
        assert isinstance(deps["service"], Provide)

        # Check provider function
        assert deps["service"].dependency() == "async_service"

        # Verify create_service_provider was called correctly
        mock_create_provider.assert_called_once()


def test_create_sync_service_dependencies() -> None:
    """Test creating sync service dependencies."""
    with patch("advanced_alchemy.extensions.litestar.providers.create_service_provider") as mock_create_provider:
        mock_create_provider.return_value = lambda: "sync_service"

        deps = create_service_dependencies(
            MockSyncService,
            key="service",
            statement=select(DITestModel),
            config=MagicMock(),
        )

        assert "service" in deps
        assert isinstance(deps["service"], Provide)

        # Check provider function
        assert deps["service"].dependency() == "sync_service"

        # Verify create_service_provider was called correctly
        mock_create_provider.assert_called_once()

        # Verify sync_to_thread is False for sync services
        assert deps["service"].sync_to_thread is False


def test_create_service_dependencies_with_filters() -> None:
    """Test creating service dependencies with filters."""
    with patch("advanced_alchemy.extensions.litestar.providers.create_service_provider") as mock_create_provider:
        with patch("advanced_alchemy.extensions.litestar.providers.create_filter_dependencies") as mock_create_filters:
            mock_create_provider.return_value = lambda: "service"
            mock_create_filters.return_value = {"filter1": Provide(lambda: "filter1")}

            deps = create_service_dependencies(
                MockSyncService,
                key="service",
                filters={"id_filter": int},
            )

            assert "service" in deps
            assert "filter1" in deps

            # Verify create_filter_dependencies was called
            mock_create_filters.assert_called_once_with({"id_filter": int}, DEPENDENCY_DEFAULTS)


def test_create_filter_dependencies_cache_hit() -> None:
    """Test create_filter_dependencies with cache hit."""
    # Setup cache with a pre-existing entry
    mock_deps = {"test": Provide(lambda: "test")}

    with patch.object(dep_cache, "get_dependencies", return_value=mock_deps) as mock_get:
        with patch.object(dep_cache, "add_dependencies") as mock_add:
            config = cast(FilterConfig, {"key1": 1, "key2": 2})
            deps = create_filter_dependencies(config)

            # Verify cache was checked
            mock_get.assert_called_once()

            # Verify result is from cache
            assert deps == mock_deps

            # Verify cache wasn't updated
            mock_add.assert_not_called()


def test_create_filter_dependencies_cache_miss() -> None:
    """Test create_filter_dependencies with cache miss."""
    # Setup cache to return None (cache miss)
    mock_deps = {"test": Provide(lambda: "test")}

    with patch.object(dep_cache, "get_dependencies", return_value=None) as mock_get:
        with patch.object(dep_cache, "add_dependencies") as mock_add:
            with patch(
                "advanced_alchemy.extensions.litestar.providers._create_statement_filters", return_value=mock_deps
            ) as mock_create:
                config = cast(FilterConfig, {"key1": 1, "key2": 2})
                deps = create_filter_dependencies(config)

                # Verify cache was checked
                mock_get.assert_called_once()

                # Verify _create_statement_filters was called
                mock_create.assert_called_once()

                # Verify cache was updated
                mock_add.assert_called_once()

                # Verify return value
                assert deps == mock_deps


def test_id_filter() -> None:
    """Test creating ID filter dependency."""
    config = cast(FilterConfig, {"id_filter": int})
    deps = _create_statement_filters(config)

    assert "id_filter" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["id_filter"].dependency
    f = provider_func(ids=["1", "2", "3"])
    assert isinstance(f, InCollectionFilter)
    assert f.field_name == "id"
    assert f.values is not None  # type: ignore
    assert f.values == ["1", "2", "3"]  # type: ignore


def test_created_at_filter() -> None:
    """Test creating created_at filter dependency."""
    config = cast(FilterConfig, {"created_at": "created_at"})
    deps = _create_statement_filters(config)

    assert "created_filter" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["created_filter"].dependency
    before = datetime.now()
    later = datetime.now() + timedelta(days=1)
    f = provider_func(created_at_before=before, created_at_after=later)
    assert isinstance(f, BeforeAfterFilter)
    assert f.field_name == "created_at"
    assert f.before == before
    assert f.after == later


def test_updated_at_filter() -> None:
    """Test creating updated_at filter dependency."""
    config = cast(FilterConfig, {"updated_at": "updated_at"})
    deps = _create_statement_filters(config)

    assert "updated_filter" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["updated_filter"].dependency
    f = provider_func(updated_at_before=datetime.now(), updated_at_after=datetime.now())
    assert isinstance(f, BeforeAfterFilter)
    assert f.field_name == "updated_at"


def test_date_filter_providers_have_distinct_python_parameter_names() -> None:
    """The created/updated filter providers must not share `before`/`after` parameter names.

    Tools that recursively inspect a route dependency graph key on Python parameter names, so
    each provider needs distinct names even though the public query aliases
    (`createdBefore`/`createdAfter`/`updatedBefore`/`updatedAfter`) already differ.
    """
    deps = _create_statement_filters(cast(FilterConfig, {"created_at": True, "updated_at": True}))

    created_sig = inspect.signature(deps["created_filter"].dependency)
    updated_sig = inspect.signature(deps["updated_filter"].dependency)

    assert list(created_sig.parameters) == ["created_at_before", "created_at_after"]
    assert list(updated_sig.parameters) == ["updated_at_before", "updated_at_after"]


def test_search_filter() -> None:
    """Test creating search filter dependency."""
    config = cast(FilterConfig, {"search": "name", "search_ignore_case": True})
    deps = _create_statement_filters(config)

    assert "search_filter" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["search_filter"].dependency
    f = provider_func(search_string="test", ignore_case=True)
    assert isinstance(f, SearchFilter)
    assert f.field_name == "name" or f.field_name == {"name"}
    assert f.value == "test"
    assert f.ignore_case is True
    assert f.escape_wildcards is False


def test_search_filter_applies_configured_wildcard_escaping() -> None:
    """The `search_escape_wildcards` config key makes every generated SearchFilter match literally."""
    deps = _create_statement_filters({"search": "name", "search_escape_wildcards": True})

    f = deps["search_filter"].dependency(search_string="50%")

    assert isinstance(f, SearchFilter)
    assert f.escape_wildcards is True


def test_limit_offset_filter() -> None:
    """Test creating limit_offset filter dependency."""
    config = cast(FilterConfig, {"pagination_type": "limit_offset", "default_limit": 10, "max_limit": 100})
    deps = _create_statement_filters(config)

    assert "limit_offset_filter" in deps
    assert "filters" in deps
    # Test the provider function
    provider_func = deps["limit_offset_filter"].dependency

    f = provider_func(current_page=2, page_size=5)
    assert isinstance(f, LimitOffsetFilter)
    assert f.limit == 5
    assert f.offset == 5


def test_order_by_filter() -> None:
    """Test creating order_by filter dependency."""
    config = cast(FilterConfig, {"sort_field": "name"})
    deps = _create_statement_filters(config)

    assert "order_by_filter" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["order_by_filter"].dependency
    f = provider_func(field_name="name", sort_order="desc")
    assert isinstance(f, OrderByFilter)
    assert f.field_name == "name"
    assert f.sort_order == "desc"


def test_order_by_filter_applies_configured_nulls_placement() -> None:
    """The `sort_nulls` config key pins NULL placement on every generated OrderByFilter."""
    deps = _create_statement_filters({"sort_field": "name", "sort_nulls": "last"})

    provider_func = deps["order_by_filter"].dependency
    f = provider_func(field_name="name", sort_order="asc")

    assert isinstance(f, OrderByFilter)
    assert f.nulls == "last"
    assert _create_statement_filters({"sort_field": "name"})["order_by_filter"].dependency().nulls is None


def test_order_by_filter_uses_scalar_default_from_list_sort_field() -> None:
    """Test list-based sort fields produce a scalar default order field."""
    deps = _create_statement_filters({"sort_field": ["name", "id"]})

    provider_func = deps["order_by_filter"].dependency
    f = provider_func()

    assert isinstance(f, OrderByFilter)
    assert f.field_name == "name"
    f.append_to_statement(select(DITestModel), DITestModel)


def test_order_by_filter_uses_scalar_default_from_set_sort_field() -> None:
    """Test set-based sort fields produce a deterministic scalar default order field."""
    deps = _create_statement_filters({"sort_field": {"name", "id"}})

    provider_func = deps["order_by_filter"].dependency
    f = provider_func()

    assert isinstance(f, OrderByFilter)
    assert f.field_name == "id"
    f.append_to_statement(select(DITestModel), DITestModel)


def test_individual_order_by_dependency_injection_skips_runtime_field_validation() -> None:
    """Test individual Litestar filter dependencies can be injected directly."""

    @get("/", dependencies=create_filter_dependencies({"sort_field": "name"}))
    async def handler(order_by_filter: NamedDependency[OrderByFilter]) -> dict[str, str]:
        return {"field_name": cast(str, order_by_filter.field_name), "sort_order": order_by_filter.sort_order}

    with TestClient(Litestar([handler])) as client:
        response = client.get("/")
        overridden_response = client.get("/?orderBy=id&sortOrder=asc")

    assert response.status_code == 200
    assert response.json() == {"field_name": "name", "sort_order": "desc"}
    assert overridden_response.status_code == 200
    assert overridden_response.json() == {"field_name": "id", "sort_order": "asc"}


def test_litestar_openapi_schema_uses_typed_sort_parameters() -> None:
    """Test sort parameters keep concrete OpenAPI schemas for collection defaults."""
    filter_dependencies = create_filter_dependencies({"sort_field": ["name", "id"], "sort_order": "asc"})

    @get("/test")
    async def handler(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> list[str]:
        return [type(filter_).__name__ for filter_ in filters]

    app = Litestar(
        route_handlers=[handler],
        signature_namespace=signature_namespace_values,
        dependencies=filter_dependencies,
        openapi_config=OpenAPIConfig(title="Test API", version="1.0.0", path="/schema"),
    )

    with TestClient(app) as client:
        response = client.get("/schema/openapi.json")

    assert response.status_code == 200
    parameters = response.json()["paths"]["/test"]["get"]["parameters"]
    order_by_param = next(param for param in parameters if param["name"] == "orderBy")
    sort_order_param = next(param for param in parameters if param["name"] == "sortOrder")

    assert order_by_param["schema"] == {
        "oneOf": [{"type": "string", "default": "name"}, {"type": "null"}],
        "title": "Order by field",
        "default": "name",
    }
    assert sort_order_param["schema"] == {
        "type": ["null", "string"],
        "enum": ["asc", "desc", None],
        "title": "Field to search",
        "default": "asc",
    }


def test_not_in_filter() -> None:
    """Test creating not_in filter dependency."""
    deps = _create_statement_filters({"not_in_fields": ["status"]})

    assert "status_not_in_filter" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["status_not_in_filter"].dependency
    f = provider_func(status_not_in=["pending", "failed"])
    assert isinstance(f, NotInCollectionFilter)
    assert f.field_name == "status"
    assert f.values == ["pending", "failed"]

    # Test with None
    f_none = provider_func(status_not_in=None)
    assert f_none is None


def test_in_filter() -> None:
    """Test creating in filter dependency."""
    deps = _create_statement_filters({"in_fields": ["tag"]})

    assert "tag_in_filter" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["tag_in_filter"].dependency
    f = provider_func(tag_in=["python", "litestar"])
    assert isinstance(f, InCollectionFilter)
    assert f.field_name == "tag"
    assert f.values == ["python", "litestar"]

    # Test with None
    f_none = provider_func(tag_in=None)
    assert f_none is None


def test_boolean_filter() -> None:
    """Test creating boolean filter dependency."""
    deps = _create_statement_filters({"boolean_fields": ["is_featured"]})

    assert "is_featured_boolean_filter" in deps
    assert "filters" in deps

    provider_func = deps["is_featured_boolean_filter"].dependency
    f = provider_func(is_featured_boolean=True)
    assert isinstance(f, BooleanFilter)
    assert f.field_name == "is_featured"
    assert f.value is True

    f_none = provider_func(is_featured_boolean=None)
    assert f_none is None


def test_choices_filter() -> None:
    """Test creating choices filter dependency."""
    deps = _create_statement_filters({"choice_fields": [ChoiceField("status", ("active", "pending"))]})

    assert "status_choices_filter" in deps
    assert "filters" in deps

    provider_func = deps["status_choices_filter"].dependency
    f = provider_func(status_choices=["active", "pending"])
    assert isinstance(f, ChoicesFilter)
    assert f.field_name == "status"
    assert f.values == ["active", "pending"]

    f_none = provider_func(status_choices=None)
    assert f_none is None


def test_choice_filter_openapi_schema_supports_explicit_and_enum_choices() -> None:
    """Test choice filters expose explicit, StrEnum, and IntEnum values in OpenAPI."""
    filter_dependencies = create_filter_dependencies(
        {
            "choice_fields": [
                ("visibility", ("public", "private")),
                ("status", StatusChoice),
                ("priority", PriorityChoice),
            ],
        }
    )

    @get("/items")
    async def handler(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> list[str]:
        return [type(filter_).__name__ for filter_ in filters]

    app = Litestar(
        route_handlers=[handler],
        signature_namespace=signature_namespace_values,
        dependencies=filter_dependencies,
        openapi_config=OpenAPIConfig(title="Test API", version="1.0.0", path="/schema"),
    )

    with TestClient(app) as client:
        response = client.get("/items?visibility=public&status=active&priority=1")
        schema = client.get("/schema/openapi.json").json()

    assert response.status_code == 200
    assert response.json() == ["ChoicesFilter", "ChoicesFilter", "ChoicesFilter"]

    parameters = schema["paths"]["/items"]["get"]["parameters"]
    assert [parameter["name"] for parameter in parameters] == ["visibility", "status", "priority"]
    param_schemas = {parameter["name"]: parameter["schema"] for parameter in parameters}
    components = schema["components"]["schemas"]

    visibility_items = next(schema for schema in param_schemas["visibility"]["oneOf"] if schema.get("type") == "array")[
        "items"
    ]
    assert visibility_items == {"enum": ["public", "private"], "type": "string"}

    status_items = next(schema for schema in param_schemas["status"]["oneOf"] if schema.get("type") == "array")["items"]
    assert status_items == {"$ref": "#/components/schemas/StatusChoice"}
    assert components["StatusChoice"]["enum"] == ["active", "pending"]
    assert components["StatusChoice"]["type"] == "string"

    priority_items = next(schema for schema in param_schemas["priority"]["oneOf"] if schema.get("type") == "array")[
        "items"
    ]
    assert priority_items == {"$ref": "#/components/schemas/PriorityChoice"}
    assert components["PriorityChoice"]["enum"] == [1, 2]
    assert components["PriorityChoice"]["type"] == "integer"


def test_litestar_in_filter_values_are_isolated() -> None:
    """Ensure in-filter query params do not overwrite each other."""
    filter_config: FilterConfig = {"in_fields": ["first_name", "last_name"]}
    filter_dependencies = create_filter_dependencies(filter_config)

    @get("/test")
    def handler(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> dict[str, list[str]]:
        response: dict[str, list[str]] = {}
        for filter_ in filters:
            if isinstance(filter_, InCollectionFilter):
                field_name = str(filter_.field_name)
                response[field_name] = list(filter_.values or [])
        return response

    app = Litestar(route_handlers=[handler], dependencies=filter_dependencies)
    client = TestClient(app)

    response = client.get("/test?firstNameIn=Sezer&lastNameIn=Tasan")
    assert response.status_code == 200
    payload = response.json()
    assert payload["first_name"] == ["Sezer"]
    assert payload["last_name"] == ["Tasan"]


def test_litestar_not_in_filter_values_are_isolated() -> None:
    """Ensure not-in-filter query params do not overwrite each other."""
    filter_config: FilterConfig = {"not_in_fields": ["first_name", "last_name"]}
    filter_dependencies = create_filter_dependencies(filter_config)

    @get("/test")
    def handler(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> dict[str, list[str]]:
        response: dict[str, list[str]] = {}
        for filter_ in filters:
            if isinstance(filter_, NotInCollectionFilter):
                field_name = str(filter_.field_name)
                response[field_name] = list(filter_.values or [])
        return response

    app = Litestar(route_handlers=[handler], dependencies=filter_dependencies, debug=True)
    client = TestClient(app)

    response = client.get("/test?firstNameNotIn=Sezer&lastNameNotIn=Tasan")
    assert response.status_code == 200
    payload = response.json()
    assert payload["first_name"] == ["Sezer"]
    assert payload["last_name"] == ["Tasan"]


def test_filter_cache_separates_page_size_defaults() -> None:
    class BigPages(DependencyDefaults):
        DEFAULT_PAGINATION_SIZE = 100

    config: FilterConfig = {"pagination_type": "limit_offset"}
    default = create_filter_dependencies(config)
    big = create_filter_dependencies(config, BigPages())
    assert default is not big
    key = DEPENDENCY_DEFAULTS.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY
    assert default[key].dependency().limit == 20
    assert big[key].dependency().limit == 100


def test_filter_cache_shares_equal_defaults() -> None:
    config: FilterConfig = {"pagination_type": "limit_offset"}
    assert create_filter_dependencies(config, DependencyDefaults()) is create_filter_dependencies(
        config, DependencyDefaults()
    )


def test_custom_dependency_defaults_are_resolved_in_requests() -> None:
    class CustomDefaults(DependencyDefaults):
        FILTERS_DEPENDENCY_KEY = "custom_filters"
        ID_FILTER_DEPENDENCY_KEY = "custom_ids"
        CREATED_FILTER_DEPENDENCY_KEY = "custom_created"
        UPDATED_FILTER_DEPENDENCY_KEY = "custom_updated"
        LIMIT_OFFSET_FILTER_DEPENDENCY_KEY = "custom_page"
        SEARCH_FILTER_DEPENDENCY_KEY = "custom_search"
        ORDER_BY_FILTER_DEPENDENCY_KEY = "custom_order"
        DEFAULT_PAGINATION_SIZE = 100

    config: FilterConfig = {
        "id_filter": str,
        "created_at": True,
        "updated_at": True,
        "pagination_type": "limit_offset",
        "search": "name",
        "sort_field": "name",
    }
    default_dependencies = create_filter_dependencies(config)
    custom_dependencies = create_filter_dependencies(config, CustomDefaults())
    assert default_dependencies is not custom_dependencies

    @get("/default", dependencies=default_dependencies, sync_to_thread=False)
    def default_handler(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> list[int]:
        return [filter_.limit for filter_ in filters if isinstance(filter_, LimitOffsetFilter)]

    @get("/custom", dependencies=custom_dependencies, sync_to_thread=False)
    def custom_handler(custom_filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> dict[str, Any]:
        return {
            "types": [type(filter_).__name__ for filter_ in custom_filters],
            "fields": [str(filter_.field_name) for filter_ in custom_filters if isinstance(filter_, BeforeAfterFilter)],
            "pages": [
                [filter_.limit, filter_.offset] for filter_ in custom_filters if isinstance(filter_, LimitOffsetFilter)
            ],
            "ids": [
                list(filter_.values or []) for filter_ in custom_filters if isinstance(filter_, InCollectionFilter)
            ],
            "search": [filter_.value for filter_ in custom_filters if isinstance(filter_, SearchFilter)],
            "sort": [filter_.field_name for filter_ in custom_filters if isinstance(filter_, OrderByFilter)],
        }

    with TestClient(Litestar([default_handler, custom_handler])) as client:
        response = client.get("/default")
        assert response.status_code == 200
        assert response.json() == [20]
        response = client.get("/custom", params={"ids": "42", "searchString": "needle", "currentPage": 2})
        assert response.status_code == 200
        assert response.json() == {
            "types": [
                "InCollectionFilter",
                "BeforeAfterFilter",
                "LimitOffsetFilter",
                "BeforeAfterFilter",
                "SearchFilter",
                "OrderByFilter",
            ],
            "fields": ["created_at", "updated_at"],
            "pages": [[100, 100]],
            "ids": [["42"]],
            "search": ["needle"],
            "sort": ["name"],
        }


def test_custom_dependency_defaults() -> None:
    """Test using custom dependency defaults."""

    class CustomDefaults(DependencyDefaults):
        """Custom dependency defaults."""

        LIMIT_OFFSET_FILTER_DEPENDENCY_KEY = "page"
        ID_FILTER_DEPENDENCY_KEY = "ids"
        DEFAULT_PAGINATION_SIZE = 100

    custom_defaults = CustomDefaults()
    config = cast(FilterConfig, {"id_filter": int, "id_field": "custom_id", "pagination_type": "limit_offset"})
    deps = _create_statement_filters(config, custom_defaults)
    assert "ids" in deps
    assert "page" in deps
    assert "filters" in deps
    ids_func = deps["ids"].dependency
    f = ids_func(ids=["1", "2", "3"])
    assert isinstance(f, InCollectionFilter)  # type: ignore
    assert f.field_name == "custom_id"
    assert f.values is not None  # type: ignore
    assert f.values == ["1", "2", "3"]  # type: ignore
    page_func = deps["page"].dependency
    f: LimitOffsetFilter = page_func(current_page=2, page_size=5)  # type: ignore
    assert isinstance(f, LimitOffsetFilter)
    assert f.limit == 5
    assert f.offset == 5


def test_id_filter_aggregation() -> None:
    """Test aggregation with ID filter."""
    config = cast(FilterConfig, {"id_filter": str})
    aggregate_func = _create_filter_aggregate_function(config)

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "id_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=InCollectionFilter)
    result = aggregate_func(id_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_created_at_filter_aggregation() -> None:
    """Test aggregation with created_at filter."""
    aggregate_func = _create_filter_aggregate_function({"created_at": True})

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "created_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=BeforeAfterFilter)
    result = aggregate_func(created_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_updated_at_filter_aggregation() -> None:
    """Test aggregation with updated_at filter."""
    aggregate_func = _create_filter_aggregate_function({"updated_at": True})

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "updated_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=BeforeAfterFilter)
    result = aggregate_func(updated_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_search_filter_aggregation() -> None:
    """Test aggregation with search filter."""
    aggregate_func = _create_filter_aggregate_function({"search": ["name"]})

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "search_filter" in sig.parameters

    # Mock search filter with valid attributes
    mock_filter = MagicMock(spec=SearchFilter)
    mock_filter.field_name = "name"
    mock_filter.value = "test"

    result = aggregate_func(search_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result

    # Test with invalid search filter (None value)
    mock_filter.value = None
    result = aggregate_func(search_filter=mock_filter)
    assert mock_filter not in result


def test_limit_offset_filter_aggregation() -> None:
    """Test aggregation with limit_offset filter."""
    aggregate_func = _create_filter_aggregate_function({"pagination_type": "limit_offset"})

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "limit_offset_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=LimitOffsetFilter)
    result = aggregate_func(limit_offset_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_order_by_filter_aggregation() -> None:
    """Test aggregation with order_by filter."""
    aggregate_func = _create_filter_aggregate_function({"sort_field": "name"})

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "order_by_filter" in sig.parameters

    # Mock order_by filter with valid field_name
    mock_filter = MagicMock(spec=OrderByFilter)
    mock_filter.field_name = "name"

    result = aggregate_func(order_by_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result

    # Test with invalid order_by filter (None field_name)
    mock_filter.field_name = None
    result = aggregate_func(order_by_filter=mock_filter)
    assert mock_filter not in result


def test_not_in_filter_aggregation() -> None:
    """Test aggregation with not_in filter."""
    aggregate_func = _create_filter_aggregate_function({"not_in_fields": ["status"]})
    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "status_not_in_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=NotInCollectionFilter)
    result = aggregate_func(status_not_in_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result

    # Simulate calling without filter (value is None)
    result_none = aggregate_func(status_not_in_filter=None)
    assert mock_filter not in result_none


def test_in_filter_aggregation() -> None:
    """Test aggregation with in filter."""
    config = cast(FilterConfig, {"in_fields": ["tag"]})
    aggregate_func = _create_filter_aggregate_function(config)

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "tag_in_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=InCollectionFilter)
    result = aggregate_func(tag_in_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result

    # Simulate calling without filter (value is None)
    result_none = aggregate_func(tag_in_filter=None)
    assert mock_filter not in result_none


def test_boolean_filter_aggregation() -> None:
    """Test aggregation with boolean filter."""
    aggregate_func = _create_filter_aggregate_function({"boolean_fields": ["is_featured"]})

    sig = inspect.signature(aggregate_func)
    assert "is_featured_boolean_filter" in sig.parameters

    mock_filter = MagicMock(spec=BooleanFilter)
    result = aggregate_func(is_featured_boolean_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result

    result_none = aggregate_func(is_featured_boolean_filter=None)
    assert mock_filter not in result_none


def test_choices_filter_aggregation() -> None:
    """Test aggregation with choices filter."""
    aggregate_func = _create_filter_aggregate_function({"choice_fields": ["status"]})

    sig = inspect.signature(aggregate_func)
    assert "status_choices_filter" in sig.parameters

    mock_filter = MagicMock(spec=ChoicesFilter)
    result = aggregate_func(status_choices_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result

    result_none = aggregate_func(status_choices_filter=None)
    assert mock_filter not in result_none


def test_multiple_filters_aggregation() -> None:
    """Test aggregation with multiple filters."""

    aggregate_func = _create_filter_aggregate_function(
        {
            "id_filter": int,
            "created_at": True,
            "updated_at": True,
            "search": "name",
            "pagination_type": "limit_offset",
            "sort_field": "name",
            "not_in_fields": ["status"],
            "in_fields": ["tag"],
            "boolean_fields": ["is_featured"],
            "choice_fields": ["state"],
        }
    )

    # Check signature has all parameters
    sig = inspect.signature(aggregate_func)
    assert "id_filter" in sig.parameters
    assert "created_filter" in sig.parameters
    assert "updated_filter" in sig.parameters
    assert "search_filter" in sig.parameters
    assert "limit_offset_filter" in sig.parameters
    assert "order_by_filter" in sig.parameters
    assert "status_not_in_filter" in sig.parameters
    assert "tag_in_filter" in sig.parameters
    assert "is_featured_boolean_filter" in sig.parameters
    assert "state_choices_filter" in sig.parameters

    # Simulate calling with multiple filters
    mock_id_filter = MagicMock(spec=InCollectionFilter)
    mock_created_filter = MagicMock(spec=BeforeAfterFilter)
    mock_updated_filter = MagicMock(spec=BeforeAfterFilter)
    mock_search_filter = MagicMock(spec=SearchFilter)
    mock_search_filter.field_name = "name"
    mock_search_filter.value = "test"
    mock_limit_offset = MagicMock(spec=LimitOffsetFilter)
    mock_order_by_filter = MagicMock(spec=OrderByFilter)
    mock_order_by_filter.field_name = "name"
    mock_not_in_filter = MagicMock(spec=NotInCollectionFilter)
    mock_in_filter = MagicMock(spec=InCollectionFilter)
    mock_boolean_filter = MagicMock(spec=BooleanFilter)
    mock_choices_filter = MagicMock(spec=ChoicesFilter)

    result = aggregate_func(
        id_filter=mock_id_filter,
        created_filter=mock_created_filter,
        updated_filter=mock_updated_filter,
        search_filter=mock_search_filter,
        limit_offset_filter=mock_limit_offset,
        order_by_filter=mock_order_by_filter,
        status_not_in_filter=mock_not_in_filter,
        tag_in_filter=mock_in_filter,
        is_featured_boolean_filter=mock_boolean_filter,
        state_choices_filter=mock_choices_filter,
    )

    # Verify all filters are included
    assert len(result) == 10
    assert mock_id_filter in result
    assert mock_created_filter in result
    assert mock_updated_filter in result
    assert mock_search_filter in result
    assert mock_limit_offset in result
    assert mock_order_by_filter in result
    assert mock_not_in_filter in result
    assert mock_in_filter in result
    assert mock_boolean_filter in result
    assert mock_choices_filter in result


@unittest.mock.patch(
    "advanced_alchemy.extensions.litestar.providers.create_filter_dependencies",
    wraps=create_filter_dependencies,  # Call the original function logic
)
def test_litestar_openapi_schema(mock_create_filters: unittest.mock.MagicMock) -> None:
    """Test OpenAPI schema generation for filter dependencies."""

    filter_config = {
        "id_filter": uuid.UUID,  # Example using UUID
        "id_field": "guid",
        "created_at": True,
        "updated_at": True,
        "pagination_type": "limit_offset",
        "pagination_size": 25,
        "search": "name,description",
        "search_ignore_case": True,
        "sort_field": "name",
        "sort_order": "asc",
        "not_in_fields": ["status", "category"],
        "in_fields": ["tag", "region"],
        "boolean_fields": ["is_featured"],
        "choice_fields": ["state"],
    }
    # Call the mocked function, which wraps the original
    filter_dependencies = mock_create_filters(filter_config)

    @get("/test")
    async def test_handler(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> list[str]:
        """Dummy handler to test schema generation."""
        return [type(f).__name__ for f in filters]

    app = Litestar(
        route_handlers=[test_handler],
        signature_namespace=signature_namespace_values,
        dependencies=filter_dependencies,  # Provide all dependencies to the app
        openapi_config=OpenAPIConfig(
            title="Test API", version="1.0.0", use_handler_docstrings=True, path="/schema"
        ),  # Explicitly enable OpenAPI with specific path
    )
    client = TestClient(app)

    # Fetch the OpenAPI schema (using the exact path from Litestar's default config)
    response = client.get("/schema/openapi.json")
    assert response.status_code == 200, (
        f"Failed to get schema, status: {response.status_code}, content: {response.text[:200]}"
    )
    schema = response.json()

    # Find the parameters for the /test endpoint
    path_item = schema.get("paths", {}).get("/test", {}).get("get", {})
    parameters = path_item.get("parameters", [])

    # Assert all expected parameter names are present
    param_names = {p["name"] for p in parameters}
    expected_params = {
        "ids",  # from id_filter, alias based on id_field 'guid' might not be reflected here, Litestar uses parameter name
        "createdBefore",
        "createdAfter",
        "updatedBefore",
        "updatedAfter",
        "currentPage",
        "pageSize",
        "searchString",
        "searchIgnoreCase",
        "orderBy",
        "sortOrder",
        "statusNotIn",
        "categoryNotIn",
        "tagIn",
        "regionIn",
        "isFeatured",
        "state",
    }
    assert param_names == expected_params

    # Check details of specific parameters

    # ids (based on id_filter: uuid.UUID)
    ids_param = next(p for p in parameters if p["name"] == "ids")
    assert ids_param["in"] == "query"
    assert ids_param["required"] is False
    assert "oneOf" in ids_param["schema"]
    assert len(ids_param["schema"]["oneOf"]) == 2
    array_schema = ids_param["schema"]["oneOf"][0]
    assert array_schema["type"] == "array"
    assert array_schema["items"]["type"] == "string"

    # createdBefore (datetime parameter)
    created_before_param = next(p for p in parameters if p["name"] == "createdBefore")
    assert created_before_param["in"] == "query"
    assert created_before_param["required"] is False
    assert "oneOf" in created_before_param["schema"]
    date_schema = created_before_param["schema"]["oneOf"][0]
    assert date_schema["type"] == "string"
    assert date_schema["format"] == "date-time"

    # Check in and not_in parameters
    status_not_in_param = next(p for p in parameters if p["name"] == "statusNotIn")
    assert status_not_in_param["in"] == "query"
    assert status_not_in_param["required"] is False
    assert "oneOf" in status_not_in_param["schema"]

    tag_in_param = next(p for p in parameters if p["name"] == "tagIn")
    assert tag_in_param["in"] == "query"
    assert tag_in_param["required"] is False
    assert "oneOf" in tag_in_param["schema"]

    is_featured_param = next(p for p in parameters if p["name"] == "isFeatured")
    assert is_featured_param["in"] == "query"
    assert is_featured_param["required"] is False
    assert any(
        schema.get("type") == "boolean"
        for schema in is_featured_param["schema"].get("oneOf", [is_featured_param["schema"]])
    )

    state_param = next(p for p in parameters if p["name"] == "state")
    assert state_param["in"] == "query"
    assert state_param["required"] is False
    state_array_schema = next(
        schema
        for schema in state_param["schema"].get("oneOf", [state_param["schema"]])
        if schema.get("type") == "array"
    )
    assert state_array_schema["items"]["type"] == "string"


def test_custom_query_aliases_match_requests_and_openapi() -> None:
    config: FilterConfig = {
        "pagination_type": "limit_offset",
        "search": "name",
        "sort_field": "created_at",
        "in_fields": ["account_id"],
        "boolean_fields": ["is_active"],
        "alias_generator": "snake_case",
    }

    @get("/aliased")
    def handler(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> dict[str, Any]:
        return {type(item).__name__: asdict(item) for item in filters}

    app = Litestar(route_handlers=[handler], dependencies=create_filter_dependencies(config))
    with TestClient(app) as client:
        response = client.get(
            "/aliased",
            params={
                "page_size": 7,
                "current_page": 3,
                "search_string": "needle",
                "order_by": "other_field",
                "account_id_in": "abc",
                "is_active": "false",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["LimitOffsetFilter"] == {"limit": 7, "offset": 14}
        assert data["SearchFilter"]["value"] == "needle"
        assert data["OrderByFilter"]["field_name"] == "other_field"
        assert data["InCollectionFilter"]["values"] == ["abc"]
        assert data["BooleanFilter"]["value"] is False
        schema = client.get("/schema/openapi.json").json()
    names = {item["name"] for item in schema["paths"]["/aliased"]["get"]["parameters"]}
    assert names == {
        "page_size",
        "current_page",
        "search_string",
        "search_ignore_case",
        "order_by",
        "sort_order",
        "account_id_in",
        "is_active",
    }


def test_dependency_defaults_prefix() -> None:
    defaults = DependencyDefaults(prefix="service")
    assert defaults.prefix == "service"
    assert defaults.FILTERS_DEPENDENCY_KEY == "service_filters"
    assert defaults.CREATED_FILTER_DEPENDENCY_KEY == "service_created_filter"
    assert defaults.ID_FILTER_DEPENDENCY_KEY == "service_id_filter"
    assert defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY == "service_limit_offset_filter"
    assert defaults.UPDATED_FILTER_DEPENDENCY_KEY == "service_updated_filter"
    assert defaults.ORDER_BY_FILTER_DEPENDENCY_KEY == "service_order_by_filter"
    assert defaults.SEARCH_FILTER_DEPENDENCY_KEY == "service_search_filter"
    assert defaults.DEFAULT_PAGINATION_SIZE == 20

    defaults_with_trailing = DependencyDefaults(prefix="service_")
    assert defaults_with_trailing.FILTERS_DEPENDENCY_KEY == "service_filters"

    defaults_custom = DependencyDefaults(prefix="user", search_filter_key="custom_search")
    assert defaults_custom.SEARCH_FILTER_DEPENDENCY_KEY == "user_custom_search"

    class UsersDefaults(DependencyDefaults):
        prefix = "users"

    subclass_defaults = UsersDefaults()
    assert subclass_defaults.prefix == "users"
    assert subclass_defaults.FILTERS_DEPENDENCY_KEY == "users_filters"
    assert subclass_defaults.CREATED_FILTER_DEPENDENCY_KEY == "users_created_filter"
    assert subclass_defaults.ID_FILTER_DEPENDENCY_KEY == "users_id_filter"
    assert subclass_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY == "users_limit_offset_filter"
    assert subclass_defaults.UPDATED_FILTER_DEPENDENCY_KEY == "users_updated_filter"
    assert subclass_defaults.ORDER_BY_FILTER_DEPENDENCY_KEY == "users_order_by_filter"
    assert subclass_defaults.SEARCH_FILTER_DEPENDENCY_KEY == "users_search_filter"

    underscore_defaults = DependencyDefaults(prefix="_")
    assert underscore_defaults.FILTERS_DEPENDENCY_KEY == "filters"


def test_create_service_dependencies_scoped_filters() -> None:
    with patch("advanced_alchemy.extensions.litestar.providers.create_service_provider") as mock_create_provider:
        mock_create_provider.return_value = lambda: "user_service"
        deps = create_service_dependencies(
            MockSyncService,
            key="user_service",
            scoped_filters=True,
            filters=cast(
                FilterConfig,
                {
                    "id_filter": True,
                    "search": "name",
                    "pagination_type": "limit_offset",
                    "in_fields": ["status"],
                },
            ),
        )
        assert "user_service" in deps
        assert "user_service_filters" in deps
        assert "user_service_id_filter" in deps
        assert "user_service_search_filter" in deps
        assert "user_service_limit_offset_filter" in deps
        assert "user_service_status_in_filter" in deps


def test_create_service_dependencies_merge_collision_prevented() -> None:
    with patch("advanced_alchemy.extensions.litestar.providers.create_service_provider") as mock_create_provider:
        mock_create_provider.side_effect = [lambda: "user_service", lambda: "course_service"]
        user_deps = create_service_dependencies(
            MockSyncService,
            key="user_service",
            scoped_filters=True,
            filters=cast(
                FilterConfig,
                {"search": "name", "pagination_type": "limit_offset", "id_filter": True},
            ),
        )
        course_deps = create_service_dependencies(
            MockSyncService,
            key="course_service",
            scoped_filters=True,
            filters=cast(
                FilterConfig,
                {"search": "title", "pagination_type": "limit_offset", "id_filter": True},
            ),
        )

        merged_deps = {**user_deps, **course_deps}
        assert len(merged_deps) == len(user_deps) + len(course_deps)
        assert "user_service_filters" in merged_deps
        assert "course_service_filters" in merged_deps
        assert "user_service_search_filter" in merged_deps
        assert "course_service_search_filter" in merged_deps
        assert "user_service_limit_offset_filter" in merged_deps
        assert "course_service_limit_offset_filter" in merged_deps

        @get("/combined")
        def handler(
            user_service_filters: NamedDependency[SkipValidation[list[FilterTypes]]],
            course_service_filters: NamedDependency[SkipValidation[list[FilterTypes]]],
        ) -> dict[str, Any]:
            return {
                "user_filters": {type(f).__name__: asdict(f) for f in user_service_filters},
                "course_filters": {type(f).__name__: asdict(f) for f in course_service_filters},
            }

        app = Litestar(route_handlers=[handler], dependencies=merged_deps, debug=True)
        with TestClient(app) as client:
            resp = client.get(
                "/combined",
                params={
                    "userServiceSearchString": "alice",
                    "userServicePageSize": 5,
                    "userServiceCurrentPage": 2,
                    "courseServiceSearchString": "math",
                    "courseServicePageSize": 12,
                    "courseServiceCurrentPage": 3,
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["user_filters"]["SearchFilter"]["value"] == "alice"
            assert data["user_filters"]["LimitOffsetFilter"] == {"limit": 5, "offset": 5}
            assert data["course_filters"]["SearchFilter"]["value"] == "math"
            assert data["course_filters"]["LimitOffsetFilter"] == {"limit": 12, "offset": 24}


def test_scoped_filters_prefix_subclass_and_pagination_isolation() -> None:
    class UsersDefaults(DependencyDefaults):
        prefix = "users"

    class RolesDefaults(DependencyDefaults):
        prefix = "roles"

    user_filters_deps = create_filter_dependencies(
        cast(FilterConfig, {"pagination_type": "limit_offset"}),
        dep_defaults=UsersDefaults(),
    )
    role_filters_deps = create_filter_dependencies(
        cast(FilterConfig, {"pagination_type": "limit_offset"}),
        dep_defaults=RolesDefaults(),
    )

    @get("/scoped-pages")
    def handler(
        users_filters: NamedDependency[SkipValidation[list[FilterTypes]]],
        roles_filters: NamedDependency[SkipValidation[list[FilterTypes]]],
    ) -> dict[str, Any]:
        return {
            "users": {type(f).__name__: asdict(f) for f in users_filters},
            "roles": {type(f).__name__: asdict(f) for f in roles_filters},
        }

    app = Litestar(route_handlers=[handler], dependencies={**user_filters_deps, **role_filters_deps}, debug=True)
    with TestClient(app) as client:
        resp = client.get("/scoped-pages", params={"usersCurrentPage": 2, "rolesCurrentPage": 5})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["users"]["LimitOffsetFilter"] == {"limit": 20, "offset": 20}
        assert data["roles"]["LimitOffsetFilter"] == {"limit": 20, "offset": 80}


def test_scoped_filters_snake_case_query_aliases() -> None:
    aliases = resolve_filter_aliases(
        cast(FilterConfig, {"pagination_type": "limit_offset", "search": "name", "alias_generator": "snake_case"}),
        prefix="users",
    )
    assert aliases == {
        "current_page": "users_current_page",
        "page_size": "users_page_size",
        "search_string": "users_search_string",
        "search_ignore_case": "users_search_ignore_case",
    }


class _LitestarPlainHelper:
    """Plain helper service whose async mode cannot be inferred without config."""

    def __init__(self, session: Any) -> None:
        self.session = session


class _LitestarUndeterminedGroup(ServiceGroup):
    """ServiceGroup composed solely of plain classes without SQLAlchemy base classes."""

    helper: _LitestarPlainHelper


class _LitestarPairGroup(ServiceGroup):
    """ServiceGroup with two async services for scoped filter dependency coverage."""

    primary: MockAsyncService
    secondary: MockAsyncService


def test_dependency_defaults_pagination_override_and_prefix_cloning() -> None:
    defaults = DependencyDefaults(filters_key="custom_filters", default_pagination_size=25)
    assert defaults.DEFAULT_PAGINATION_SIZE == 25
    cloned = _with_dep_defaults_prefix(defaults, "grp")
    assert cloned.FILTERS_DEPENDENCY_KEY == "grp_custom_filters"
    assert cloned.DEFAULT_PAGINATION_SIZE == 25


def test_is_async_provider_target_for_undetermined_group() -> None:
    sync_cfg = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
    assert _is_async_provider_target(_LitestarUndeterminedGroup, sync_cfg) is False
    assert _is_async_provider_target(_LitestarUndeterminedGroup, None) is True


@pytest.mark.parametrize(
    ("dep_defaults", "scoped_filters", "expected_filter_key"),
    [
        (None, True, "items_filters"),
        (DependencyDefaults(filters_key="q"), True, "items_q"),
        (DependencyDefaults(prefix="custom"), True, "custom_filters"),
    ],
)
def test_create_service_dependencies_single_service_prefix_resolution(
    dep_defaults: DependencyDefaults | None,
    scoped_filters: bool,
    expected_filter_key: str,
) -> None:
    deps = create_service_dependencies(
        MockAsyncService,
        key="items",
        filters=cast(FilterConfig, {"id_filter": int}),
        dep_defaults=dep_defaults,
        scoped_filters=scoped_filters,
    )
    assert "items" in deps
    assert expected_filter_key in deps


@pytest.mark.parametrize(
    ("dep_defaults", "scoped_filters", "expected_filter_key"),
    [
        (DependencyDefaults(prefix="grp"), False, "grp_primary_filters"),
        (None, True, "auth_primary_filters"),
    ],
)
def test_create_service_dependencies_group_prefix_and_empty_branch(
    dep_defaults: DependencyDefaults | None,
    scoped_filters: bool,
    expected_filter_key: str,
) -> None:
    deps = create_service_dependencies(
        _LitestarPairGroup,
        key="auth",
        filters={"primary": cast(FilterConfig, {"id_filter": int}), "secondary": {}},
        dep_defaults=dep_defaults,
        scoped_filters=scoped_filters,
    )
    assert "auth" in deps
    assert expected_filter_key in deps
    assert "auth_secondary_filters" not in deps


class _LitestarGridBase(DeclarativeBase):
    """Isolated base for Litestar field filtering tests."""


class _LitestarGridAuthor(_LitestarGridBase):
    """Author model for Litestar field filter tests."""

    __tablename__ = "litestar_grid_author"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    mentor_id: Mapped[int | None] = mapped_column(ForeignKey("litestar_grid_author.id"), nullable=True)
    mentor: Mapped[_LitestarGridAuthor | None] = relationship(remote_side=[id])
    articles: Mapped[list[_LitestarGridArticle]] = relationship(back_populates="author")


class _LitestarGridArticle(_LitestarGridBase):
    """Article model for Litestar field filter tests."""

    __tablename__ = "litestar_grid_article"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150))
    rel_author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    views: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("litestar_grid_author.id"))
    author: Mapped[_LitestarGridAuthor] = relationship(back_populates="articles")
    author_mentor: Mapped[_LitestarGridAuthor] = relationship(viewonly=True, foreign_keys=[author_id])


class _LitestarGridArticleRepo(SQLAlchemyAsyncRepository[_LitestarGridArticle]):
    model_type = _LitestarGridArticle


class _LitestarGridArticleService(SQLAlchemyAsyncRepositoryService[_LitestarGridArticle, _LitestarGridArticleRepo]):
    repository_type = _LitestarGridArticleRepo


def _serialize_grid_filters(filters: Sequence[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in filters:
        if isinstance(item, RelationshipFilter):
            serialized.append(
                {
                    "type": "RelationshipFilter",
                    "relationship": item.relationship,
                    "filters": _serialize_grid_filters(item.filters),
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
def test_litestar_field_filter_group_names_do_not_collide(
    field_spec: FilterFieldsSpec, parameters: dict[str, str], expected: list[dict[str, Any]]
) -> None:
    """Direct columns and distinct relationship paths retain their public parameters."""
    config: FilterConfig = {"filter_fields": field_spec}

    @get("/articles")
    async def list_articles(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> list[dict[str, Any]]:
        return _serialize_grid_filters(filters)

    deps = create_service_dependencies(_LitestarGridArticleService, key="articles", filters=config)
    app = Litestar(route_handlers=[list_articles], dependencies=deps, signature_namespace=signature_namespace_values)
    with TestClient(app) as client:
        response = client.get("/articles", params=parameters)
        assert response.status_code == 200, response.text
        assert response.json() == expected


def test_litestar_field_filter_fields_and_sort_fields_openapi_and_parsing() -> None:
    """Verify grouped relationship filters, repeatable orderBy, 400 validation, and OpenAPI schema."""
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

    @get("/articles")
    async def list_articles(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> list[dict[str, Any]]:
        return _serialize_grid_filters(filters)

    deps = create_service_dependencies(_LitestarGridArticleService, key="articles", filters=config)
    app = Litestar(
        route_handlers=[list_articles],
        dependencies=deps,
        openapi_config=OpenAPIConfig(title="Grid API", version="1.0.0"),
        signature_namespace=signature_namespace_values,
        debug=True,
    )

    schema = app.openapi_schema.to_schema()
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
    order_schema = param_map["orderBy"]["schema"]
    order_variants = order_schema.get("oneOf") or order_schema.get("anyOf") or [order_schema]
    assert any(variant.get("type") == "array" for variant in order_variants)

    with TestClient(app) as client:
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
        assert invalid_sort.status_code == 400


def test_litestar_field_filters_snake_case_scoped_and_explicit_model() -> None:
    """Verify snake_case query names, scoped prefixes, and explicit create_filter_dependencies model binding."""
    config: FilterConfig = {
        "filter_fields": {"title": {"contains"}, "author.name": {"eq"}},
        "sort_fields": ["title", "author.name"],
        "alias_generator": "snake_case",
    }
    aliases = resolve_filter_aliases(config, prefix="posts", model=_LitestarGridArticle)
    assert aliases == {
        "title_contains": "posts_title_contains",
        "author_name_eq": "posts_author_name_eq",
        "order_by": "posts_order_by",
        "sort_order": "posts_sort_order",
    }

    deps = create_filter_dependencies(config, model=_LitestarGridArticle)

    @get("/explicit")
    async def list_explicit(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> list[dict[str, Any]]:
        return _serialize_grid_filters(filters)

    app = Litestar(route_handlers=[list_explicit], dependencies=deps, debug=True)
    with TestClient(app) as client:
        resp = client.get(
            "/explicit",
            params=[("title_contains", "alc"), ("author_name_eq", "Ada"), ("order_by", "-author.name")],
        )
        assert resp.status_code == 200, resp.text
        parsed = resp.json()
        assert {"type": "SearchFilter", "field_name": "title", "value": "alc", "ignore_case": True} in parsed
        assert {
            "type": "RelationshipFilter",
            "relationship": "author",
            "filters": [{"type": "ComparisonFilter", "field_name": "name", "operator": "eq", "value": "Ada"}],
        } in parsed
        assert {"type": "OrderByFilter", "field_name": "author.name", "sort_order": "desc"} in parsed


def test_litestar_field_e2e_async_sqlite_prototype() -> None:
    """Exercise full HTTP -> Litestar DI -> SQLAlchemyAsyncRepositoryService -> SQLite grid query flow."""
    db_config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")

    async def seed_database(app: Litestar) -> None:
        engine = db_config.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(_LitestarGridBase.metadata.create_all)
        async with db_config.get_session() as session:
            ada = _LitestarGridAuthor(name="Ada")
            cody = _LitestarGridAuthor(name="Cody")
            session.add_all(
                [
                    _LitestarGridArticle(
                        title="SQLAlchemy Basics",
                        views=150,
                        status="draft",
                        published_at=None,
                        author=cody,
                    ),
                    _LitestarGridArticle(
                        title="Advanced SQL Queries",
                        views=420,
                        status="draft",
                        published_at=datetime(2026, 1, 5),
                        author=cody,
                    ),
                    _LitestarGridArticle(
                        title="SQL Indexing Deep Dive",
                        views=900,
                        status="draft",
                        published_at=None,
                        author=ada,
                    ),
                    _LitestarGridArticle(
                        title="Python Packaging",
                        views=300,
                        status="published",
                        published_at=datetime(2026, 2, 1),
                        author=cody,
                    ),
                ]
            )
            await session.commit()

    @get("/grid")
    async def list_grid(
        articles_service: NamedDependency[_LitestarGridArticleService],
        filters: NamedDependency[SkipValidation[list[FilterTypes]]],
    ) -> dict[str, Any]:
        rows, total = await articles_service.get_many_and_count(*filters)
        return {
            "total": total,
            "items": [{"title": row.title, "views": row.views, "status": row.status} for row in rows],
        }

    deps = create_service_dependencies(
        _LitestarGridArticleService,
        key="articles_service",
        filters={
            "filter_fields": {
                "title": {"contains", "eq"},
                "views": {"ge", "le"},
                "status": {"in"},
                "published_at": {"is_null"},
                "author.name": {"contains", "eq"},
            },
            "sort_fields": ["title", "views", "author.name"],
            "pagination_type": "limit_offset",
            "pagination_size": 10,
        },
    )
    app = Litestar(
        route_handlers=[list_grid],
        dependencies=deps,
        plugins=[SQLAlchemyPlugin(config=db_config)],
        on_startup=[seed_database],
        debug=True,
    )
    with TestClient(app) as client:
        filtered = client.get(
            "/grid",
            params=[
                ("titleContains", "sql"),
                ("viewsGe", "100"),
                ("viewsLe", "500"),
                ("statusIn", "draft"),
                ("authorNameContains", "cody"),
                ("orderBy", "-views"),
                ("currentPage", "1"),
                ("pageSize", "1"),
            ],
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json() == {
            "total": 2,
            "items": [{"title": "Advanced SQL Queries", "views": 420, "status": "draft"}],
        }

        rel_sorted = client.get(
            "/grid",
            params=[("publishedAtIsNull", "true"), ("orderBy", "author.name")],
        )
        assert rel_sorted.status_code == 200, rel_sorted.text
        assert rel_sorted.json() == {
            "total": 2,
            "items": [
                {"title": "SQL Indexing Deep Dive", "views": 900, "status": "draft"},
                {"title": "SQLAlchemy Basics", "views": 150, "status": "draft"},
            ],
        }


def test_litestar_pagination_max_size_validation_and_openapi() -> None:
    deps = create_filter_dependencies(
        {"pagination_type": "limit_offset", "pagination_max_size": 15},
        DependencyDefaults(default_pagination_size=25),
    )

    @get("/items", sync_to_thread=False)
    def list_items(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> dict[str, int]:
        limit_offset = next(f for f in filters if isinstance(f, LimitOffsetFilter))
        return {"limit": limit_offset.limit, "offset": limit_offset.offset}

    app = Litestar(
        route_handlers=[list_items],
        dependencies=deps,
        signature_namespace=signature_namespace_values,
        openapi_config=OpenAPIConfig(title="Test", version="1.0.0", path="/schema"),
    )
    with TestClient(app) as client:
        assert client.get("/items").json() == {"limit": 15, "offset": 0}
        assert client.get("/items", params={"pageSize": "15"}).json() == {"limit": 15, "offset": 0}
        assert client.get("/items", params={"pageSize": "16"}).status_code == 400
        params = {
            param["name"]: param["schema"]
            for param in client.get("/schema/openapi.json").json()["paths"]["/items"]["get"]["parameters"]
        }
        assert params["pageSize"]["minimum"] == 1
        assert params["pageSize"]["maximum"] == 15

    with pytest.raises(ImproperConfigurationError, match="cannot exceed"):
        create_filter_dependencies(
            {"pagination_type": "limit_offset", "pagination_size": 30, "pagination_max_size": 15}
        )
    with pytest.raises(ImproperConfigurationError, match="pagination_max_size"):
        create_filter_dependencies({"pagination_type": "limit_offset", "pagination_max_size": 0})

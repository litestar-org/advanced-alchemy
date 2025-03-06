"""Tests for the DI module."""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

from litestar.di import Provide
from sqlalchemy import FromClause, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column

from advanced_alchemy.extensions.litestar.providers import (
    DEPENDENCY_DEFAULTS,
    DependencyCache,
    DependencyDefaults,
    FilterConfig,
    SingletonMeta,
    _create_filter_aggregate_function,  # pyright: ignore[reportPrivateUsage]
    _create_statement_filters,  # pyright: ignore[reportPrivateUsage]
    create_filter_dependencies,
    create_service_dependencies,
    create_service_provider,
    dep_cache,
)
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    LimitOffset,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.service import (
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.types.identity import BigIntIdentity
from tests.helpers import anext_


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


class TestSyncService(SQLAlchemySyncRepositoryService[DITestModel]):
    """Test sync service class."""

    class Repo(SQLAlchemySyncRepository[DITestModel]):
        """Test repo class."""

        model_type = DITestModel

    repository_type = Repo


class TestAsyncService(SQLAlchemyAsyncRepositoryService[DITestModel]):
    """Test async service class."""

    class Repo(SQLAlchemyAsyncRepository[DITestModel]):
        """Test repo class."""

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
    provider = create_service_provider(TestSyncService)

    # Ensure the provider is callable
    assert callable(provider)
    svc = next(provider(db_session=MagicMock()))
    assert isinstance(svc, TestSyncService)


async def test_create_async_service_provider() -> None:
    """Test creating an async service provider."""
    provider = create_service_provider(TestAsyncService)

    # Ensure the provider is callable
    assert callable(provider)
    svc = await anext_(provider(db_session=MagicMock()))
    assert isinstance(svc, TestAsyncService)


def test_create_async_service_dependencies() -> None:
    """Test creating async service dependencies."""
    with patch("advanced_alchemy.extensions.litestar.providers.create_service_provider") as mock_create_provider:
        mock_create_provider.return_value = lambda: "async_service"

        deps = create_service_dependencies(
            TestAsyncService,
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
            TestSyncService,
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
                TestSyncService,
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
                mock_create.assert_called_once_with(config, DEPENDENCY_DEFAULTS)

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
    assert isinstance(f, CollectionFilter)
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
    f = provider_func(before=before, after=later)
    assert isinstance(f, BeforeAfter)
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
    f = provider_func(before=datetime.now(), after=datetime.now())
    assert isinstance(f, BeforeAfter)
    assert f.field_name == "updated_at"


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


def test_limit_offset_filter() -> None:
    """Test creating limit_offset filter dependency."""
    config = cast(FilterConfig, {"pagination_type": "limit_offset", "default_limit": 10, "max_limit": 100})
    deps = _create_statement_filters(config)

    assert "limit_offset" in deps
    assert "filters" in deps
    # Test the provider function
    provider_func = deps["limit_offset"].dependency

    f = provider_func(current_page=2, page_size=5)
    assert isinstance(f, LimitOffset)
    assert f.limit == 5
    assert f.offset == 5


def test_order_by_filter() -> None:
    """Test creating order_by filter dependency."""
    config = cast(FilterConfig, {"sort_field": "name"})
    deps = _create_statement_filters(config)

    assert "order_by" in deps
    assert "filters" in deps

    # Test the provider function
    provider_func = deps["order_by"].dependency
    f = provider_func(field_name="name", sort_order="desc")
    assert isinstance(f, OrderBy)
    assert f.field_name == "name"
    assert f.sort_order == "desc"


def test_custom_dependency_defaults() -> None:
    """Test using custom dependency defaults."""

    class CustomDefaults(DependencyDefaults):
        """Custom dependency defaults."""

        LIMIT_OFFSET_DEPENDENCY_KEY = "page"
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
    assert isinstance(f, CollectionFilter)  # type: ignore
    assert f.field_name == "custom_id"
    assert f.values is not None  # type: ignore
    assert f.values == ["1", "2", "3"]  # type: ignore
    page_func = deps["page"].dependency
    f: LimitOffset = page_func(current_page=2, page_size=5)  # type: ignore
    assert isinstance(f, LimitOffset)
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
    mock_filter = MagicMock(spec=CollectionFilter)
    result = aggregate_func(id_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_created_at_filter_aggregation() -> None:
    """Test aggregation with created_at filter."""
    config = cast(FilterConfig, {"created_at": "created_at"})
    aggregate_func = _create_filter_aggregate_function(config)

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "created_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=BeforeAfter)
    result = aggregate_func(created_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_updated_at_filter_aggregation() -> None:
    """Test aggregation with updated_at filter."""
    config = cast(FilterConfig, {"updated_at": "updated_at"})
    aggregate_func = _create_filter_aggregate_function(config)

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "updated_filter" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=BeforeAfter)
    result = aggregate_func(updated_filter=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_search_filter_aggregation() -> None:
    """Test aggregation with search filter."""
    config = cast(FilterConfig, {"search": ["name"]})
    aggregate_func = _create_filter_aggregate_function(config)

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
    config = cast(FilterConfig, {"pagination_type": "limit_offset"})
    aggregate_func = _create_filter_aggregate_function(config)

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "limit_offset" in sig.parameters

    # Simulate calling with filter
    mock_filter = MagicMock(spec=LimitOffset)
    result = aggregate_func(limit_offset=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result


def test_order_by_filter_aggregation() -> None:
    """Test aggregation with order_by filter."""
    config = cast(FilterConfig, {"sort_field": "name"})
    aggregate_func = _create_filter_aggregate_function(config)

    # Check signature
    sig = inspect.signature(aggregate_func)
    assert "order_by" in sig.parameters

    # Mock order_by filter with valid field_name
    mock_filter = MagicMock(spec=OrderBy)
    mock_filter.field_name = "name"

    result = aggregate_func(order_by=mock_filter)

    assert isinstance(result, list)
    assert mock_filter in result

    # Test with invalid order_by filter (None field_name)
    mock_filter.field_name = None
    result = aggregate_func(order_by=mock_filter)
    assert mock_filter not in result


def test_multiple_filters_aggregation() -> None:
    """Test aggregation with multiple filters."""
    config = cast(
        FilterConfig,
        {
            "id_filter": int,
            "created_at": True,
            "updated_at": True,
            "search": "name",
            "pagination_type": "limit_offset",
            "sort_field": "name",
        },
    )

    aggregate_func = _create_filter_aggregate_function(config)

    # Check signature has all parameters
    sig = inspect.signature(aggregate_func)
    assert "id_filter" in sig.parameters
    assert "created_filter" in sig.parameters
    assert "updated_filter" in sig.parameters
    assert "search_filter" in sig.parameters
    assert "limit_offset" in sig.parameters
    assert "order_by" in sig.parameters

    # Simulate calling with multiple filters
    mock_id_filter = MagicMock(spec=CollectionFilter)
    mock_created_filter = MagicMock(spec=BeforeAfter)
    mock_updated_filter = MagicMock(spec=BeforeAfter)
    mock_search_filter = MagicMock(spec=SearchFilter)
    mock_search_filter.field_name = "name"
    mock_search_filter.value = "test"
    mock_limit_offset = MagicMock(spec=LimitOffset)
    mock_order_by = MagicMock(spec=OrderBy)
    mock_order_by.field_name = "name"

    result = aggregate_func(
        id_filter=mock_id_filter,
        created_filter=mock_created_filter,
        updated_filter=mock_updated_filter,
        search_filter=mock_search_filter,
        limit_offset=mock_limit_offset,
        order_by=mock_order_by,
    )

    # Verify all filters are included
    assert len(result) == 6
    assert mock_id_filter in result
    assert mock_created_filter in result
    assert mock_updated_filter in result
    assert mock_search_filter in result
    assert mock_limit_offset in result
    assert mock_order_by in result

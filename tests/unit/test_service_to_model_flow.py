"""Unit tests for service model conversion flow.

These tests verify that update input types are routed through to_model(data, "update")
and the update lifecycle hook before persistence. They also cover service-level
input normalization before repository delegation.
"""

from __future__ import annotations

import datetime as dt
import warnings
from typing import Any, Generic, Optional, TypeVar, Union, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import String, create_engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, Session, mapped_column
from sqlalchemy.pool import StaticPool

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.exceptions import IntegrityError
from advanced_alchemy.repository import (
    SQLAlchemyAsyncRepository,
    SQLAlchemyAsyncSlugRepository,
    SQLAlchemySyncRepository,
    SQLAlchemySyncSlugRepository,
)
from advanced_alchemy.repository._util import get_primary_key_info, supports_partial_hydration
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository
from advanced_alchemy.repository.typing import PrimaryKeyType
from advanced_alchemy.service import SchemaDumpConfig, SQLAlchemyAsyncRepositoryService, SQLAlchemySyncRepositoryService
from advanced_alchemy.utils.serialization import ATTRS_INSTALLED, MSGSPEC_INSTALLED, PYDANTIC_INSTALLED, ModelDictT
from tests.helpers import maybe_async

pytestmark = [pytest.mark.unit]


class MockModel(UUIDAuditBase):
    """Minimal SQLAlchemy model for service flow tests."""

    name: Mapped[str] = mapped_column(String(length=100))  # pyright: ignore[reportUninitializedInstanceVariable]
    dob: Mapped[Optional[dt.date]] = mapped_column(nullable=True)  # pyright: ignore[reportUninitializedInstanceVariable]


class MockRepository(SQLAlchemyAsyncRepository[MockModel]):
    """Mock repository for testing."""

    model_type = MockModel

    def __init__(self) -> None:
        # Don't call super().__init__ to avoid needing session
        self.model_type = MockModel
        self.id_attribute = "id"
        # Initialize PK info for composite PK support
        self._pk_columns, self._pk_attr_names = get_primary_key_info(MockModel)


class MockSyncRepository(SQLAlchemySyncRepository[MockModel]):
    """Mock sync repository for testing."""

    model_type = MockModel

    def __init__(self) -> None:
        # Don't call super().__init__ to avoid needing session
        self.model_type = MockModel
        self.id_attribute = "id"
        # Initialize PK info for composite PK support
        self._pk_columns, self._pk_attr_names = get_primary_key_info(MockModel)


class TrackingService(SQLAlchemyAsyncRepositoryService[MockModel, MockRepository]):
    """Service that tracks to_model() calls for testing."""

    repository_type = MockRepository

    def __init__(self) -> None:
        self._repository = MockRepository()
        mock_model = MockModel()
        mock_model.id = "existing-id"  # type: ignore[assignment]
        mock_model.name = "existing"
        mock_model.dob = None  # type: ignore[assignment]
        self._repository.get = AsyncMock(return_value=mock_model)  # type: ignore[method-assign]
        self._repository.update = AsyncMock(side_effect=lambda data, **kwargs: data)  # type: ignore[method-assign]

        self.to_model_calls: list[tuple[Any, Optional[str]]] = []
        self.to_model_on_update_calls: list[Any] = []

    @property
    def repository(self) -> MockRepository:
        """Return mock repository."""
        return self._repository

    async def to_model(
        self,
        data: ModelDictT[MockModel],
        operation: Optional[str] = None,
        schema_dump_config: Optional[SchemaDumpConfig] = None,
    ) -> MockModel:
        """Track to_model calls."""
        self.to_model_calls.append((data, operation))
        return await super().to_model(data, operation, schema_dump_config=schema_dump_config)

    async def to_model_on_update(self, data: ModelDictT[MockModel]) -> ModelDictT[MockModel]:
        """Track to_model_on_update calls."""
        self.to_model_on_update_calls.append(data)
        return await super().to_model_on_update(data)


class TrackingSyncService(SQLAlchemySyncRepositoryService[MockModel, MockSyncRepository]):
    """Sync service that tracks to_model() calls for testing."""

    repository_type = MockSyncRepository

    def __init__(self) -> None:
        self._repository = MockSyncRepository()
        mock_model = MockModel()
        mock_model.id = "existing-id"  # type: ignore[assignment]
        mock_model.name = "existing"
        mock_model.dob = None  # type: ignore[assignment]
        self._repository.get = MagicMock(return_value=mock_model)  # type: ignore[method-assign]
        self._repository.update = MagicMock(side_effect=lambda data, **kwargs: data)  # type: ignore[method-assign]

        self.to_model_calls: list[tuple[Any, Optional[str]]] = []
        self.to_model_on_update_calls: list[Any] = []

    @property
    def repository(self) -> MockSyncRepository:
        """Return mock repository."""
        return self._repository

    def to_model(
        self,
        data: ModelDictT[MockModel],
        operation: Optional[str] = None,
        schema_dump_config: Optional[SchemaDumpConfig] = None,
    ) -> MockModel:
        """Track to_model calls."""
        self.to_model_calls.append((data, operation))
        return super().to_model(data, operation, schema_dump_config=schema_dump_config)

    def to_model_on_update(self, data: ModelDictT[MockModel]) -> ModelDictT[MockModel]:
        """Track to_model_on_update calls."""
        self.to_model_on_update_calls.append(data)
        return super().to_model_on_update(data)


# Tests for async service


@pytest.mark.asyncio
async def test_delete_many_passes_id_only_input_through_without_copying() -> None:
    """Id-only delete_many() input should keep the existing bulk-delete fast path."""
    service = TrackingService()
    captured: dict[str, Any] = {}

    async def delete_many(item_ids: list[Any], **_: Any) -> list[MockModel]:
        captured["item_ids"] = item_ids
        return []

    service.repository.delete_many = AsyncMock(side_effect=delete_many)  # type: ignore[method-assign]

    item_ids: list[PrimaryKeyType] = ["first-id", "second-id"]
    await service.delete_many(item_ids)

    assert captured["item_ids"] is item_ids


@pytest.mark.asyncio
async def test_update_dict_calls_to_model_with_operation() -> None:
    """Test that update() with dict data calls to_model(data, 'update')."""
    service = TrackingService()

    # Update with dict data and item_id
    await service.update({"name": "Updated Name"}, item_id="test-id")

    # Verify to_model was called with operation="update"
    assert len(service.to_model_calls) == 1
    data, operation = service.to_model_calls[0]
    assert operation == "update"
    assert data == {"name": "Updated Name"}

    # Verify to_model_on_update was also called (via operation_map)
    assert len(service.to_model_on_update_calls) == 1


@pytest.mark.asyncio
async def test_update_model_instance_calls_to_model_with_operation() -> None:
    """Test that update() with model instance calls to_model(data, 'update')."""
    service = TrackingService()

    # Update with model instance
    model = MockModel()
    model.id = "test-id"  # type: ignore[assignment]
    model.name = "Updated Name"
    await service.update(model)

    # Verify to_model was called with operation="update"
    assert len(service.to_model_calls) == 1
    data, operation = service.to_model_calls[0]
    assert operation == "update"
    assert data is model


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
@pytest.mark.asyncio
async def test_update_pydantic_calls_to_model_with_operation() -> None:
    """Test that update() with Pydantic data calls to_model(data, 'update')."""
    from pydantic import BaseModel

    class AuthorSchema(BaseModel):
        name: str

    service = TrackingService()

    # Update with Pydantic model
    schema = AuthorSchema(name="Updated Name")
    await service.update(schema, item_id="test-id")

    # Verify to_model was called with operation="update"
    assert len(service.to_model_calls) == 1
    data, operation = service.to_model_calls[0]
    assert operation == "update"
    assert isinstance(data, AuthorSchema)


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
@pytest.mark.asyncio
async def test_update_pydantic_per_call_schema_dump_config_includes_unset_defaults() -> None:
    """Per-call schema_dump_config should include Pydantic defaults when exclude_unset is disabled."""
    from pydantic import BaseModel

    default_dob = dt.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: dt.date = default_dob

    service = TrackingService()

    result = await service.update(
        AuthorSchema(name="Updated Name"),
        item_id="test-id",
        schema_dump_config=SchemaDumpConfig(exclude_unset=False),
    )

    assert result.name == "Updated Name"
    assert result.dob == default_dob


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
@pytest.mark.asyncio
async def test_update_pydantic_class_schema_dump_config_includes_unset_defaults() -> None:
    """Service class schema_dump_config should apply when no per-call override is passed."""
    from pydantic import BaseModel

    default_dob = dt.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: dt.date = default_dob

    class IncludeUnsetDefaultsService(TrackingService):
        schema_dump_config = SchemaDumpConfig(exclude_unset=False)

    service = IncludeUnsetDefaultsService()

    result = await service.update(AuthorSchema(name="Updated Name"), item_id="test-id")

    assert result.name == "Updated Name"
    assert result.dob == default_dob


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
@pytest.mark.asyncio
async def test_update_pydantic_per_call_schema_dump_config_does_not_leak() -> None:
    """A per-call schema_dump_config override should not affect later service calls."""
    from pydantic import BaseModel

    default_dob = dt.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: dt.date = default_dob

    service = TrackingService()
    first_existing = MockModel()
    first_existing.id = "first-id"  # type: ignore[assignment]
    first_existing.name = "first"
    first_existing.dob = None  # type: ignore[assignment]
    second_existing = MockModel()
    second_existing.id = "second-id"  # type: ignore[assignment]
    second_existing.name = "second"
    second_existing.dob = None  # type: ignore[assignment]
    service.repository.get = AsyncMock(side_effect=[first_existing, second_existing])  # type: ignore[method-assign]

    first_result = await service.update(
        AuthorSchema(name="First Updated"),
        item_id="first-id",
        schema_dump_config=SchemaDumpConfig(exclude_unset=False),
    )
    second_result = await service.update(AuthorSchema(name="Second Updated"), item_id="second-id")

    assert first_result.dob == default_dob
    assert second_result.name == "Second Updated"
    assert second_result.dob is None


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
@pytest.mark.asyncio
async def test_update_msgspec_calls_to_model_with_operation() -> None:
    """Test that update() with msgspec data calls to_model(data, 'update')."""
    import msgspec

    class AuthorStruct(msgspec.Struct):
        name: str

    service = TrackingService()

    # Update with msgspec struct
    struct = AuthorStruct(name="Updated Name")
    await service.update(struct, item_id="test-id")

    # Verify to_model was called with operation="update"
    assert len(service.to_model_calls) == 1
    data, operation = service.to_model_calls[0]
    assert operation == "update"
    assert isinstance(data, AuthorStruct)


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
@pytest.mark.asyncio
async def test_update_attrs_calls_to_model_with_operation() -> None:
    """Test that update() with attrs data calls to_model(data, 'update')."""
    from attrs import define

    @define
    class AuthorAttrs:
        name: str

    service = TrackingService()

    # Update with attrs instance
    attrs_obj = AuthorAttrs(name="Updated Name")
    await service.update(attrs_obj, item_id="test-id")

    # Verify to_model was called with operation="update"
    assert len(service.to_model_calls) == 1
    data, operation = service.to_model_calls[0]
    assert operation == "update"
    assert isinstance(data, AuthorAttrs)


@pytest.mark.asyncio
async def test_update_operation_map_routes_to_to_model_on_update() -> None:
    """Test that to_model() with operation='update' routes to to_model_on_update()."""
    service = TrackingService()

    # Update with dict data
    await service.update({"name": "updated"}, item_id="test-id")

    # Verify both methods were called
    assert len(service.to_model_calls) == 1
    assert len(service.to_model_on_update_calls) == 1

    # Verify operation_map routing worked
    _, operation = service.to_model_calls[0]
    assert operation == "update"


@pytest.mark.asyncio
async def test_update_propagates_with_for_update_flag() -> None:
    """Ensure the async service forwards locking hints directly to repository.update without a duplicate get()."""

    service = TrackingService()
    await service.update({"name": "updated"}, item_id="test-id", with_for_update=True)

    get_mock = cast(AsyncMock, service.repository.get)
    get_mock.assert_not_awaited()
    update_mock = cast(AsyncMock, service.repository.update)
    update_mock.assert_awaited_once()
    assert update_mock.call_args.kwargs["with_for_update"] is True


# Tests for sync service


def test_sync_delete_many_passes_id_only_input_through_without_copying() -> None:
    """Sync id-only delete_many() input should keep the existing bulk-delete fast path."""
    service = TrackingSyncService()
    captured: dict[str, Any] = {}

    def delete_many(item_ids: list[Any], **_: Any) -> list[MockModel]:
        captured["item_ids"] = item_ids
        return []

    service.repository.delete_many = MagicMock(side_effect=delete_many)  # type: ignore[method-assign]

    item_ids: list[PrimaryKeyType] = ["first-id", "second-id"]
    service.delete_many(item_ids)

    assert captured["item_ids"] is item_ids


def test_sync_delete_many_resolves_model_instances_before_delegating() -> None:
    """Sync delete_many() should resolve model instances to primary key values."""
    service = TrackingSyncService()
    captured: dict[str, Any] = {}

    def delete_many(item_ids: list[Any], **_: Any) -> list[MockModel]:
        captured["item_ids"] = item_ids
        return []

    service.repository.delete_many = MagicMock(side_effect=delete_many)  # type: ignore[method-assign]

    model = MockModel()
    model.id = "model-id"  # type: ignore[assignment]
    item_ids = cast("list[PrimaryKeyType]", [model, "raw-id"])
    service.delete_many(item_ids)

    assert captured["item_ids"] == ["model-id", "raw-id"]
    assert captured["item_ids"] is not item_ids


def test_sync_update_dict_calls_to_model_with_operation() -> None:
    """Test that sync update() with dict data calls to_model(data, 'update')."""
    service = TrackingSyncService()

    # Update with dict data and item_id
    service.update({"name": "Updated Name"}, item_id="test-id")

    # Verify to_model was called with operation="update"
    assert len(service.to_model_calls) == 1
    data, operation = service.to_model_calls[0]
    assert operation == "update"
    assert data == {"name": "Updated Name"}

    # Verify to_model_on_update was also called (via operation_map)
    assert len(service.to_model_on_update_calls) == 1


def test_sync_update_model_instance_calls_to_model_with_operation() -> None:
    """Test that sync update() with model instance calls to_model(data, 'update')."""
    service = TrackingSyncService()

    # Update with model instance
    model = MockModel()
    model.id = "test-id"  # type: ignore[assignment]
    model.name = "Updated Name"
    service.update(model)

    # Verify to_model was called with operation="update"
    assert len(service.to_model_calls) == 1
    data, operation = service.to_model_calls[0]
    assert operation == "update"
    assert data is model


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
def test_sync_update_pydantic_per_call_schema_dump_config_includes_unset_defaults() -> None:
    """Sync services should honor per-call schema_dump_config for Pydantic defaults."""
    from pydantic import BaseModel

    default_dob = dt.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: dt.date = default_dob

    service = TrackingSyncService()

    result = service.update(
        AuthorSchema(name="Updated Name"),
        item_id="test-id",
        schema_dump_config=SchemaDumpConfig(exclude_unset=False),
    )

    assert result.name == "Updated Name"
    assert result.dob == default_dob


def test_sync_update_propagates_with_for_update_flag() -> None:
    """Ensure the sync service forwards the locking flag directly to repository.update without a duplicate get()."""

    service = TrackingSyncService()
    service.update({"name": "updated"}, item_id="test-id", with_for_update=True)

    get_mock = cast(MagicMock, service.repository.get)
    get_mock.assert_not_called()
    update_mock = cast(MagicMock, service.repository.update)
    update_mock.assert_called_once()
    assert update_mock.call_args.kwargs["with_for_update"] is True


@pytest.mark.asyncio
async def test_update_invokes_overridden_to_model_on_update() -> None:
    """An overridden update lifecycle hook should be invoked during update conversion."""

    class UpdateHookService(SQLAlchemyAsyncRepositoryService[MockModel, MockRepository]):
        repository_type = MockRepository

        def __init__(self) -> None:
            self._repository = MockRepository()
            mock_model = MockModel()
            mock_model.id = "test-id"  # type: ignore[assignment]
            mock_model.name = "Old Name"
            self._repository.get = AsyncMock(return_value=mock_model)  # type: ignore[method-assign]
            self._repository.update = AsyncMock(side_effect=lambda data, **kwargs: data)  # type: ignore[method-assign]
            self.update_hook_called = False

        @property
        def repository(self) -> MockRepository:
            return self._repository

        async def to_model_on_update(self, data: ModelDictT[MockModel]) -> ModelDictT[MockModel]:
            self.update_hook_called = True
            return await super().to_model_on_update(data)

    service = UpdateHookService()
    await service.update({"name": "Updated Name"}, item_id="test-id")

    assert service.update_hook_called


@pytest.mark.asyncio
async def test_update_without_item_id_uses_model_id() -> None:
    """Test update without item_id uses ID from model instance."""
    service = TrackingService()

    model = MockModel()
    model.id = "model-id"  # type: ignore[assignment]
    model.name = "Updated Name"
    await service.update(model)

    assert len(service.to_model_calls) == 1


@pytest.mark.asyncio
async def test_update_preserves_existing_instance_attributes() -> None:
    """Test that update with item_id sets the ID on the partial model without touching unset attributes."""
    service = TrackingService()

    result = await service.update({"name": "New Name"}, item_id="test-id")
    state = sa_inspect(result)

    assert result.name == "New Name"
    assert result.id == "test-id"
    assert state is not None
    assert "dob" not in state.dict
    cast(AsyncMock, service.repository.get).assert_not_awaited()


def test_sync_update_preserves_existing_instance_attributes() -> None:
    """Test that sync update with item_id sets the ID on the partial model without touching unset attributes."""
    service = TrackingSyncService()

    result = service.update({"name": "New Name"}, item_id="test-id")
    state = sa_inspect(result)

    assert result.name == "New Name"
    assert result.id == "test-id"
    assert state is not None
    assert "dob" not in state.dict
    cast(MagicMock, service.repository.get).assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_cls", "mock_cls"),
    [(TrackingService, AsyncMock), (TrackingSyncService, MagicMock)],
)
@pytest.mark.parametrize("lookup_id", ["existing-id", "missing-id"])
async def test_service_get_or_none_delegates_to_repository(
    service_cls: type[Union[TrackingService, TrackingSyncService]],
    mock_cls: type[Union[AsyncMock, MagicMock]],
    lookup_id: str,
) -> None:
    """Ensure sync and async service get_or_none forward lookups without error_messages."""
    service = service_cls()
    sentinel = MockModel()
    sentinel.id = "existing-id"  # type: ignore[assignment]
    expected = sentinel if lookup_id == "existing-id" else None
    mock_get_or_none = mock_cls(return_value=expected)
    service.repository.get_or_none = mock_get_or_none  # type: ignore[method-assign]

    result = await maybe_async(service.get_or_none(lookup_id))

    assert result is expected
    mock_get_or_none.assert_called_once()
    assert mock_get_or_none.call_args.kwargs["item_id"] == lookup_id
    assert "error_messages" not in mock_get_or_none.call_args.kwargs


def test_service_generic_subclass_auto_binds_repository_type() -> None:
    """Service subclasses bind repository_type and model_type from generic type arguments."""

    class AutoAsyncService(SQLAlchemyAsyncRepositoryService[MockModel]):
        pass

    class AutoSyncService(SQLAlchemySyncRepositoryService[MockModel]):
        pass

    class CustomAsyncRepo(SQLAlchemyAsyncRepository[MockModel]):
        pass

    class CustomSyncRepo(SQLAlchemySyncRepository[MockModel]):
        pass

    class CustomRepoAsyncService(SQLAlchemyAsyncRepositoryService[MockModel, CustomAsyncRepo]):
        pass

    class CustomRepoSyncService(SQLAlchemySyncRepositoryService[MockModel, CustomSyncRepo]):
        pass

    class ParametricSlugAsyncService(
        SQLAlchemyAsyncRepositoryService[MockModel, SQLAlchemyAsyncSlugRepository[MockModel]]
    ):
        pass

    class ParametricSlugSyncService(
        SQLAlchemySyncRepositoryService[MockModel, SQLAlchemySyncSlugRepository[MockModel]]
    ):
        pass

    async_session = AsyncMock(spec=AsyncSession, bind=MagicMock(), info={})
    sync_session = MagicMock(spec=Session, bind=MagicMock(), info={})

    auto_async_svc = AutoAsyncService(session=async_session)
    auto_sync_svc = AutoSyncService(session=sync_session)
    custom_async_svc = CustomRepoAsyncService(session=async_session)
    custom_sync_svc = CustomRepoSyncService(session=sync_session)
    slug_async_svc = ParametricSlugAsyncService(session=async_session)
    slug_sync_svc = ParametricSlugSyncService(session=sync_session)

    assert AutoAsyncService._model_type is MockModel
    assert isinstance(auto_async_svc.repository, SQLAlchemyAsyncRepository)
    assert auto_async_svc.repository.model_type is MockModel

    assert AutoSyncService._model_type is MockModel
    assert isinstance(auto_sync_svc.repository, SQLAlchemySyncRepository)
    assert auto_sync_svc.repository.model_type is MockModel

    assert isinstance(custom_async_svc.repository, CustomAsyncRepo)
    assert custom_async_svc.repository.model_type is MockModel

    assert isinstance(custom_sync_svc.repository, CustomSyncRepo)
    assert custom_sync_svc.repository.model_type is MockModel

    assert isinstance(slug_async_svc.repository, SQLAlchemyAsyncSlugRepository)
    assert slug_async_svc.repository.model_type is MockModel

    assert isinstance(slug_sync_svc.repository, SQLAlchemySyncSlugRepository)
    assert slug_sync_svc.repository.model_type is MockModel

    direct_async_service: SQLAlchemyAsyncRepositoryService[MockModel] = SQLAlchemyAsyncRepositoryService(
        session=async_session,
        model_type=MockModel,
    )
    direct_sync_service: SQLAlchemySyncRepositoryService[MockModel] = SQLAlchemySyncRepositoryService(
        session=sync_session,
        model_type=MockModel,
    )

    assert isinstance(direct_async_service.repository, SQLAlchemyAsyncRepository)
    assert direct_async_service.repository.model_type is MockModel
    assert isinstance(direct_sync_service.repository, SQLAlchemySyncRepository)
    assert direct_sync_service.repository.model_type is MockModel

    class MockAsyncOverrideRepo(SQLAlchemyAsyncMockRepository[MockModel]):
        pass

    class MockSyncOverrideRepo(SQLAlchemySyncMockRepository[MockModel]):
        pass

    mock_async_svc = AutoAsyncService(session=async_session, repository_type=MockAsyncOverrideRepo)
    mock_sync_svc = AutoSyncService(session=sync_session, repository_type=MockSyncOverrideRepo)
    assert isinstance(mock_async_svc.repository, MockAsyncOverrideRepo)
    assert isinstance(mock_sync_svc.repository, MockSyncOverrideRepo)


def test_inherited_repository_type_survives_extra_generic_parameters() -> None:
    """Service subclasses with custom or reordered generic parameters resolve mapped models and preserve repository_type."""
    model_var = TypeVar("model_var")
    schema_var = TypeVar("schema_var")

    class BaseService(SQLAlchemySyncRepositoryService[model_var], Generic[model_var, schema_var]):  # type: ignore[type-var]
        pass

    class ParentService(BaseService[MockModel, dict[str, Any]]):
        repository_type = MockSyncRepository

    class LeafService(ParentService):
        pass

    class ReorderedBaseService(SQLAlchemySyncRepositoryService[model_var], Generic[schema_var, model_var]):  # type: ignore[type-var]
        pass

    class ReorderedLeafService(ReorderedBaseService[dict[str, Any], MockModel]):
        pass

    reordered_repo_type = getattr(ReorderedLeafService, "repository_type", None)
    assert LeafService.repository_type is MockSyncRepository
    assert ReorderedLeafService._model_type is MockModel
    assert reordered_repo_type is not None
    assert issubclass(reordered_repo_type, SQLAlchemySyncRepository)
    assert getattr(reordered_repo_type, "model_type", None) is MockModel
    assert reordered_repo_type.__module__ == __name__


class DataclassMappedBase(MappedAsDataclass, DeclarativeBase):
    """Base for dataclass-mapped service update tests."""


class DataclassMappedArticle(DataclassMappedBase):
    """Dataclass-mapped model with required, nullable, and default columns."""

    __tablename__ = "service_dataclass_article"

    id: Mapped[int] = mapped_column(primary_key=True, init=False)
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default="draft")
    subtitle: Mapped[Optional[str]] = mapped_column(default="default-sub", nullable=True)
    server_tag: Mapped[Optional[str]] = mapped_column(default=None, server_default="srv-tag", nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(default=None, nullable=True)


class DataclassMappedArticleService(SQLAlchemySyncRepositoryService[DataclassMappedArticle]):
    """Auto-bound sync service for DataclassMappedArticle."""


def test_dataclass_mapped_model_partial_update_and_explicit_none() -> None:
    """Service item_id updates write explicit None while repository instance updates preserve defaults silently."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    DataclassMappedBase.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            service = DataclassMappedArticleService(session=session)
            article = DataclassMappedArticle(
                title="Initial",
                status="published",
                subtitle="custom-sub",
                server_tag="keep-srv",
                notes="keep-me",
            )
            session.add(article)
            session.commit()
            article_id = article.id

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                updated = service.update({"title": "Renamed"}, item_id=article_id, auto_commit=True)
                assert updated.title == "Renamed"
                assert updated.status == "published"
                assert updated.subtitle == "custom-sub"
                assert updated.server_tag == "keep-srv"
                assert updated.notes == "keep-me"

                repo_input = DataclassMappedArticle(title="Repo Renamed", status="published")
                repo_input.id = article_id
                repo_updated = service.repository.update(repo_input, auto_commit=True)
                assert repo_updated.title == "Repo Renamed"
                assert repo_updated.server_tag == "keep-srv"

                cleared = service.update({"subtitle": None, "notes": None}, item_id=article_id, auto_commit=True)
                assert cleared.title == "Repo Renamed"
                assert cleared.status == "published"
                assert cleared.subtitle is None
                assert cleared.notes is None
                assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]

            with pytest.raises(IntegrityError):
                service.update({"status": None}, item_id=article_id, auto_commit=True)
            session.rollback()

            with pytest.raises(IntegrityError):
                service.update({"title": None}, item_id=article_id, auto_commit=True)
    finally:
        engine.dispose()


class CustomInitBase(DeclarativeBase):
    """Base for models with constructor-derived attributes."""


class DefaultInitArticle(CustomInitBase):
    """Model using the default declarative constructor."""

    __tablename__ = "service_default_init_article"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class SluggedArticle(CustomInitBase):
    """Model whose constructor derives ``slug`` from ``name``."""

    __tablename__ = "service_slugged_article"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    body: Mapped[Optional[str]] = mapped_column(nullable=True)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if "name" in kwargs:
            self.slug = str(kwargs["name"]).lower().replace(" ", "-")


class SluggedArticleService(SQLAlchemySyncRepositoryService[SluggedArticle]):
    """Auto-bound sync service for SluggedArticle."""


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        pytest.param(DefaultInitArticle, True, id="declarative-constructor"),
        pytest.param(DataclassMappedArticle, True, id="mapped-as-dataclass"),
        pytest.param(SluggedArticle, False, id="custom-init"),
    ],
)
def test_supports_partial_hydration(model: type[Any], expected: bool) -> None:
    """Partial hydration applies only when the model constructor has no side effects to preserve."""
    assert supports_partial_hydration(model) is expected


def test_custom_init_model_update_applies_constructor_side_effects() -> None:
    """Updates on models with a custom ``__init__`` still apply constructor-derived attributes."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    CustomInitBase.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            service = SluggedArticleService(session=session)
            session.add(SluggedArticle(id=1, name="First Post", body="keep-me"))
            session.commit()

            updated = service.update({"name": "Renamed Post"}, item_id=1, auto_commit=True)
            assert updated.name == "Renamed Post"
            assert updated.slug == "renamed-post"
            assert updated.body == "keep-me"
    finally:
        engine.dispose()


@pytest.mark.parametrize("use_config", [False, True])
async def test_service_new_preserves_custom_constructor(use_config: bool) -> None:
    """Inherited factories preserve constructors predating the model/repository overrides."""

    class LegacyAsyncService(SQLAlchemyAsyncRepositoryService[MockModel]):
        def __init__(
            self,
            session: Any,
            statement: Any = None,
            error_messages: Any = None,
            load: Any = None,
            execution_options: Any = None,
            uniquify: Any = None,
            count_with_window_function: Any = None,
        ) -> None:
            super().__init__(session=session)

    class LegacySyncService(SQLAlchemySyncRepositoryService[MockModel]):
        def __init__(
            self,
            session: Any,
            statement: Any = None,
            error_messages: Any = None,
            load: Any = None,
            execution_options: Any = None,
            uniquify: Any = None,
            count_with_window_function: Any = None,
        ) -> None:
            super().__init__(session=session)

    async_session = AsyncMock(spec=AsyncSession, bind=MagicMock(), info={})
    sync_session = MagicMock(spec=Session, bind=MagicMock(), info={})
    async_config = MagicMock()
    async_config.get_session.return_value.__aenter__.return_value = async_session
    sync_config = MagicMock()
    sync_config.get_session.return_value.__enter__.return_value = sync_session
    async_options: dict[str, Any] = {"config": async_config} if use_config else {"session": async_session}
    sync_options: dict[str, Any] = {"config": sync_config} if use_config else {"session": sync_session}
    async with LegacyAsyncService.new(**async_options) as svc:
        assert svc.repository.session is async_session
    with LegacySyncService.new(**sync_options) as svc_sync:
        assert svc_sync.repository.session is sync_session


async def test_service_new_explicit_overrides() -> None:
    """Factory overrides still reach the constructed service in sync and async mode."""
    async_session = AsyncMock(spec=AsyncSession, bind=MagicMock(), info={})
    sync_session = MagicMock(spec=Session, bind=MagicMock(), info={})
    async with SQLAlchemyAsyncRepositoryService.new(
        session=async_session, model_type=MockModel, repository_type=SQLAlchemyAsyncMockRepository
    ) as svc:
        assert isinstance(svc.repository, SQLAlchemyAsyncMockRepository)
        assert svc.repository.model_type is MockModel
    with SQLAlchemySyncRepositoryService.new(
        session=sync_session, model_type=MockModel, repository_type=SQLAlchemySyncMockRepository
    ) as svc_sync:
        assert isinstance(svc_sync.repository, SQLAlchemySyncMockRepository)
        assert svc_sync.repository.model_type is MockModel

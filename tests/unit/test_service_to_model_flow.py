"""Unit tests for service.update() model conversion flow.

These tests verify that update input types are routed through to_model(data, "update")
and the update lifecycle hook before persistence.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.repository._util import get_primary_key_info
from advanced_alchemy.service import SchemaDumpConfig, SQLAlchemyAsyncRepositoryService, SQLAlchemySyncRepositoryService
from advanced_alchemy.utils.serialization import ATTRS_INSTALLED, MSGSPEC_INSTALLED, PYDANTIC_INSTALLED, ModelDictT

pytestmark = [pytest.mark.unit]


class MockModel(UUIDAuditBase):
    """Minimal SQLAlchemy model for service flow tests."""

    name: Mapped[str] = mapped_column(String(length=100))  # pyright: ignore[reportUninitializedInstanceVariable]
    dob: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)  # pyright: ignore[reportUninitializedInstanceVariable]


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
        # Create mock repository
        self._repository = MockRepository()
        # Mock model with proper SQLAlchemy attributes
        mock_model = MockModel()
        mock_model.id = "existing-id"  # type: ignore[assignment]
        mock_model.name = "existing"
        mock_model.dob = None  # type: ignore[assignment]
        self._repository.get = AsyncMock(return_value=mock_model)  # type: ignore[method-assign]
        self._repository.update = AsyncMock(side_effect=lambda data, **kwargs: data)  # type: ignore[method-assign]

        # Track method calls
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
        # Create mock repository
        self._repository = MockSyncRepository()
        # Mock model with proper SQLAlchemy attributes
        mock_model = MockModel()
        mock_model.id = "existing-id"  # type: ignore[assignment]
        mock_model.name = "existing"
        mock_model.dob = None  # type: ignore[assignment]
        self._repository.get = MagicMock(return_value=mock_model)  # type: ignore[method-assign]
        self._repository.update = MagicMock(side_effect=lambda data, **kwargs: data)  # type: ignore[method-assign]

        # Track method calls
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

    default_dob = datetime.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: datetime.date = default_dob

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

    default_dob = datetime.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: datetime.date = default_dob

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

    default_dob = datetime.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: datetime.date = default_dob

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
    """Ensure the async service forwards locking hints to the repository."""

    service = TrackingService()
    await service.update({"name": "updated"}, item_id="test-id", with_for_update=True)

    get_mock = cast(AsyncMock, service.repository.get)
    get_mock.assert_awaited_once()
    assert get_mock.call_args.kwargs["with_for_update"] is True


# Tests for sync service


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

    default_dob = datetime.date(2000, 1, 1)

    class AuthorSchema(BaseModel):
        name: str
        dob: datetime.date = default_dob

    service = TrackingSyncService()

    result = service.update(
        AuthorSchema(name="Updated Name"),
        item_id="test-id",
        schema_dump_config=SchemaDumpConfig(exclude_unset=False),
    )

    assert result.name == "Updated Name"
    assert result.dob == default_dob


def test_sync_update_propagates_with_for_update_flag() -> None:
    """Ensure the sync service forwards the locking flag to its repository."""

    service = TrackingSyncService()
    service.update({"name": "updated"}, item_id="test-id", with_for_update=True)

    get_mock = cast(MagicMock, service.repository.get)
    get_mock.assert_called_once()
    assert get_mock.call_args.kwargs["with_for_update"] is True


# Tests for update lifecycle overrides


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


# Edge case tests


@pytest.mark.asyncio
async def test_update_without_item_id_uses_model_id() -> None:
    """Test update without item_id uses ID from model instance."""
    service = TrackingService()

    # Update with model that has ID
    model = MockModel()
    model.id = "model-id"  # type: ignore[assignment]
    model.name = "Updated Name"
    await service.update(model)

    # Should work - uses model's ID
    assert len(service.to_model_calls) == 1


@pytest.mark.asyncio
async def test_update_preserves_existing_instance_attributes() -> None:
    """Test that update with item_id preserves existing instance attributes."""
    service = TrackingService()

    # Update only name field
    result = await service.update({"name": "New Name"}, item_id="test-id")

    # Existing ID should be preserved from existing instance
    assert result.name == "New Name"
    assert result.id == "existing-id"  # From mock repository's get()


def test_sync_update_preserves_existing_instance_attributes() -> None:
    """Test that sync update with item_id preserves existing instance attributes."""
    service = TrackingSyncService()

    # Update only name field
    result = service.update({"name": "New Name"}, item_id="test-id")

    # Existing ID should be preserved from existing instance
    assert result.name == "New Name"
    assert result.id == "existing-id"  # From mock repository's get()

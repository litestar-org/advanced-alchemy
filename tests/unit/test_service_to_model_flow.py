"""Unit tests verifying to_model() operation flow for service.update()

This test suite validates GitHub issue #555 fix - ensuring that service.update()
calls to_model(data, "update") for ALL data types (dict, Pydantic, msgspec, attrs, model).

Before the fix, dict/Pydantic/msgspec/attrs data bypassed to_model() entirely.
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, SQLAlchemySyncRepositoryService
from advanced_alchemy.service.typing import ATTRS_INSTALLED, MSGSPEC_INSTALLED, PYDANTIC_INSTALLED, ModelDictT

# Use real SQLAlchemy models from fixtures instead of mock
# Import from test fixtures which have proper SQLAlchemy declarative models
from tests.fixtures.uuid.models import UUIDAuthor as MockModel

pytestmark = [pytest.mark.unit]


class MockRepository(SQLAlchemyAsyncRepository[MockModel]):
    """Mock repository for testing."""

    model_type = MockModel

    def __init__(self) -> None:
        # Don't call super().__init__ to avoid needing session
        self.model_type = MockModel
        self.id_attribute = "id"


class MockSyncRepository(SQLAlchemySyncRepository[MockModel]):
    """Mock sync repository for testing."""

    model_type = MockModel

    def __init__(self) -> None:
        # Don't call super().__init__ to avoid needing session
        self.model_type = MockModel
        self.id_attribute = "id"


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
    ) -> MockModel:
        """Track to_model calls."""
        self.to_model_calls.append((data, operation))
        return await super().to_model(data, operation)

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
    ) -> MockModel:
        """Track to_model calls."""
        self.to_model_calls.append((data, operation))
        return super().to_model(data, operation)

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


# Tests for backward compatibility


@pytest.mark.asyncio
async def test_backward_compat_to_model_on_update_only() -> None:
    """Test backward compatibility - service with ONLY to_model_on_update() override."""

    class LegacyService(SQLAlchemyAsyncRepositoryService[MockModel, MockRepository]):
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
            """Legacy pattern - only override to_model_on_update."""
            self.update_hook_called = True
            return await super().to_model_on_update(data)

    service = LegacyService()
    await service.update({"name": "Updated Name"}, item_id="test-id")

    # Verify to_model_on_update was called (backward compatible)
    assert service.update_hook_called


# Real-world pattern tests using SlugBook fixtures are in integration tests
# The SlugBookAsyncService and SlugBookSyncService in tests/fixtures/uuid/services.py
# demonstrate the exact pattern this fix enables:
# - Custom to_model() that checks operation == "update"
# - Regenerates slug when title changes during update
# - This pattern would have been broken before the fix for dict/Pydantic/msgspec/attrs data


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

"""Tests for delete operations with auto_expunge.

This test module validates the fix for issue #514 where delete operations
with auto_expunge=True and auto_commit=True would fail with InvalidRequestError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy import base
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestModel(base.UUIDAuditBase):
    """Test model for delete expunge tests."""


class TestModelRepository(SQLAlchemyAsyncRepository[TestModel]):
    """Async repository for TestModel."""

    model_type = TestModel


class TestModelRepositorySync(SQLAlchemySyncRepository[TestModel]):
    """Sync repository for TestModel."""

    model_type = TestModel


class TestExpungeDeletedObjects:
    """Test that _expunge() correctly handles deleted objects."""

    @pytest.fixture
    def mock_instance(self) -> MagicMock:
        """Create a mock instance for testing."""
        return MagicMock()

    def test_expunge_skips_deleted_objects_async(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that _expunge() skips deleted objects to avoid InvalidRequestError.

        This is the core fix for issue #514.
        """
        # Setup: Mock session and repository
        session = AsyncMock(spec=AsyncSession, bind=MagicMock())
        repo = TestModelRepository(session=session, auto_expunge=True)

        # Mock inspect to return deleted state
        mock_state = MagicMock()
        mock_state.deleted = True
        mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_state)

        # Call _expunge - should not raise, should not call session.expunge
        repo._expunge(mock_instance, auto_expunge=True)

        # Verify: expunge was NOT called (because object is deleted)
        session.expunge.assert_not_called()

    def test_expunge_calls_session_for_non_deleted_async(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that _expunge() still calls session.expunge for non-deleted objects."""
        # Setup
        session = AsyncMock(spec=AsyncSession, bind=MagicMock())
        repo = TestModelRepository(session=session, auto_expunge=True)

        # Mock inspect to return non-deleted, non-detached state
        mock_state = MagicMock()
        mock_state.deleted = False
        mock_state.detached = False
        mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_state)

        # Call _expunge - should call session.expunge
        repo._expunge(mock_instance, auto_expunge=True)

        # Verify: expunge WAS called (object not deleted and not detached)
        session.expunge.assert_called_once_with(mock_instance)

    def test_expunge_respects_auto_expunge_false_async(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that _expunge() respects auto_expunge=False."""
        # Setup
        session = AsyncMock(spec=AsyncSession, bind=MagicMock())
        repo = TestModelRepository(session=session, auto_expunge=False)

        # Mock inspect (shouldn't be called)
        mock_inspect = mocker.patch("advanced_alchemy.repository._async.inspect")

        # Call _expunge with auto_expunge=False
        repo._expunge(mock_instance, auto_expunge=False)

        # Verify: Neither inspect nor expunge were called
        mock_inspect.assert_not_called()
        session.expunge.assert_not_called()

    def test_expunge_handles_none_state_async(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that _expunge() handles inspect returning None gracefully."""
        # Setup
        session = AsyncMock(spec=AsyncSession, bind=MagicMock())
        repo = TestModelRepository(session=session, auto_expunge=True)

        # Mock inspect to return None (edge case)
        mocker.patch("advanced_alchemy.repository._async.inspect", return_value=None)

        # Call _expunge - should call session.expunge (no state check passes)
        repo._expunge(mock_instance, auto_expunge=True)

        # Verify: expunge WAS called (None state doesn't have .deleted)
        session.expunge.assert_called_once_with(mock_instance)

    def test_expunge_skips_detached_objects_async(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that _expunge() skips detached objects.

        This handles the case where objects from DELETE...RETURNING have
        already been detached after commit.
        """
        # Setup
        session = AsyncMock(spec=AsyncSession, bind=MagicMock())
        repo = TestModelRepository(session=session, auto_expunge=True)

        # Mock inspect to return detached state
        mock_state = MagicMock()
        mock_state.deleted = False
        mock_state.detached = True
        mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_state)

        # Call _expunge - should not call session.expunge
        result = repo._expunge(mock_instance, auto_expunge=True)

        # Verify: expunge was NOT called (object is detached)
        session.expunge.assert_not_called()
        assert result is None

    def test_expunge_skips_deleted_objects_sync(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that _expunge() skips deleted objects in sync repository."""
        # Setup
        session = MagicMock(spec=Session, bind=MagicMock())
        repo = TestModelRepositorySync(session=session, auto_expunge=True)

        # Mock inspect to return deleted state
        mock_state = MagicMock()
        mock_state.deleted = True
        mocker.patch("advanced_alchemy.repository._sync.inspect", return_value=mock_state)

        # Call _expunge - should not call session.expunge
        repo._expunge(mock_instance, auto_expunge=True)

        # Verify: expunge was NOT called
        session.expunge.assert_not_called()

    def test_expunge_calls_session_for_non_deleted_sync(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that _expunge() calls session.expunge for non-deleted objects in sync repo."""
        # Setup
        session = MagicMock(spec=Session, bind=MagicMock())
        repo = TestModelRepositorySync(session=session, auto_expunge=True)

        # Mock inspect to return non-deleted, non-detached state
        mock_state = MagicMock()
        mock_state.deleted = False
        mock_state.detached = False
        mocker.patch("advanced_alchemy.repository._sync.inspect", return_value=mock_state)

        # Call _expunge
        repo._expunge(mock_instance, auto_expunge=True)

        # Verify: expunge WAS called
        session.expunge.assert_called_once_with(mock_instance)


class TestDeleteMethodsStateChecking:
    """Test that delete methods interact correctly with the updated _expunge()."""

    @pytest.fixture
    def mock_instance(self) -> MagicMock:
        """Create a mock instance."""
        instance = MagicMock()
        instance.id = "test-id"
        return instance

    async def test_delete_with_auto_expunge_does_not_raise(
        self,
        mock_instance: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Integration test: delete() with auto_expunge=True should not raise InvalidRequestError.

        This is the high-level regression test for issue #514.
        """
        # Setup
        session = AsyncMock(spec=AsyncSession, bind=MagicMock())
        repo = TestModelRepository(session=session, auto_expunge=True, auto_commit=True)

        # Mock get_one to return our instance
        mocker.patch.object(repo, "get_one", return_value=mock_instance)

        # Mock inspect to simulate deleted state after commit
        mock_state = MagicMock()
        mock_state.deleted = True
        mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_state)

        # Mock session.delete and commit
        session.delete = AsyncMock()
        session.commit = AsyncMock()

        # This should NOT raise InvalidRequestError
        result = await repo.delete("test-id")

        # Verify the instance was returned
        assert result == mock_instance

        # Verify session.expunge was NOT called (because object is deleted)
        session.expunge.assert_not_called()

    async def test_delete_many_with_auto_expunge_does_not_raise(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Integration test: delete_many() with auto_expunge should not raise."""
        # Setup
        session = AsyncMock(spec=AsyncSession, bind=MagicMock())
        repo = TestModelRepository(session=session, auto_expunge=True, auto_commit=True)

        instances = [MagicMock(id=f"id-{i}") for i in range(3)]

        # Mock _get_delete_many_statement to return a statement
        mocker.patch.object(repo, "_get_delete_many_statement", return_value=MagicMock())

        # Mock scalars to return instances
        mock_scalars_result = MagicMock()
        mock_scalars_result.__aiter__ = AsyncMock(return_value=iter(instances))
        session.scalars = AsyncMock(return_value=mock_scalars_result)

        # Mock dialect to support returning
        repo._dialect.delete_executemany_returning = True

        # Mock inspect to simulate deleted state
        mock_state = MagicMock()
        mock_state.deleted = True
        mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_state)

        # This should NOT raise InvalidRequestError
        result = await repo.delete_many(["id-1", "id-2", "id-3"])

        # Verify instances were returned
        assert len(result) == 3

        # Verify session.expunge was NOT called for any instance
        session.expunge.assert_not_called()

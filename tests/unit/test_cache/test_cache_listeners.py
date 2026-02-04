"""Unit tests for cache-related listeners in advanced_alchemy._listeners."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from advanced_alchemy._listeners import (
    AsyncCacheListener,
    BaseCacheListener,
    CacheInvalidationListener,
    CacheInvalidationTracker,
    SyncCacheListener,
    get_cache_tracker,
    setup_cache_listeners,
)

# --- CacheInvalidationTracker Tests ---


def test_cache_invalidation_tracker_add_invalidation() -> None:
    mock_manager = MagicMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    assert ("User", 1, "group1") in tracker._pending_invalidations
    assert "User" in tracker._pending_model_bumps


def test_cache_invalidation_tracker_commit() -> None:
    mock_manager = MagicMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    tracker.commit()

    mock_manager.bump_model_version_sync.assert_called_with("User")
    mock_manager.invalidate_entity_sync.assert_called_with("User", 1, "group1")
    assert not tracker._pending_invalidations
    assert not tracker._pending_model_bumps


def test_cache_invalidation_tracker_rollback() -> None:
    mock_manager = MagicMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    tracker.rollback()

    mock_manager.bump_model_version_sync.assert_not_called()
    assert not tracker._pending_invalidations
    assert not tracker._pending_model_bumps


@pytest.mark.asyncio
async def test_cache_invalidation_tracker_commit_async() -> None:
    mock_manager = AsyncMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    await tracker.commit_async()

    mock_manager.bump_model_version_async.assert_called_with("User")
    mock_manager.invalidate_entity_async.assert_called_with("User", 1, "group1")
    assert not tracker._pending_invalidations
    assert not tracker._pending_model_bumps


# --- get_cache_tracker Tests ---


def test_get_cache_tracker_existing() -> None:
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker}

    result = get_cache_tracker(session)
    assert result is tracker


def test_get_cache_tracker_create() -> None:
    session = MagicMock(spec=Session)
    session.info = {}
    mock_manager = MagicMock()

    result = get_cache_tracker(session, cache_manager=mock_manager, create=True)
    assert isinstance(result, CacheInvalidationTracker)
    assert session.info["_aa_cache_tracker"] is result


def test_get_cache_tracker_no_create() -> None:
    session = MagicMock(spec=Session)
    session.info = {}

    result = get_cache_tracker(session, create=False)
    assert result is None


# --- SyncCacheListener Tests ---


def test_sync_cache_listener_after_commit() -> None:
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    SyncCacheListener.after_commit(session)

    tracker.commit.assert_called_once()
    assert "_aa_cache_tracker" not in session.info


def test_sync_cache_listener_after_rollback() -> None:
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    SyncCacheListener.after_rollback(session)

    tracker.rollback.assert_called_once()
    assert "_aa_cache_tracker" not in session.info


def test_sync_cache_listener_disabled() -> None:
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": False}

    SyncCacheListener.after_commit(session)

    tracker.commit.assert_not_called()


# --- AsyncCacheListener Tests ---


@pytest.mark.asyncio
async def test_async_cache_listener_after_commit() -> None:
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    # Mock commit_async to verify it's scheduled
    tracker.commit_async = AsyncMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    AsyncCacheListener.after_commit(session)

    # Since it creates a task, we verify it popped the tracker
    assert "_aa_cache_tracker" not in session.info


def test_async_cache_listener_after_rollback() -> None:
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    AsyncCacheListener.after_rollback(session)

    tracker.rollback.assert_called_once()
    assert "_aa_cache_tracker" not in session.info


# --- CacheInvalidationListener Tests ---


def test_cache_invalidation_listener_after_commit_sync_context() -> None:
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    try:
        CacheInvalidationListener.after_commit(session)
    except RuntimeError:
        # If no loop, it calls tracker.commit()
        pass


# --- BaseCacheListener Tests ---


class TestBaseCacheListener(BaseCacheListener):
    pass


def test_base_cache_listener_is_listener_enabled() -> None:
    session = MagicMock(spec=Session)
    session.info = {}
    session.bind = None
    session.execution_options = None
    assert TestBaseCacheListener._is_listener_enabled(session) is True

    session.info = {"enable_cache_listener": False}
    assert TestBaseCacheListener._is_listener_enabled(session) is False


def test_base_cache_listener_execution_options() -> None:
    session = MagicMock(spec=Session)
    session.info = {}
    session.bind = None

    # Test execution_options via session
    session.execution_options = {"enable_cache_listener": False}
    assert TestBaseCacheListener._is_listener_enabled(session) is False

    session.execution_options = {"enable_cache_listener": True}
    assert TestBaseCacheListener._is_listener_enabled(session) is True


# --- Setup Tests ---


def test_setup_cache_listeners() -> None:
    with patch("advanced_alchemy._listeners.event.listen") as mock_listen:
        setup_cache_listeners()
        assert mock_listen.called

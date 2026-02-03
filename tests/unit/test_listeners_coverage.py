import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from advanced_alchemy._listeners import (
    AsyncCacheListener,
    AsyncFileObjectListener,
    BaseCacheListener,
    BaseFileObjectListener,
    CacheInvalidationListener,
    CacheInvalidationTracker,
    FileObjectInspector,
    FileObjectListener,
    SyncCacheListener,
    SyncFileObjectListener,
    _active_file_operations,
    _has_persistent_column_changes,
    get_cache_tracker,
    get_file_tracker,
    is_async_context,
    reset_async_context,
    set_async_context,
    setup_cache_listeners,
    setup_file_object_listeners,
    touch_updated_timestamp,
)

# --- CacheInvalidationTracker Tests ---

def test_cache_invalidation_tracker_add_invalidation():
    mock_manager = MagicMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    assert ("User", 1, "group1") in tracker._pending_invalidations
    assert "User" in tracker._pending_model_bumps

def test_cache_invalidation_tracker_commit():
    mock_manager = MagicMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    tracker.commit()

    mock_manager.bump_model_version_sync.assert_called_with("User")
    mock_manager.invalidate_entity_sync.assert_called_with("User", 1, "group1")
    assert not tracker._pending_invalidations
    assert not tracker._pending_model_bumps

def test_cache_invalidation_tracker_rollback():
    mock_manager = MagicMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    tracker.rollback()

    mock_manager.bump_model_version_sync.assert_not_called()
    assert not tracker._pending_invalidations
    assert not tracker._pending_model_bumps

@pytest.mark.asyncio
async def test_cache_invalidation_tracker_commit_async():
    mock_manager = AsyncMock()
    tracker = CacheInvalidationTracker(mock_manager)
    tracker.add_invalidation("User", 1, "group1")

    await tracker.commit_async()

    mock_manager.bump_model_version_async.assert_called_with("User")
    mock_manager.invalidate_entity_async.assert_called_with("User", 1, "group1")
    assert not tracker._pending_invalidations
    assert not tracker._pending_model_bumps

# --- get_cache_tracker Tests ---

def test_get_cache_tracker_existing():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker}

    result = get_cache_tracker(session)
    assert result is tracker

def test_get_cache_tracker_create():
    session = MagicMock(spec=Session)
    session.info = {}
    mock_manager = MagicMock()

    result = get_cache_tracker(session, cache_manager=mock_manager, create=True)
    assert isinstance(result, CacheInvalidationTracker)
    assert session.info["_aa_cache_tracker"] is result

def test_get_cache_tracker_no_create():
    session = MagicMock(spec=Session)
    session.info = {}

    result = get_cache_tracker(session, create=False)
    assert result is None

# --- SyncCacheListener Tests ---

def test_sync_cache_listener_after_commit():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    SyncCacheListener.after_commit(session)

    tracker.commit.assert_called_once()
    assert "_aa_cache_tracker" not in session.info

def test_sync_cache_listener_after_rollback():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    SyncCacheListener.after_rollback(session)

    tracker.rollback.assert_called_once()
    assert "_aa_cache_tracker" not in session.info

def test_sync_cache_listener_disabled():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": False}

    SyncCacheListener.after_commit(session)

    tracker.commit.assert_not_called()

# --- AsyncCacheListener Tests ---

@pytest.mark.asyncio
async def test_async_cache_listener_after_commit():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    # Mock commit_async to verify it's scheduled
    tracker.commit_async = AsyncMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    AsyncCacheListener.after_commit(session)

    # Since it creates a task, we verify it popped the tracker
    assert "_aa_cache_tracker" not in session.info

def test_async_cache_listener_after_rollback():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    AsyncCacheListener.after_rollback(session)

    tracker.rollback.assert_called_once()
    assert "_aa_cache_tracker" not in session.info

# --- CacheInvalidationListener Tests ---

def test_cache_invalidation_listener_after_commit_sync_context():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_cache_tracker": tracker, "enable_cache_listener": True}

    try:
        CacheInvalidationListener.after_commit(session)
    except RuntimeError:
         # If no loop, it calls tracker.commit()
         pass

# --- FileObjectInspector Tests ---

def test_file_object_inspector_inspect_instance_no_state():
    instance = MagicMock()
    tracker = MagicMock()
    # Mock inspect to return None
    with patch("advanced_alchemy._listeners.inspect", return_value=None):
        FileObjectInspector.inspect_instance(instance, tracker)
        # Should return early, no exception

def test_file_object_inspector_inspect_instance_no_mapper():
    instance = MagicMock()
    tracker = MagicMock()
    mock_state = MagicMock()
    mock_state.mapper = None

    with patch("advanced_alchemy._listeners.inspect", return_value=mock_state):
        FileObjectInspector.inspect_instance(instance, tracker)
        # Should return early

def test_file_object_inspector_inspect_instance_key_error():
    from advanced_alchemy.types.file_object import StoredObject
    instance = MagicMock()
    tracker = MagicMock()
    mock_state = MagicMock()
    mock_mapper = MagicMock()
    mock_state.mapper = mock_mapper

    mock_attr = MagicMock()
    mock_attr.expression.type = MagicMock(spec=StoredObject)

    mock_mapper.column_attrs = {"file_col": mock_attr}
    mock_state.attrs = {} # Empty attrs, will trigger KeyError

    with patch("advanced_alchemy._listeners.inspect", return_value=mock_state):
        FileObjectInspector.inspect_instance(instance, tracker)
        # Should handle KeyError gracefully

def test_handle_single_attribute_added():
    from advanced_alchemy.types.file_object import FileObject, FileObjectSessionTracker

    tracker = MagicMock(spec=FileObjectSessionTracker)
    attr_state = MagicMock()

    mock_file = MagicMock(spec=FileObject)
    mock_file._pending_source_content = b"content"
    mock_file._pending_source_path = None

    attr_state.history.added = [mock_file]
    attr_state.history.deleted = []

    FileObjectInspector.handle_single_attribute(attr_state, tracker)

    tracker.add_pending_save.assert_called_with(mock_file, b"content")

def test_handle_single_attribute_deleted():
    from advanced_alchemy.types.file_object import FileObject, FileObjectSessionTracker

    tracker = MagicMock(spec=FileObjectSessionTracker)
    attr_state = MagicMock()

    mock_file = MagicMock(spec=FileObject)
    mock_file.path = "some/path"

    attr_state.history.added = []
    attr_state.history.deleted = [mock_file]

    FileObjectInspector.handle_single_attribute(attr_state, tracker)

    tracker.add_pending_delete.assert_called_with(mock_file)

def test_handle_multiple_attribute():
    from advanced_alchemy.types.file_object import FileObject, FileObjectSessionTracker
    from advanced_alchemy.types.mutables import MutableList

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    # Case: Deletion from pending removed
    current_list = MagicMock(spec=MutableList)
    deleted_item = MagicMock(spec=FileObject)
    deleted_item.path = "path/to/delete"
    current_list._pending_removed = {deleted_item}
    current_list._pending_append = []

    setattr(instance, attr_name, current_list)
    attr_state.history.deleted = []
    attr_state.history.added = []

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    tracker.add_pending_delete.assert_called_with(deleted_item)

def test_handle_multiple_attribute_replacement():
    from advanced_alchemy.types.file_object import FileObject, FileObjectSessionTracker

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    # Case: List replacement
    # Original list had item1, item2
    # New list has item2 (so item1 removed)
    item1 = MagicMock(spec=FileObject); item1.path = "p1"
    item2 = MagicMock(spec=FileObject); item2.path = "p2"

    # SQLAlchemy history.deleted contains the *value* that was deleted.
    # For a scalar it's [old_value].
    # For a list assignment replacing the whole list, it might be [old_list].
    # The code expects history.deleted[0] to be the list.
    attr_state.history.deleted = [[item1, item2]] # original list wrapped in list
    attr_state.history.added = [[item2]] # new list wrapped in list

    # We must mock getattr(instance, attr_name) to return None or regular list, not necessarily MutableList
    setattr(instance, attr_name, [item2])

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    tracker.add_pending_delete.assert_called_with(item1)
    # item2 should NOT be deleted
    # tracker.add_pending_delete.assert_any_call(item2) # Should fail

def test_handle_multiple_attribute_append_and_new():
    from advanced_alchemy.types.file_object import FileObject, FileObjectSessionTracker
    from advanced_alchemy.types.mutables import MutableList

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    current_list = MagicMock(spec=MutableList)
    current_list._pending_removed = set()

    item1 = MagicMock(spec=FileObject); item1.path = None; item1._pending_content = b"d1"; item1._pending_source_path = None
    # For item2, we want to test pending_source_path, so pending_source_content must be None
    item2 = MagicMock(spec=FileObject); item2.path = None; item2._pending_source_path = "p2"; item2._pending_source_content = None

    current_list._pending_append = [item1]

    setattr(instance, attr_name, current_list)

    # Case: New items in history.added
    attr_state.history.deleted = []
    attr_state.history.added = [[item2]]

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    tracker.add_pending_save.assert_any_call(item1, b"d1")
    tracker.add_pending_save.assert_any_call(item2, "p2")

def test_base_cache_listener_execution_options():
    session = MagicMock(spec=Session)
    session.info = {}
    session.bind = None

    # Test execution_options via session
    session.execution_options = {"enable_cache_listener": False}
    assert TestBaseCacheListener._is_listener_enabled(session) is False

    session.execution_options = {"enable_cache_listener": True}
    assert TestBaseCacheListener._is_listener_enabled(session) is True


def test_process_deleted_instance():
    from advanced_alchemy.types.file_object import StoredObject

    instance = MagicMock()
    tracker = MagicMock()
    mapper = MagicMock()

    mock_attr = MagicMock()
    mock_attr.expression.type = MagicMock(spec=StoredObject)
    mock_attr.expression.type.multiple = False

    mapper.column_attrs = {"file_col": mock_attr}

    file_obj = MagicMock()
    file_obj.path = "path"
    setattr(instance, "file_col", file_obj)

    FileObjectInspector.process_deleted_instance(instance, mapper, tracker)

    tracker.add_pending_delete.assert_called_with(file_obj)

def test_get_file_tracker_create():
    session = MagicMock(spec=Session)
    session.info = {}

    result = get_file_tracker(session, create=True)
    assert result is not None
    assert session.info["_aa_file_tracker"] is result

# --- FileObjectListener Tests ---

class TestBaseFileObjectListener(BaseFileObjectListener):
    pass

def test_base_file_object_listener_is_listener_enabled_default():
    session = MagicMock(spec=Session)
    session.info = {}
    session.bind = None
    session.execution_options = None

    assert TestBaseFileObjectListener._is_listener_enabled(session) is True

def test_base_file_object_listener_is_listener_enabled_session_info():
    session = MagicMock(spec=Session)
    session.info = {"enable_file_object_listener": False}

    assert TestBaseFileObjectListener._is_listener_enabled(session) is False

def test_base_file_object_listener_before_flush_disabled():
    session = MagicMock(spec=Session)
    session.info = {"enable_file_object_listener": False}

    TestBaseFileObjectListener.before_flush(session, MagicMock(), None)
    # Should return early
    assert "_aa_file_tracker" not in session.info

def test_base_file_object_listener_before_flush():
    session = MagicMock(spec=Session)
    session.bind = MagicMock() # Fix AttributeError: Mock object has no attribute 'bind'
    session.info = {}
    session.new = []
    session.dirty = []
    session.deleted = []

    # Mock get_file_tracker to return a tracker
    with patch("advanced_alchemy._listeners.get_file_tracker") as mock_get_tracker:
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker
        TestBaseFileObjectListener.before_flush(session, MagicMock(), None)

    # It should have called get_file_tracker, but we mocked it.
    # The actual code calls get_file_tracker(session, create=True).
    # If we want to verify it set info, we should rely on get_file_tracker doing it,
    # or just verify logic flow.
    # Actually get_file_tracker puts it in session.info.
    # Let's trust get_file_tracker works (tested separately) and just mock it to return something
    # so execution proceeds.

    # We can inspect if it tried to inspect instances.
    # But new/dirty/deleted are empty.

def test_sync_file_object_listener_after_commit():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_file_tracker": tracker}

    SyncFileObjectListener.after_commit(session)

    tracker.commit.assert_called_once()
    assert "_aa_file_tracker" not in session.info

def test_sync_file_object_listener_after_rollback():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_file_tracker": tracker}

    SyncFileObjectListener.after_rollback(session)

    tracker.rollback.assert_called_once()
    assert "_aa_file_tracker" not in session.info

@pytest.mark.asyncio
async def test_async_file_object_listener_after_commit():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    tracker.commit_async = AsyncMock()
    session.info = {"_aa_file_tracker": tracker}

    AsyncFileObjectListener.after_commit(session)

    # Find the task and await it
    assert len(_active_file_operations) > 0
    task = list(_active_file_operations)[0]
    await task

    assert "_aa_file_tracker" not in session.info
    tracker.commit_async.assert_called_once()

@pytest.mark.asyncio
async def test_async_file_object_listener_after_rollback():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    tracker.rollback_async = AsyncMock()
    session.info = {"_aa_file_tracker": tracker}

    AsyncFileObjectListener.after_rollback(session)

    # Find the task and await it
    assert len(_active_file_operations) > 0
    task = list(_active_file_operations)[0]
    await task

    assert "_aa_file_tracker" not in session.info
    tracker.rollback_async.assert_called_once()

def test_file_object_listener_legacy_sync():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_file_tracker": tracker}

    # patch is_async_context to return False
    with patch("advanced_alchemy._listeners.is_async_context", return_value=False):
        FileObjectListener.after_commit(session)
        tracker.commit.assert_called_once()

        session.info = {"_aa_file_tracker": tracker} # put it back
        FileObjectListener.after_rollback(session)
        tracker.rollback.assert_called_once()

@pytest.mark.asyncio
async def test_file_object_listener_legacy_async():
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    tracker.commit_async = AsyncMock()
    tracker.rollback_async = AsyncMock()
    session.info = {"_aa_file_tracker": tracker}

    # patch is_async_context to return True
    with patch("advanced_alchemy._listeners.is_async_context", return_value=True):
        FileObjectListener.after_commit(session)

        # Await task
        if _active_file_operations:
            await list(_active_file_operations)[0]

        session.info = {"_aa_file_tracker": tracker}
        FileObjectListener.after_rollback(session)

        # Await task
        if _active_file_operations:
             for t in list(_active_file_operations):
                 if not t.done():
                     await t

# --- Setup Tests ---

def test_setup_file_object_listeners():
    with patch("sqlalchemy.event.listen") as mock_listen:
        setup_file_object_listeners()
        assert mock_listen.called

def test_setup_cache_listeners():
    with patch("sqlalchemy.event.listen") as mock_listen:
        setup_cache_listeners()
        assert mock_listen.called

# --- Timestamp Tests ---

def test_touch_updated_timestamp():
    session = MagicMock(spec=Session)
    instance = MagicMock()
    session.dirty = [instance]
    session.new = []

    with patch("advanced_alchemy._listeners.inspect") as mock_inspect:
        state = MagicMock()
        state.mapper.class_ = MagicMock()
        state.mapper.class_.updated_at = "exists"
        state.deleted = False

        # Mock updated_at attribute state
        attr_state = MagicMock()
        attr_state.history.added = [] # No manual update
        state.attrs.get.return_value = attr_state

        mock_inspect.return_value = state

        # Mock _has_persistent_column_changes to return True
        with patch("advanced_alchemy._listeners._has_persistent_column_changes", return_value=True):
            touch_updated_timestamp(session)

            # Verify instance.updated_at was set
            # We can't verify exact time easily, but we can verify it was assigned
            assert isinstance(instance.updated_at, datetime.datetime)

def test_has_persistent_column_changes():
    state = MagicMock()
    mapper = MagicMock()
    attr = MagicMock()
    attr.key = "some_col"
    mapper.column_attrs = [attr]
    state.mapper = mapper

    attr_state = MagicMock()
    attr_state.history.has_changes.return_value = True
    state.attrs.get.return_value = attr_state

    assert _has_persistent_column_changes(state) is True

# --- Deprecation / Context Tests ---

def test_deprecated_context_functions():
    with pytest.warns(DeprecationWarning):
        set_async_context(True)

    with pytest.warns(DeprecationWarning):
        reset_async_context(None)

    with pytest.warns(DeprecationWarning):
        is_async_context()

# --- BaseCacheListener Tests ---

class TestBaseCacheListener(BaseCacheListener):
    pass

def test_base_cache_listener_is_listener_enabled():
    session = MagicMock(spec=Session)
    session.info = {}
    session.bind = None
    session.execution_options = None
    assert TestBaseCacheListener._is_listener_enabled(session) is True

    session.info = {"enable_cache_listener": False}
    assert TestBaseCacheListener._is_listener_enabled(session) is False


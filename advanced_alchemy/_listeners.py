"""Application ORM configuration."""

import contextvars
import datetime
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import event

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import InstanceState, Session, UOWTransaction

    from advanced_alchemy.types.file_object import FileObjectSessionTracker, StorageRegistry
    from advanced_alchemy.types.mutables import MutableList

# Context variable to hold the session tracker instance for the current session context
_current_session_tracker: contextvars.ContextVar[Optional["FileObjectSessionTracker"]] = contextvars.ContextVar(
    "_current_session_tracker",
    default=None,
)


def _get_session_tracker(create: bool = True) -> Optional["FileObjectSessionTracker"]:
    from advanced_alchemy.types.file_object import FileObjectSessionTracker

    tracker = _current_session_tracker.get()
    if tracker is None and create:
        tracker = FileObjectSessionTracker()
        _current_session_tracker.set(tracker)
    return tracker


def _inspect_attribute_changes(
    state: "InstanceState[Any]",
    tracker: "FileObjectSessionTracker",
) -> None:
    """Inspects an instance's attributes for FileObject changes."""
    from sqlalchemy.inspection import inspect
    from sqlalchemy.orm.attributes import get_history

    from advanced_alchemy.types.file_object import FileObject, StoredObject

    mapper = inspect(state.class_)
    for attr_name, attr in mapper.column_attrs.items():
        # Check if the column type is our StoredObject
        if not isinstance(attr.expression.type, StoredObject):
            continue

        is_multiple = getattr(attr.expression.type, "multiple", False)
        history = get_history(state, attr_name)

        # Handle single FileObject attribute
        if not is_multiple:
            current_value: Optional[FileObject] = history.added[0] if history.added else None
            original_value: Optional[FileObject] = history.deleted[0] if history.deleted else None

            # If attribute was set or changed to a new FileObject with pending data
            if current_value and current_value.has_pending_data:
                # Access internal attributes for pending data
                data: Optional[Union[bytes, Path]] = getattr(current_value, "_pending_content", None) or getattr(
                    current_value, "_pending_source_path", None
                )
                if data:
                    tracker.add_pending_save(current_value, data)

            # If attribute was changed or cleared, mark the original for deletion
            if original_value and original_value.path:
                tracker.add_pending_delete(original_value)
            return

        current_list: Optional[MutableList[FileObject]] = history.added[0] if history.added else None

        if current_list:
            # Access internal attribute _pending_append
            pending_append = getattr(current_list, "_pending_append", [])
            for item in pending_append:
                if item.has_pending_data:
                    # Access internal attributes for pending data
                    data: Optional[Union[bytes, Path]] = getattr(item, "_pending_content", None) or getattr(  # type: ignore[no-redef]
                        item, "_pending_source_path", None
                    )
                    if data:
                        tracker.add_pending_save(item, data)

            # Access internal attribute _removed
            removed_items: set[FileObject] = getattr(current_list, "_removed", set["FileObject"]())
            for removed_item in removed_items:
                tracker.add_pending_delete(removed_item)

            # Access internal method _finalize_pending
            finalize_method = getattr(current_list, "_finalize_pending", None)
            if finalize_method:
                finalize_method()


class FileObjectSyncListener:
    @classmethod
    def before_flush(cls, session: "Session", flush_context: "UOWTransaction", instances: Optional[object]) -> None:
        """Track FileObject changes before a synchronous flush."""
        from sqlalchemy.inspection import inspect

        from advanced_alchemy.types.file_object import StoredObject

        config = getattr(session.bind, "engine_config", {}) if session.bind else {}
        if not config.get("enable_file_object_listener", False):
            return

        tracker = _get_session_tracker(create=True)
        if not tracker:
            return  # Should not happen if create=True

        # Inspect newly added instances
        for instance in session.new:
            state = inspect(instance)
            _inspect_attribute_changes(state, tracker)

        # Inspect modified instances
        for instance in session.dirty:
            state = inspect(instance)
            _inspect_attribute_changes(state, tracker)

        # Inspect deleted instances (mark their FileObjects for deletion)
        for instance in session.deleted:
            state = inspect(instance)
            mapper = inspect(state.class_)
            for attr_name, attr in mapper.column_attrs.items():
                if isinstance(attr.expression.type, StoredObject):
                    is_multiple = getattr(attr.expression.type, "multiple", False)
                    original_value = getattr(instance, attr_name)  # Get value before delete
                    if not is_multiple:
                        tracker.add_pending_delete(original_value)
                    else:
                        for item in original_value:
                            tracker.add_pending_delete(item)

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        """Process file operations after a successful synchronous commit."""
        tracker = _get_session_tracker(create=False)
        if tracker:
            try:
                tracker.commit()
            finally:
                # Ensure tracker is reset even if commit fails
                _current_session_tracker.set(None)

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        """Clean up pending file operations after a synchronous rollback."""
        tracker = _get_session_tracker(create=False)
        if tracker:
            try:
                tracker.rollback()
            finally:
                # Ensure tracker is reset even if rollback fails
                _current_session_tracker.set(None)


class FileObjectAsyncListener:
    @classmethod
    async def before_flush(
        cls,
        session: "AsyncSession",
        flush_context: Optional["UOWTransaction"],
        instances: Optional[object],
    ) -> None:
        """Track FileObject changes before an asynchronous flush."""
        from sqlalchemy.inspection import inspect

        from advanced_alchemy.types.file_object import StoredObject

        config = getattr(session.bind, "engine_config", {}) if session.bind else {}
        if not config.get("enable_file_object_listener", False):
            return

        tracker = _get_session_tracker(create=True)
        if not tracker:
            return  # Should not happen if create=True

        # Use run_sync within the async listener to inspect state, as inspection tools are often sync
        # This might be inefficient but necessary if state inspection triggers sync-only operations.
        # Alternatively, ensure all models/operations needed are loaded before this point.

        # Inspect newly added instances
        for instance in session.new:
            state = inspect(instance)
            _inspect_attribute_changes(state, tracker)

        # Inspect modified instances
        for instance in session.dirty:
            state = inspect(instance)
            _inspect_attribute_changes(state, tracker)

        # Inspect deleted instances
        for instance in session.deleted:
            state = inspect(instance)
            mapper = inspect(state.class_)
            for attr_name, attr in mapper.column_attrs.items():
                if isinstance(attr.expression.type, StoredObject):
                    is_multiple = getattr(attr.expression.type, "multiple", False)
                    # Need the state *before* deletion for original value, which might be tricky
                    # in async context if object attributes are unloaded. Relying on session.deleted
                    # state might be sufficient if values are retained until flush.
                    # Let's assume the object still holds the value here.
                    original_value = getattr(instance, attr_name)
                    if not is_multiple:
                        tracker.add_pending_delete(original_value)
                    else:
                        for item in original_value:
                            tracker.add_pending_delete(item)

    @classmethod
    async def after_commit(cls, session: "AsyncSession") -> None:
        """Process file operations after a successful asynchronous commit."""
        tracker = _get_session_tracker(create=False)
        if tracker:
            try:
                await tracker.commit_async()
            finally:
                _current_session_tracker.set(None)

    @classmethod
    async def after_rollback(cls, session: "AsyncSession") -> None:
        """Clean up pending file operations after an asynchronous rollback."""
        tracker = _get_session_tracker(create=False)
        if tracker:
            try:
                await tracker.rollback_async()
            finally:
                _current_session_tracker.set(None)


def setup_file_object_listeners(registry: Optional["StorageRegistry"] = None) -> None:  # noqa: ARG001
    """Registers the FileObject event listeners globally if not already registered."""
    # Import AsyncSession lazily to avoid circular dependency if called early
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    # Register synchronous listeners
    event.listen(Session, "before_flush", FileObjectSyncListener.before_flush)
    event.listen(Session, "after_commit", FileObjectSyncListener.after_commit)
    event.listen(Session, "after_rollback", FileObjectSyncListener.after_rollback)

    # Register asynchronous listeners
    # Ref: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-events-with-the-asyncio-extension
    # Use raw=True for async listeners on AsyncSession
    event.listen(AsyncSession, "before_flush", FileObjectAsyncListener.before_flush, raw=True)
    event.listen(AsyncSession, "after_commit", FileObjectAsyncListener.after_commit, raw=True)
    event.listen(AsyncSession, "after_rollback", FileObjectAsyncListener.after_rollback, raw=True)


# Existing listener (keep it)
def touch_updated_timestamp(session: "Session", *_: Any) -> None:
    """Set timestamp on update.

    Called from SQLAlchemy's
    :meth:`before_flush <sqlalchemy.orm.SessionEvents.before_flush>` event to bump the ``updated``
    timestamp on modified instances.

    Args:
        session: The sync :class:`Session <sqlalchemy.orm.Session>` instance that underlies the async
            session.
    """
    for instance in session.dirty:
        if hasattr(instance, "updated_at"):
            instance.updated_at = datetime.datetime.now(datetime.timezone.utc)

# ruff: noqa: BLE001, C901, PLR0915
"""Application ORM configuration."""

import asyncio
import contextvars
import datetime
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, cast

from sqlalchemy import event
from sqlalchemy.inspection import inspect

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, UOWTransaction

    from advanced_alchemy.types.file_object import FileObjectSessionTracker, StorageRegistry

_active_file_operations: set[asyncio.Task[Any]] = set()
"""Stores active file operations to prevent them from being garbage collected."""
# Context variable to hold the session tracker instance for the current session context
_current_session_tracker: contextvars.ContextVar[Optional["FileObjectSessionTracker"]] = contextvars.ContextVar(
    "_current_session_tracker",
    default=None,
)

# Context variable to track if we're in an async context
_is_async_context: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_is_async_context",
    default=False,
)

logger = logging.getLogger("advanced_alchemy")


def set_async_context(is_async: bool = True) -> Optional[contextvars.Token[bool]]:
    """Set the async context flag.

    Args:
        is_async: Whether the context is async.

    Returns:
        The token for the async context.
    """
    return _is_async_context.set(is_async)


def reset_async_context(token: contextvars.Token[bool]) -> None:
    """Reset the async context flag using the provided token."""
    _is_async_context.reset(token)


def is_async_context() -> bool:
    return _is_async_context.get()


def _get_session_tracker(create: bool = True) -> Optional["FileObjectSessionTracker"]:
    from advanced_alchemy.types.file_object import FileObjectSessionTracker

    tracker = _current_session_tracker.get()
    if tracker is None and create:
        tracker = FileObjectSessionTracker()
        _current_session_tracker.set(tracker)
    return tracker


def _inspect_attribute_changes(
    instance: Any,
    tracker: "FileObjectSessionTracker",
) -> None:
    from advanced_alchemy.types.file_object import FileObject, StoredObject
    from advanced_alchemy.types.mutables import MutableList

    state = inspect(instance)
    if not state:
        return
    mapper = state.mapper
    if not mapper:
        return

    for attr_name, attr in mapper.column_attrs.items():
        if not isinstance(attr.expression.type, StoredObject):
            continue

        is_multiple = getattr(attr.expression.type, "multiple", False)
        try:
            attr_state = state.attrs[attr_name]
        except KeyError:
            continue
        history = attr_state.history

        # Handle single FileObject attribute
        if not is_multiple:
            current_value: Optional[FileObject] = history.added[0] if history.added else None
            original_value: Optional[FileObject] = history.deleted[0] if history.deleted else None

            if current_value:
                pending_content = getattr(current_value, "_pending_source_content", None)
                pending_source_path = getattr(current_value, "_pending_source_path", None)
                if pending_content is not None:
                    tracker.add_pending_save(current_value, pending_content)
                elif pending_source_path is not None:
                    tracker.add_pending_save(current_value, pending_source_path)

            if original_value and original_value.path:
                tracker.add_pending_delete(original_value)
            continue

        # --- Multiple FileObjects Logic (v4 - Prioritize _pending_removed) ---
        items_to_delete: set[FileObject] = set()
        items_to_save: dict[FileObject, Any] = {}

        current_list_instance: Optional[MutableList[FileObject]] = getattr(instance, attr_name, None)
        original_list_from_history: Optional[MutableList[FileObject]] = history.deleted[0] if history.deleted else None
        current_list_from_history: Optional[MutableList[FileObject]] = history.added[0] if history.added else None

        # 1. Deletions from Mutations (Primary source: _pending_removed set)
        if isinstance(current_list_instance, MutableList):
            removed_items_internal: set[FileObject] = getattr(
                current_list_instance, "_pending_removed", set[FileObject]()
            )
            valid_removed_internal = {item for item in removed_items_internal if item and item.path}
            if valid_removed_internal:
                logger.debug(
                    "[Multiple-Mutation] Found %d valid items in internal _pending_removed set.",
                    len(valid_removed_internal),
                )
                items_to_delete.update(valid_removed_internal)

        # 2. Deletions from Replacements (Secondary source: history)
        if original_list_from_history:  # Indicates list replacement
            logger.debug("[Multiple-Replacement] Processing list replacement via history.")
            original_items_set = {item for item in original_list_from_history if item.path}
            current_items_set = (
                {item for item in current_list_from_history if item.path}
                if current_list_from_history
                else set[FileObject]()
            )
            removed_due_to_replacement = original_items_set - current_items_set
            if removed_due_to_replacement:
                logger.debug(
                    "[Multiple-Replacement] Found %d items removed via replacement.", len(removed_due_to_replacement)
                )
                items_to_delete.update(removed_due_to_replacement)

        # 3. Determine items to save
        # Saves from pending appends (Mutation or New)
        if isinstance(current_list_instance, MutableList):
            pending_append = getattr(current_list_instance, "_pending_append", [])
            if pending_append:
                logger.debug("[Multiple-Mutation] Found %d items in _pending_append list.", len(pending_append))
                for item in pending_append:
                    pending_content = getattr(item, "_pending_content", None)
                    pending_source_path = getattr(item, "_pending_source_path", None)
                    if pending_content is not None:
                        items_to_save[item] = pending_content
                    elif pending_source_path is not None:
                        items_to_save[item] = pending_source_path

        # Saves from newly added list items (New Instance or Replacement)
        if current_list_from_history:
            log_prefix = "[Multiple-New]" if not original_list_from_history else "[Multiple-Replacement]"
            logger.debug(
                "%s Checking current list from history (%d items) for pending saves.",
                log_prefix,
                len(current_list_from_history),
            )
            for item in current_list_from_history:
                pending_content = getattr(item, "_pending_source_content", None)
                pending_source_path = getattr(item, "_pending_source_path", None)
                if pending_content is not None and item not in items_to_save:
                    logger.debug("%s Found pending content for %r", log_prefix, item.filename)
                    items_to_save[item] = pending_content
                elif pending_source_path is not None and item not in items_to_save:
                    logger.debug("%s Found pending source path for %r", log_prefix, item.filename)
                    items_to_save[item] = pending_source_path

        # 4. Finalize MutableList state (if applicable)
        if isinstance(current_list_instance, MutableList):
            finalize_method = getattr(current_list_instance, "_finalize_pending", None)
            if finalize_method:
                logger.debug("[Multiple] Calling _finalize_pending on list instance.")
                finalize_method()

        # 5. Schedule all collected operations
        if items_to_delete:
            logger.debug("[Multiple] Scheduling %d items for deletion.", len(items_to_delete))
            for item_to_delete in items_to_delete:
                tracker.add_pending_delete(item_to_delete)

        if items_to_save:
            logger.debug("[Multiple] Scheduling %d items for saving.", len(items_to_save))
            for item_to_save, data in items_to_save.items():
                tracker.add_pending_save(item_to_save, data)


class FileObjectListener:  # pragma: no cover
    """Manages FileObject persistence actions during SQLAlchemy Session transactions.

    This listener hooks into the SQLAlchemy Session event lifecycle to automatically
    handle the saving and deletion of files associated with `FileObject` attributes
    mapped using the `StoredObject` type.

    How it Works:

    1.  **Event Registration (`setup_file_object_listeners`):**
        This listener's methods are registered to be called during specific phases
        of a Session's lifecycle (`before_flush`, `after_commit`, `after_rollback`).

    2.  **Tracking Changes (`before_flush`):**
        *   Before SQLAlchemy writes changes to the database (`flush`), this method
          is triggered.
        *   It inspects objects within the session that are:
            *   `session.new`: Newly added to the session.
            *   `session.dirty`: Modified within the session.
            *   `session.deleted`: Marked for deletion.
        *   For each object, it checks attributes mapped with `StoredObject`.
        *   Using SQLAlchemy's attribute history, it identifies:
            *   New `FileObject` instances (or those with pending content/paths) that need saving.
            *   Old `FileObject` instances that have been replaced or belong to deleted objects and need deleting.
        *   These intended file operations (saves and deletes) are recorded in a
          `FileObjectSessionTracker` specific to the current session context.

    3.  **Executing Operations (`after_commit`):**
        *   If the session transaction successfully commits, this method is called.
        *   It retrieves the `FileObjectSessionTracker` for the session.
        *   It instructs the tracker to execute all the pending file save and delete operations
          using the appropriate storage backend.
        *   The tracker is then cleared.

    4.  **Discarding Operations (`after_rollback`):**
        *   If the session transaction is rolled back, this method is called.
        *   It retrieves the tracker and instructs it to discard all pending operations,
          as the database changes they corresponded to were also discarded.
        *   The tracker is then cleared.

    **Synchronous vs. Asynchronous Handling:**
    *   The listener needs to know if it's operating within a standard synchronous
      SQLAlchemy Session or an `AsyncSession`.
    *   The `set_async_context(True)` function should be called before using an
      `AsyncSession` to set a flag (using `contextvars`).
    *   The `is_async_context()` function checks this flag.
    *   In `after_commit` and `after_rollback`, if `is_async_context()` is true,
      the file operations (tracker commit/rollback) are scheduled to run
      asynchronously using `asyncio.create_task`. Otherwise, they are executed
      synchronously.

    This ensures that file operations align correctly with the database transaction
    and are performed efficiently whether using sync or async sessions.
    """

    @classmethod
    def _is_listener_enabled(cls, session: "Session") -> bool:
        enable_listener = True  # Enabled by default

        session_info = getattr(session, "info", {})
        if "enable_file_object_listener" in session_info:
            return bool(session_info["enable_file_object_listener"])

        # Type hint for the list of potential option sources
        options_sources: list[Optional[Union[Callable[[], dict[str, Any]], dict[str, Any]]]] = []
        if session.bind:
            options_sources.append(getattr(session.bind, "execution_options", None))
            sync_engine = getattr(session.bind, "sync_engine", None)
            if sync_engine:
                options_sources.append(getattr(sync_engine, "execution_options", None))
        options_sources.append(getattr(session, "execution_options", None))

        for options_source in options_sources:
            if options_source is None:
                continue

            options: Optional[dict[str, Any]] = None
            if callable(options_source):
                try:
                    result = options_source()
                    if isinstance(result, dict):  # pyright: ignore
                        options = result
                except Exception as e:
                    logger.debug("Error calling execution_options source: %s", e)
            else:
                # If not None and not callable, assume it's the dict based on type hint
                options = options_source

            # Only perform the 'in' check if we successfully got a dictionary
            if options is not None and "enable_file_object_listener" in options:
                enable_listener = bool(options["enable_file_object_listener"])
                break

        return enable_listener

    @classmethod
    def _process_commit(cls, tracker: "FileObjectSessionTracker") -> None:
        """Processes pending operations after a commit."""
        try:
            if is_async_context():
                import asyncio

                async def _do_async_commit() -> None:
                    try:
                        await tracker.commit_async()
                    except Exception as e:
                        # Using %s for cleaner logging of exception causes
                        logger.debug("An error occurred while committing a file object: %s", e.__cause__)
                    finally:
                        _current_session_tracker.set(None)

                # Store the task reference, even if not awaited here
                t = asyncio.create_task(_do_async_commit())
                _active_file_operations.add(t)
                t.add_done_callback(lambda _: _active_file_operations.remove(t))
            else:
                tracker.commit()
                _current_session_tracker.set(None)
        except Exception:
            _current_session_tracker.set(None)

    @classmethod
    def _process_rollback(cls, tracker: "FileObjectSessionTracker") -> None:
        """Processes pending operations after a rollback."""
        try:
            if is_async_context():
                import asyncio

                async def _do_async_rollback() -> None:
                    try:
                        await tracker.rollback_async()
                    except Exception as e:
                        logger.debug("An error occurred during async FileObject rollback: %s", e.__cause__)
                    finally:
                        _current_session_tracker.set(None)

                # Store the task reference, even if not awaited here
                t = asyncio.create_task(_do_async_rollback())
                _active_file_operations.add(t)
                t.add_done_callback(lambda _: _active_file_operations.remove(t))
            else:
                tracker.rollback()
                _current_session_tracker.set(None)
        except Exception:
            _current_session_tracker.set(None)

    @classmethod
    def before_flush(cls, session: "Session", flush_context: "UOWTransaction", instances: Optional[object]) -> None:
        """Track FileObject changes before a flush."""
        from advanced_alchemy.types.file_object import StoredObject

        if not cls._is_listener_enabled(session):
            return

        tracker = _get_session_tracker(create=True)
        if not tracker:
            return

        for instance in session.new:
            _inspect_attribute_changes(instance, tracker)

        for instance in session.dirty:
            _inspect_attribute_changes(instance, tracker)

        for instance in session.deleted:
            state = inspect(instance)
            if not state:
                continue
            mapper = state.mapper
            if not mapper:
                continue

            # Avoid inspecting if no StoredObject columns exist
            has_stored_object = any(
                isinstance(attr.expression.type, StoredObject) for attr in mapper.column_attrs.values()
            )
            if not has_stored_object:
                continue

            tracker = cls._process_pending_operations(tracker, instance, mapper)

    @classmethod
    def _process_pending_operations(
        cls, tracker: "FileObjectSessionTracker", instance: Any, mapper: Any
    ) -> "FileObjectSessionTracker":
        from advanced_alchemy.types.file_object import FileObject, StoredObject
        from advanced_alchemy.types.mutables import MutableList

        for attr_name, attr in mapper.column_attrs.items():
            if isinstance(attr.expression.type, StoredObject):
                is_multiple = getattr(attr.expression.type, "multiple", False)
                original_value: Any = getattr(instance, attr_name, None)
                if original_value is None:
                    continue

                if not is_multiple:
                    tracker.add_pending_delete(original_value)
                elif isinstance(original_value, (list, MutableList)):
                    for item in original_value:  # pyright: ignore
                        tracker.add_pending_delete(cast("FileObject", item))
        return tracker

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        """Process file operations after a successful commit."""
        tracker = _get_session_tracker(create=False)
        if tracker:
            cls._process_commit(tracker)

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        """Clean up pending file operations after a rollback."""
        tracker = _get_session_tracker(create=False)
        if tracker:
            cls._process_rollback(tracker)


def setup_file_object_listeners(registry: Optional["StorageRegistry"] = None) -> None:  # noqa: ARG001
    """Registers the FileObject event listeners globally."""
    from sqlalchemy.event import contains
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session

    listeners = {
        "before_flush": FileObjectListener.before_flush,
        "after_commit": FileObjectListener.after_commit,
        "after_rollback": FileObjectListener.after_rollback,
    }

    # Register for sync Session
    for event_name, listener_func in listeners.items():
        if not contains(Session, event_name, listener_func):  # type: ignore[arg-type]
            event.listen(Session, event_name, listener_func)  # type: ignore[arg-type]

    async_listeners_to_register = {
        "after_commit": FileObjectListener.after_commit,
        "after_rollback": FileObjectListener.after_rollback,
    }
    for event_name, listener_func in async_listeners_to_register.items():
        if hasattr(AsyncSession, event_name) and not contains(AsyncSession, event_name, listener_func):
            event.listen(AsyncSession, event_name, listener_func)

    set_async_context(False)


# Existing listener (keep it)
def touch_updated_timestamp(session: "Session", *_: Any) -> None:  # pragma: no cover
    """Set timestamp on update.

    Called from SQLAlchemy's
    :meth:`before_flush <sqlalchemy.orm.SessionEvents.before_flush>` event to bump the ``updated``
    timestamp on modified instances.

    Args:
        session: The sync :class:`Session <sqlalchemy.orm.Session>` instance that underlies the async
            session.
    """
    for instance in session.dirty:
        state = inspect(instance)
        if not state or not hasattr(state.mapper.class_, "updated_at"):
            continue
        updated_at_attr = state.attrs.get("updated_at")
        if updated_at_attr and not updated_at_attr.history.has_changes():
            instance.updated_at = datetime.datetime.now(datetime.timezone.utc)

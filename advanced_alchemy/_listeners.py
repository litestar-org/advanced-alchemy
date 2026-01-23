# ruff: noqa: BLE001, C901, PLR0915
"""Application ORM configuration."""

import asyncio
import contextvars
import datetime
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, cast

from sqlalchemy import event
from sqlalchemy.inspection import inspect

from advanced_alchemy.utils.deprecation import warn_deprecation
from advanced_alchemy.utils.sync_tools import is_async_context as _is_async_context_util

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session, UOWTransaction, scoped_session
    from sqlalchemy.orm.state import InstanceState

    from advanced_alchemy.cache import CacheManager
    from advanced_alchemy.types.file_object import FileObjectSessionTracker, StorageRegistry

_active_file_operations: set[asyncio.Task[Any]] = set()
"""Stores active file operations to prevent them from being garbage collected."""
_active_cache_operations: set[asyncio.Task[Any]] = set()
"""Stores active cache invalidation operations to prevent them from being garbage collected."""

_FILE_TRACKER_KEY = "_aa_file_tracker"
_CACHE_TRACKER_KEY = "_aa_cache_tracker"

# Context variable to track if we're in an async context (legacy compatibility)
_is_async_context: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_is_async_context",
    default=False,
)


def get_file_tracker(
    session: "Session",
    create: bool = True,
) -> Optional["FileObjectSessionTracker"]:
    """Get or create a file session tracker for the session.

    The tracker is stored on session.info to ensure proper scoping
    per session instance and avoid ContextVar collisions.

    Args:
        session: The SQLAlchemy session instance.
        create: Whether to create a new tracker if one doesn't exist.

    Returns:
        The file tracker or None if not available.
    """
    from advanced_alchemy.types.file_object import FileObjectSessionTracker

    tracker: Optional[FileObjectSessionTracker] = session.info.get(_FILE_TRACKER_KEY)
    if tracker is None and create:
        raise_on_error = session.info.get("file_object_raise_on_error", True)
        tracker = FileObjectSessionTracker(raise_on_error=raise_on_error)
        session.info[_FILE_TRACKER_KEY] = tracker
    return tracker


def _get_session_tracker(
    create: bool = True, session: Optional["Session"] = None
) -> Optional["FileObjectSessionTracker"]:
    """Legacy helper for session tracker retrieval.

    Args:
        create: Whether to create a new tracker if one doesn't exist.
        session: The SQLAlchemy session instance.

    Returns:
        The file tracker or None if not available.
    """
    if session is None:
        return None
    return get_file_tracker(session, create=create)


logger = logging.getLogger("advanced_alchemy")


def set_async_context(is_async: bool = True) -> None:  # noqa: ARG001
    """Set the async context flag.

    .. deprecated:: 2.0.0
        This function is no longer needed as listeners are now explicitly sync or async.
    """
    warn_deprecation(
        version="2.0.0",
        deprecated_name="set_async_context",
        kind="function",
        removal_in="3.0.0",
        info="Listeners are now explicitly sync or async, so this context flag is no longer needed.",
    )


def reset_async_context(token: Any) -> None:  # noqa: ARG001
    """Reset the async context flag using the provided token.

    .. deprecated:: 2.0.0
        This function is no longer needed as listeners are now explicitly sync or async.
    """
    warn_deprecation(
        version="2.0.0",
        deprecated_name="reset_async_context",
        kind="function",
        removal_in="3.0.0",
        info="Listeners are now explicitly sync or async, so this context flag is no longer needed.",
    )


def is_async_context() -> bool:
    """Check if we're in an async context.

    .. deprecated:: 2.0.0
        This function is no longer needed as listeners are now explicitly sync or async.
    """
    warn_deprecation(
        version="2.0.0",
        deprecated_name="is_async_context",
        kind="function",
        removal_in="3.0.0",
        alternative="advanced_alchemy.utils.sync_tools.is_async_context",
        info="This function in `_listeners` is deprecated. Use the utility in `sync_tools` or relying on explicit listener classes.",
    )
    return _is_async_context_util()


class FileObjectInspector:
    """Utilities for inspecting FileObject attribute changes."""

    @staticmethod
    def inspect_instance(instance: Any, tracker: "FileObjectSessionTracker") -> None:
        """Inspect an instance for changes in FileObject attributes."""
        from advanced_alchemy.types.file_object import StoredObject

        state = inspect(instance)
        if not state:
            return
        mapper = state.mapper
        if not mapper:
            return

        for attr_name, attr in mapper.column_attrs.items():
            if not isinstance(attr.expression.type, StoredObject):
                continue

            try:
                attr_state = state.attrs[attr_name]
            except KeyError:
                continue

            is_multiple = getattr(attr.expression.type, "multiple", False)
            if not is_multiple:
                FileObjectInspector.handle_single_attribute(attr_state, tracker)
            else:
                FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    @staticmethod
    def handle_single_attribute(attr_state: Any, tracker: "FileObjectSessionTracker") -> None:
        """Handle inspection of a single FileObject attribute."""
        from advanced_alchemy.types.file_object import FileObject

        history = attr_state.history
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

    @staticmethod
    def handle_multiple_attribute(
        instance: Any,
        attr_name: str,
        attr_state: Any,
        tracker: "FileObjectSessionTracker",
    ) -> None:
        """Handle inspection of multiple FileObject attributes (MutableList)."""
        from advanced_alchemy.types.file_object import FileObject
        from advanced_alchemy.types.mutables import MutableList

        history = attr_state.history
        items_to_delete: set[FileObject] = set()
        items_to_save: dict[FileObject, Any] = {}

        current_list_instance: Optional[MutableList[FileObject]] = getattr(instance, attr_name, None)
        original_list_from_history: Optional[MutableList[FileObject]] = (
            history.deleted[0] if history.deleted else None
        )
        current_list_from_history: Optional[MutableList[FileObject]] = history.added[0] if history.added else None

        # 1. Deletions from Mutations (Primary source: _pending_removed set)
        if isinstance(current_list_instance, MutableList):
            removed_items_internal: set[FileObject] = getattr(
                current_list_instance,
                "_pending_removed",
                set[FileObject](),
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
                    "[Multiple-Replacement] Found %d items removed via replacement.",
                    len(removed_due_to_replacement),
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

    @staticmethod
    def process_deleted_instance(
        instance: Any,
        mapper: Any,
        tracker: "FileObjectSessionTracker",
    ) -> None:
        """Process an instance that is being deleted from the session."""
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


def _inspect_attribute_changes(
    instance: Any,
    tracker: "FileObjectSessionTracker",
) -> None:
    FileObjectInspector.inspect_instance(instance, tracker)


class BaseFileObjectListener:  # pragma: no cover
    """Base class for FileObject event listeners."""

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
    def before_flush(cls, session: "Session", flush_context: "UOWTransaction", instances: Optional[object]) -> None:
        """Track FileObject changes before a flush."""
        from advanced_alchemy.types.file_object import StoredObject

        if not cls._is_listener_enabled(session):
            return

        tracker = get_file_tracker(session, create=True)
        if not tracker:
            return

        for instance in session.new:
            FileObjectInspector.inspect_instance(instance, tracker)

        for instance in session.dirty:
            FileObjectInspector.inspect_instance(instance, tracker)

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

            FileObjectInspector.process_deleted_instance(instance, mapper, tracker)


class SyncFileObjectListener(BaseFileObjectListener):
    """Synchronous FileObject listener."""

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        """Process file operations after a successful commit."""
        tracker = get_file_tracker(session, create=False)
        if tracker:
            tracker.commit()
            session.info.pop(_FILE_TRACKER_KEY, None)

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        """Clean up pending file operations after a rollback."""
        tracker = get_file_tracker(session, create=False)
        if tracker:
            tracker.rollback()
            session.info.pop(_FILE_TRACKER_KEY, None)


class AsyncFileObjectListener(BaseFileObjectListener):
    """Asynchronous FileObject listener."""

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        """Process file operations after a successful commit."""
        tracker = get_file_tracker(session, create=False)
        if not tracker:
            return

        async def _do_async_commit() -> None:
            try:
                await tracker.commit_async()
            except Exception as e:
                # Using %s for cleaner logging of exception causes
                logger.debug("An error occurred while committing a file object: %s", e.__cause__)
            finally:
                session.info.pop(_FILE_TRACKER_KEY, None)

        # Store the task reference, even if not awaited here
        t = asyncio.create_task(_do_async_commit())
        _active_file_operations.add(t)
        t.add_done_callback(lambda _: _active_file_operations.remove(t))

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        """Clean up pending file operations after a rollback."""
        tracker = get_file_tracker(session, create=False)
        if not tracker:
            return

        async def _do_async_rollback() -> None:
            try:
                await tracker.rollback_async()
            except Exception as e:
                logger.debug("An error occurred during async FileObject rollback: %s", e.__cause__)
            finally:
                session.info.pop(_FILE_TRACKER_KEY, None)

        # Store the task reference, even if not awaited here
        t = asyncio.create_task(_do_async_rollback())
        _active_file_operations.add(t)
        t.add_done_callback(lambda _: _active_file_operations.remove(t))


class FileObjectListener(SyncFileObjectListener, AsyncFileObjectListener):  # type: ignore[misc]
    """Legacy FileObject listener that handles both sync and async via runtime checks.

    .. deprecated:: 2.0.0
        Use :class:`SyncFileObjectListener` or :class:`AsyncFileObjectListener` instead.
    """

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        if is_async_context():
            AsyncFileObjectListener.after_commit(session)
        else:
            SyncFileObjectListener.after_commit(session)

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        if is_async_context():
            AsyncFileObjectListener.after_rollback(session)
        else:
            SyncFileObjectListener.after_rollback(session)


def setup_file_object_listeners(registry: Optional["StorageRegistry"] = None) -> None:  # noqa: ARG001
    """Registers the FileObject event listeners globally.

    .. deprecated:: 2.0.0
        This function registers listeners globally on the Session class.
        Prefer using scoped listeners via SQLAlchemyConfig.
    """
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


class CacheInvalidationTracker:
    """Tracks pending cache invalidations for a session transaction.

    This tracker collects entity invalidations during a transaction and
    processes them only after a successful commit. On rollback, the
    pending invalidations are discarded.

    Note:
        Model version bumps are also deferred to commit to ensure rollbacks
        don't invalidate list caches when no DB change occurred.
    """

    __slots__ = ("_cache_manager", "_pending_invalidations", "_pending_model_bumps")

    def __init__(self, cache_manager: "CacheManager") -> None:
        self._cache_manager = cache_manager
        self._pending_invalidations: list[tuple[str, Any, Optional[str]]] = []
        self._pending_model_bumps: set[str] = set()

    def add_invalidation(self, model_name: str, entity_id: Any, bind_group: Optional[str] = None) -> None:
        """Queue an entity for cache invalidation.

        The actual invalidation and model version bump are deferred until
        commit() is called, ensuring rollbacks don't affect the cache.

        Args:
            model_name: The model/table name.
            entity_id: The entity's primary key value.
            bind_group: Optional routing group for multi-master configurations.
                When provided, only the cache entry for that bind_group is
                invalidated.
        """
        self._pending_invalidations.append((model_name, entity_id, bind_group))
        # Queue model version bump for list query invalidation (deferred to commit)
        self._pending_model_bumps.add(model_name)

    def commit(self) -> None:
        """Process all pending invalidations after successful commit."""
        # First bump model versions for list query invalidation
        for model_name in self._pending_model_bumps:
            self._cache_manager.bump_model_version_sync(model_name)
        self._pending_model_bumps.clear()

        # Then invalidate individual entities
        for model_name, entity_id, bind_group in self._pending_invalidations:
            self._cache_manager.invalidate_entity_sync(model_name, entity_id, bind_group)
        self._pending_invalidations.clear()

    def rollback(self) -> None:
        """Discard pending invalidations on rollback."""
        self._pending_invalidations.clear()
        self._pending_model_bumps.clear()

    async def commit_async(self) -> None:
        """Process all pending invalidations after successful commit (async-safe).

        This method performs cache I/O using the CacheManager async APIs so that
        dogpile backends (often sync network clients) never block the event loop.
        """
        # First bump model versions for list query invalidation
        for model_name in self._pending_model_bumps:
            await self._cache_manager.bump_model_version_async(model_name)
        self._pending_model_bumps.clear()

        # Then invalidate individual entities
        for model_name, entity_id, bind_group in self._pending_invalidations:
            await self._cache_manager.invalidate_entity_async(model_name, entity_id, bind_group)
        self._pending_invalidations.clear()


def get_cache_tracker(
    session: "Union[Session, AsyncSession, scoped_session[Session], async_scoped_session[AsyncSession]]",
    cache_manager: Optional["CacheManager"] = None,
    create: bool = True,
) -> Optional["CacheInvalidationTracker"]:
    """Get or create a cache invalidation tracker for the session.

    The tracker is stored on session.info to ensure proper scoping
    per session instance and avoid ContextVar collisions.

    Args:
        session: The SQLAlchemy session instance (sync or async, including scoped sessions).
        cache_manager: The CacheManager instance (required if create=True).
        create: Whether to create a new tracker if one doesn't exist.

    Returns:
        The cache tracker or None if not available.
    """
    tracker: Optional[CacheInvalidationTracker] = session.info.get(_CACHE_TRACKER_KEY)
    if tracker is None and create and cache_manager is not None:
        tracker = CacheInvalidationTracker(cache_manager)
        session.info[_CACHE_TRACKER_KEY] = tracker
    return tracker


class BaseCacheListener:
    """Base class for cache invalidation event listeners."""

    @classmethod
    def _is_listener_enabled(cls, session: "Session") -> bool:
        """Check if cache listener is enabled for this session."""
        enable_listener = True

        session_info = getattr(session, "info", {})
        if "enable_cache_listener" in session_info:
            return bool(session_info["enable_cache_listener"])

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
                options = options_source

            if options is not None and "enable_cache_listener" in options:
                enable_listener = bool(options["enable_cache_listener"])
                break

        return enable_listener


class SyncCacheListener(BaseCacheListener):
    """Synchronous cache invalidation listener."""

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        """Process cache invalidations after a successful commit."""
        if not cls._is_listener_enabled(session):
            return

        tracker = get_cache_tracker(session, create=False)
        if tracker:
            tracker.commit()
            session.info.pop(_CACHE_TRACKER_KEY, None)

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        """Discard pending cache invalidations after a rollback."""
        tracker = get_cache_tracker(session, create=False)
        if tracker:
            tracker.rollback()
            session.info.pop(_CACHE_TRACKER_KEY, None)


class AsyncCacheListener(BaseCacheListener):
    """Asynchronous cache invalidation listener."""

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        """Process cache invalidations after a successful commit."""
        if not cls._is_listener_enabled(session):
            return

        tracker = get_cache_tracker(session, create=False)
        if tracker:
            task = asyncio.create_task(tracker.commit_async())
            _active_cache_operations.add(task)
            task.add_done_callback(_active_cache_operations.discard)
            session.info.pop(_CACHE_TRACKER_KEY, None)

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        """Discard pending cache invalidations after a rollback."""
        tracker = get_cache_tracker(session, create=False)
        if tracker:
            tracker.rollback()
            session.info.pop(_CACHE_TRACKER_KEY, None)


class CacheInvalidationListener(SyncCacheListener, AsyncCacheListener):  # type: ignore[misc]
    """Legacy cache invalidation listener that handles both sync and async via runtime checks.

    .. deprecated:: 2.0.0
        Use :class:`SyncCacheListener` or :class:`AsyncCacheListener` instead.
    """

    @classmethod
    def after_commit(cls, session: "Session") -> None:
        if is_async_context():
            AsyncCacheListener.after_commit(session)
        else:
            SyncCacheListener.after_commit(session)

    @classmethod
    def after_rollback(cls, session: "Session") -> None:
        if is_async_context():
            AsyncCacheListener.after_rollback(session)
        else:
            SyncCacheListener.after_rollback(session)


def setup_cache_listeners() -> None:
    """Register cache invalidation event listeners globally.

    .. deprecated:: 2.0.0
        This function registers listeners globally on the Session class.
        Prefer using scoped listeners via SQLAlchemyConfig.
    """
    from sqlalchemy.event import contains
    from sqlalchemy.orm import Session

    listeners = {
        "after_commit": CacheInvalidationListener.after_commit,
        "after_rollback": CacheInvalidationListener.after_rollback,
    }

    for event_name, listener_func in listeners.items():
        if not contains(Session, event_name, listener_func):
            event.listen(Session, event_name, listener_func)

    logger.debug("Cache invalidation listeners registered")


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
        if not state or not hasattr(state.mapper.class_, "updated_at") or state.deleted or instance in session.new:
            continue
        updated_at_attr = state.attrs.get("updated_at")
        if not updated_at_attr or updated_at_attr.history.added:
            # Respect explicit user assignments such as manual overrides or import routines
            continue

        if _has_persistent_column_changes(state, skip_keys={"updated_at"}):
            instance.updated_at = datetime.datetime.now(datetime.timezone.utc)


def _has_persistent_column_changes(
    state: "InstanceState[Any]",
    *,
    skip_keys: "Optional[set[str]]" = None,
) -> bool:
    """Check if any mapped column (excluding ``skip_keys``) has modifications pending flush."""
    if skip_keys is None:
        skip_keys = set()

    mapper = state.mapper
    for attr in mapper.column_attrs:
        if attr.key in skip_keys:
            continue
        attr_state = state.attrs.get(attr.key)
        if attr_state is not None and attr_state.history.has_changes():
            return True
    return False

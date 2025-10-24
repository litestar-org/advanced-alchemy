# ruff: noqa: UP037
"""FileObject session change tracking and commit/rollback coordination.

This tracker collects FileObject save/delete intentions during a database
transaction and applies them on commit, or cleans up saved files on rollback.

Behavior summary:
- Sync commit: processes saves sequentially, then deletes; logs failures with
  stack traces and re-raises; ignores ``FileNotFoundError`` on delete; stops on
  the first save error; clears internal state only on full success.
- Async commit: executes saves and deletes concurrently via ``asyncio.gather``;
  logs each failure with ``exc_info``; raises single exceptions directly or
  multiple exceptions as ``ExceptionGroup``; lets ``BaseException`` (e.g.,
  ``asyncio.CancelledError``) bubble; attempts deletes even if a save fails;
  clears state only on full success.
- Rollback (sync/async): deletes only files saved during this transaction;
  ignores ``FileNotFoundError``; logs and re-raises errors (as ``ExceptionGroup``
  for multiple async failures); clears state after processing.
"""

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any, Union

if sys.version_info >= (3, 11):
    from builtins import ExceptionGroup
else:
    from exceptiongroup import ExceptionGroup  # type: ignore[import-not-found,unused-ignore]

if TYPE_CHECKING:
    from pathlib import Path

    from advanced_alchemy.types.file_object import FileObject

logger = logging.getLogger("advanced_alchemy")


class FileObjectSessionTracker:
    """Track pending FileObject saves/deletes for a single transaction.

    This class records pending changes and coordinates applying them on commit
    or undoing saved files on rollback. It does not manage database
    transactions; it assumes callers invoke ``commit*``/``rollback*`` at the
    appropriate points in the application transaction lifecycle.
    """

    def __init__(self, raise_on_error: bool = False) -> None:
        """Initialize empty tracking state.

        Args:
            raise_on_error: If True, raise exceptions on file operation failures.
                           If False, log warnings and continue (legacy behavior).

        Internal structures:
        - ``pending_saves``: ``FileObject -> data`` to be saved on commit
        - ``pending_deletes``: ``FileObject`` instances to delete on commit
        - ``_saved_in_transaction``: successfully saved objects used for
          selective cleanup on rollback
        """
        self.raise_on_error = raise_on_error
        # Stores objects that have pending data to be saved on commit.
        # Maps FileObject -> data source (bytes or Path)
        self.pending_saves: "dict[FileObject, Union[bytes, Path]]" = {}
        # Stores objects that should be deleted from storage on commit.
        self.pending_deletes: "set[FileObject]" = set()
        # Stores objects that were successfully saved within this transaction,
        # needed for rollback cleanup.
        self._saved_in_transaction: "set[FileObject]" = set()

    def add_pending_save(self, obj: "FileObject", data: "Union[bytes, Path]") -> None:
        """Mark a FileObject for saving on commit.

        Also cancels any prior pending delete for ``obj`` within this
        transaction.
        """
        self.pending_saves[obj] = data
        # If this object was previously marked for deletion, unmark it.
        self.pending_deletes.discard(obj)

    def add_pending_delete(self, obj: "FileObject") -> None:
        """Mark a FileObject for deletion on commit.

        Cancels any prior pending save for ``obj``. The object is only added to
        the delete set if it has a non-empty ``path`` (i.e., exists in storage).
        """
        # If this object was pending save, unmark it.
        self.pending_saves.pop(obj, None)
        # Only add to pending deletes if it actually exists in storage (has a path)
        if obj.path:
            self.pending_deletes.add(obj)

    def commit(self) -> None:
        """Apply pending changes after a successful database commit (sync).

        Processing order and error handling:
        - Saves are processed first, sequentially. If a save fails:
          * With raise_on_error=True: logged as ERROR and re-raised
          * With raise_on_error=False: logged as WARNING, processing continues
        - Deletes are processed next. ``FileNotFoundError`` is ignored; other
          exceptions follow same raise_on_error behavior.
        - State is only cleared if no errors occurred.
        """
        for obj, data in self.pending_saves.items():
            try:
                obj.save(data)
                self._saved_in_transaction.add(obj)
            except Exception:
                if self.raise_on_error:
                    logger.exception("error saving file for object %s", obj)
                    raise
                # Legacy behavior: log as warning, not error
                logger.warning("error saving file for object %s", obj, exc_info=True)

        for obj in self.pending_deletes:
            try:
                obj.delete()
            except FileNotFoundError:
                # Ignore if the file is already gone
                pass
            except Exception:
                if self.raise_on_error:
                    logger.exception("error deleting file for object %s", obj)
                    raise
                logger.warning("error deleting file for object %s", obj, exc_info=True)

        self.clear()

    async def commit_async(self) -> None:
        """Apply pending changes after a successful database commit (async).

        Execution and error handling:
        - Saves and deletes are executed concurrently via ``asyncio.gather``.
        - For each operation that fails with an ``Exception``:
          * With raise_on_error=True: logged as ERROR, collected for raising
          * With raise_on_error=False: logged as WARNING, processing continues
        - ``BaseException`` instances (e.g., ``asyncio.CancelledError``) are
          re-raised immediately regardless of raise_on_error setting.
        - After processing, if raise_on_error=True and any ``Exception`` occurred,
          a single exception is raised directly, or multiple exceptions are raised
          as an ``ExceptionGroup``.
        - State is only cleared if no errors occurred.
        """
        save_items: "list[tuple[FileObject, Union[bytes, Path]]]" = list(self.pending_saves.items())
        delete_items: "list[FileObject]" = list(self.pending_deletes)

        save_results: "list[Any]" = await asyncio.gather(
            *(obj.save_async(data) for obj, data in save_items),
            return_exceptions=True,
        )
        delete_results: "list[Any]" = await asyncio.gather(
            *(obj.delete_async() for obj in delete_items),
            return_exceptions=True,
        )

        errors: list[Exception] = []

        for (obj, _data), result in zip(save_items, save_results):
            if isinstance(result, BaseException):
                if isinstance(result, Exception):
                    if self.raise_on_error:
                        logger.error(
                            "error saving file for object %s",
                            obj,
                            exc_info=(type(result), result, result.__traceback__),
                        )
                    else:
                        # Legacy behavior: warning level
                        logger.warning(
                            "error saving file for object %s",
                            obj,
                            exc_info=(type(result), result, result.__traceback__),
                        )
                    errors.append(result)
                else:
                    # BaseException (e.g., CancelledError) - always raise
                    raise result
            else:
                self._saved_in_transaction.add(obj)

        for obj_to_delete, result in zip(delete_items, delete_results):
            if isinstance(result, FileNotFoundError):
                continue
            if isinstance(result, BaseException):
                if isinstance(result, Exception):
                    if self.raise_on_error:
                        logger.error(
                            "error deleting file %s",
                            obj_to_delete.path or obj_to_delete,
                            exc_info=(type(result), result, result.__traceback__),
                        )
                    else:
                        logger.warning(
                            "error deleting file %s",
                            obj_to_delete.path or obj_to_delete,
                            exc_info=(type(result), result, result.__traceback__),
                        )
                    errors.append(result)
                else:
                    raise result

        # Raise ExceptionGroup if multiple errors occurred, single error otherwise
        if errors and self.raise_on_error:
            if len(errors) == 1:
                raise errors[0]
            msg = "multiple FileObject operation failures"
            raise ExceptionGroup(msg, errors)

        # Only clear if no errors occurred
        if not errors:
            self.clear()

    def rollback(self) -> None:
        """Delete files saved in the current transaction (sync rollback).

        Only files recorded in ``_saved_in_transaction`` (i.e., saved by this
        tracker during the current transaction) are candidates for deletion.
        ``FileNotFoundError`` is ignored; other exceptions are logged (with
        traceback) and re-raised. Tracking state is cleared afterward.
        """
        for obj in self._saved_in_transaction:
            if obj.path:
                try:
                    obj.delete()
                except FileNotFoundError:
                    # Ignore if the file is already gone (shouldn't happen often here)
                    pass
                except Exception:
                    logger.exception("error deleting file during rollback %s", obj.path or obj)
                    raise
        self.clear()

    async def rollback_async(self) -> None:
        """Delete files saved in the current transaction (async rollback).

        Uses asyncio.gather to attempt all deletions concurrently, preventing
        partial rollback failures. ``FileNotFoundError`` is ignored; other
        exceptions are logged and collected. If multiple exceptions occur, they
        are raised as an ``ExceptionGroup``; single exceptions are raised
        directly. Tracking state is cleared afterward.
        """
        objects_to_delete = [obj for obj in self._saved_in_transaction if obj.path]
        if not objects_to_delete:
            self.clear()
            return

        delete_results = await asyncio.gather(
            *(obj.delete_async() for obj in objects_to_delete),
            return_exceptions=True,
        )

        errors: list[Exception] = []
        for obj, result in zip(objects_to_delete, delete_results):
            if isinstance(result, FileNotFoundError):
                continue
            if isinstance(result, BaseException):
                if isinstance(result, Exception):
                    logger.error(
                        "error deleting file during rollback %s",
                        obj.path or obj,
                        exc_info=(type(result), result, result.__traceback__),
                    )
                    errors.append(result)
                else:
                    # Propagate BaseExceptions like CancelledError
                    raise result

        self.clear()
        if errors:
            if len(errors) == 1:
                raise errors[0]
            msg = "multiple FileObject rollback failures"
            raise ExceptionGroup(msg, errors)

    def clear(self) -> None:
        """Clear all internal tracking state.

        Empties ``pending_saves`` and ``pending_deletes``, and resets
        ``_saved_in_transaction``. Typically invoked after a successful
        commit/rollback or before reusing the tracker.
        """
        self.pending_saves.clear()
        self.pending_deletes.clear()
        self._saved_in_transaction.clear()

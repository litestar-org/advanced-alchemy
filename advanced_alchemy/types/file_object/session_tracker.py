# ruff: noqa: UP037
"""Application ORM configuration."""

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
    """Tracks FileObject changes within a single session transaction."""

    def __init__(self, raise_on_error: bool = False) -> None:
        """Initialize empty tracking state.

        Args:
            raise_on_error: If True, raise exceptions on file operation failures.
                            If False, log warnings and continue.

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
        """Mark a FileObject for saving."""
        self.pending_saves[obj] = data
        # If this object was previously marked for deletion, unmark it.
        self.pending_deletes.discard(obj)

    def add_pending_delete(self, obj: "FileObject") -> None:
        """Mark a FileObject for deletion."""
        # If this object was pending save, unmark it.
        self.pending_saves.pop(obj, None)
        # Only add to pending deletes if it actually exists in storage (has a path)
        if obj.path:
            self.pending_deletes.add(obj)

    def commit(self) -> None:
        """Process pending saves and deletes after a successful commit."""
        for obj, data in self.pending_saves.items():
            try:
                obj.save(data)
                self._saved_in_transaction.add(obj)
            except Exception:
                if self.raise_on_error:
                    logger.exception("error saving file for object %s", obj)
                    raise
                logger.warning("error saving file for object %s", obj, exc_info=True)

        for obj in self.pending_deletes:
            try:
                obj.delete()
            except FileNotFoundError:
                pass
            except Exception:
                if self.raise_on_error:
                    logger.exception("error deleting file for object %s", obj)
                    raise
                logger.warning("error deleting file for object %s", obj, exc_info=True)

        self.clear()

    async def commit_async(self) -> None:
        """Process pending saves and deletes after a successful commit."""

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

        if errors and self.raise_on_error:
            if len(errors) == 1:
                raise errors[0]
            msg = "multiple FileObject operation failures"
            raise ExceptionGroup(msg, errors)
        if not errors:
            self.clear()

    def rollback(self) -> None:
        """Clean up files saved during a transaction that is being rolled back."""
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
        """Clean up files saved during a transaction that is being rolled back."""
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
        """Clear the tracker's state."""
        self.pending_saves.clear()
        self.pending_deletes.clear()
        self._saved_in_transaction.clear()

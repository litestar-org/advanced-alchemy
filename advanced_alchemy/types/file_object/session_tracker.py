# ruff: noqa: UP037
"""Application ORM configuration."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from pathlib import Path

    from advanced_alchemy.types.file_object import FileObject

logger = logging.getLogger("advanced_alchemy")


class FileObjectSessionTracker:
    """Tracks FileObject changes within a single session transaction."""

    def __init__(self) -> None:
        """Initialize the tracker."""
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
            except Exception as e:  # noqa: BLE001
                logger.warning("Error saving file for object %s: %s", obj, e.__cause__)
        for obj in self.pending_deletes:
            try:
                obj.delete()
            except FileNotFoundError:
                # Ignore if the file is already gone (shouldn't happen often here)
                pass
            except Exception as e:  # noqa: BLE001
                logger.warning("Error deleting file for object %s: %s", obj, e.__cause__)
        self.clear()

    async def commit_async(self) -> None:
        """Process pending saves and deletes after a successful commit."""
        save_tasks: list[Awaitable[Any]] = []
        for obj, data in self.pending_saves.items():
            save_tasks.append(obj.save_async(data))
            self._saved_in_transaction.add(obj)

        delete_tasks: list[Awaitable[Any]] = [obj.delete_async() for obj in self.pending_deletes]

        # Run save and delete tasks concurrently
        save_results = await asyncio.gather(*save_tasks, return_exceptions=True)
        delete_results = await asyncio.gather(*delete_tasks, return_exceptions=True)

        # Process save results (log errors)
        for result, (obj, _data) in zip(save_results, self.pending_saves.items()):
            if isinstance(result, Exception):
                logger.warning("Error saving file for object %s: %s", obj, result.__cause__)
        # Process delete results (log errors, ignore FileNotFoundError)
        for result, obj_to_delete in zip(delete_results, self.pending_deletes):
            if isinstance(result, FileNotFoundError):
                continue
            if isinstance(result, Exception):
                logger.warning("Error deleting file %s: %s", obj_to_delete.path, result.__cause__)

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
                except Exception as e:  # noqa: BLE001
                    logger.warning("Error deleting file during rollback %s: %s", obj.path, e.__cause__)
        self.clear()

    async def rollback_async(self) -> None:
        """Clean up files saved during a transaction that is being rolled back."""
        rollback_delete_tasks: list[Awaitable[Any]] = []
        objects_to_delete_on_rollback: list[FileObject] = []
        # Only delete files that were actually saved *during this transaction*
        for obj in self._saved_in_transaction:
            if obj.path:
                rollback_delete_tasks.append(obj.delete_async())
                objects_to_delete_on_rollback.append(obj)

        for task, obj_to_delete in zip(rollback_delete_tasks, objects_to_delete_on_rollback):
            try:
                await task
            except FileNotFoundError:
                # Ignore if the file is already gone (shouldn't happen often here)
                pass
            except Exception as e:  # noqa: BLE001
                logger.warning("Error deleting file during rollback %s: %s", obj_to_delete.path, e.__cause__)

        self.clear()

    def clear(self) -> None:
        """Clear the tracker's state."""
        self.pending_saves.clear()
        self.pending_deletes.clear()
        self._saved_in_transaction.clear()

# ruff: noqa: TRY301, SLF001, C901, PLR1702
import contextlib
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import event
from sqlalchemy.orm import ColumnProperty, InstanceState, Mapper, Session, SessionTransaction
from sqlalchemy.orm.base import PASSIVE_OFF

if TYPE_CHECKING:
    # Imports from advanced_alchemy
    from collections.abc import Coroutine

    from advanced_alchemy.types.file_object.base import StorageBackend
    from advanced_alchemy.types.file_object.data_type import StoredObject
    from advanced_alchemy.types.file_object.file import FileObject
    from advanced_alchemy.types.file_object.registry import StorageRegistry


def _extract_paths_and_keys(
    file_objects: "Optional[Union[FileObject, list[FileObject]]]", storage_key: str
) -> "list[tuple[str, str]]":
    """Extract paths and storage keys from FileObject(s).

    Args:
        file_objects: A single FileObject or a list of FileObjects
        storage_key: The storage key to extract paths and keys for

    Returns:
        A list of tuples containing (path, storage_key)
    """
    if file_objects is None:
        return []
    objects = file_objects if isinstance(file_objects, list) else [file_objects]
    # Ensure it's a FileObject and has a path before tracking
    return [(fo.target_filename, storage_key) for fo in objects if fo and fo.target_filename]


class FileObjectSessionTracker:
    """Manages automatic cleanup of old files in storage via SQLAlchemy events.

    This tracker listens for ORM events (updates, deletes) and records
    file paths that should be deleted from the storage backend upon successful
    transaction commit.

    Note: This tracker focuses on **cleanup** of old/replaced/deleted files.
          It does **not** automatically handle:
            - Uploading new files (must be done explicitly before commit).
            - Deleting newly uploaded files if the transaction rolls back
              (must be handled in the calling code's exception handling).
    """

    mapped_entities: "dict[type[Any], list[tuple[str, str, bool]]]" = {}
    _storages: "Optional[StorageRegistry]" = None
    # Flag to control deletion of new files on rollback
    _handle_rollback: bool = False

    @classmethod
    def _set_registry(cls, registry: "StorageRegistry") -> None:
        cls._storages = registry

    @classmethod
    def _get_backend(cls, storage_key: str) -> "StorageBackend":
        if cls._storages is None:
            # This should not happen if setup is called correctly
            msg = "FileObjectSessionTracker not initialized with storage registry. Call setup_file_object_listeners()."
            raise RuntimeError(msg)
        backend = cls._storages.get_backend(storage_key)
        if not backend:
            msg = f"Storage backend '{storage_key}' not found in registry."
            raise RuntimeError(msg)
        return backend

    @classmethod
    def _get_session_ops_dict(cls, session: "Session") -> "dict[str, set[str]]":
        attr_name = "_aa_files_to_delete_on_commit"
        if not hasattr(session, attr_name):
            setattr(session, attr_name, {})  # Initialize as dict
        return getattr(session, attr_name)  # type: ignore[no-any-return]

    @classmethod
    def _get_rollback_ops_dict(cls, session: "Session") -> "dict[str, set[str]]":
        attr_name = "_aa_new_files_to_delete_on_rollback"
        if not hasattr(session, attr_name):
            setattr(session, attr_name, {})  # Initialize as dict
        return getattr(session, attr_name)  # type: ignore[no-any-return]

    @classmethod
    def _add_new_op_for_rollback(cls, session: "Session", path: str, storage_key: str) -> None:
        ops_dict = cls._get_rollback_ops_dict(session)
        ops_dict.setdefault(storage_key, set()).add(path)

    @classmethod
    def _add_old_op(cls, session: "Session", path: str, storage_key: str) -> None:
        ops_dict = cls._get_session_ops_dict(session)
        # Get the set for the key, initializing if necessary
        ops_dict.setdefault(storage_key, set()).add(path)

    @classmethod
    def _clear_session_ops(cls, session: "Session") -> None:
        attr_name = "_aa_files_to_delete_on_commit"
        if hasattr(session, attr_name):
            delattr(session, attr_name)

    @classmethod
    def _clear_rollback_ops(cls, session: "Session") -> None:
        attr_name = "_aa_new_files_to_delete_on_rollback"
        if hasattr(session, attr_name):
            delattr(session, attr_name)

    # --- Event Listeners ---
    @classmethod
    def _mapper_configured(cls, mapper: "Mapper[Any]", class_: "type[Any]") -> None:
        from advanced_alchemy.types.file_object.data_type import StoredObject
        from advanced_alchemy.types.mutables import MutableList

        for prop in mapper.iterate_properties:
            if isinstance(prop, ColumnProperty) and isinstance(prop.columns[0].type, StoredObject):
                column_type = prop.columns[0].type
                storage_key = column_type.storage_key
                is_multiple = column_type.multiple
                # Associate MutableList *if* multiple is True
                if is_multiple:
                    with contextlib.suppress(TypeError):
                        # Associate MutableList with the mapped attribute for change tracking
                        MutableList.associate_with_attribute(getattr(class_, prop.key))
                cls.mapped_entities.setdefault(class_, []).append((prop.key, storage_key, is_multiple))

    @classmethod
    def _after_configured(cls) -> None:
        for entity in cls.mapped_entities:
            event.listen(entity, "before_update", cls._before_update, raw=True)
            event.listen(entity, "after_delete", cls._after_delete, raw=True)

    @classmethod
    def _before_update(cls, mapper: "Mapper[Any]", connection: "Any", state: "InstanceState[Any]") -> None:
        from advanced_alchemy.types.mutables import MutableList

        session = state.session
        if not session:
            return

        tracked_props = cls.mapped_entities.get(mapper.class_, [])
        for key, storage_key, is_multiple in tracked_props:
            history = state.get_history(key, passive=PASSIVE_OFF)
            # Track files replaced in the history
            deleted_paths = _extract_paths_and_keys(history.deleted, storage_key)  # type: ignore
            for path, skey in deleted_paths:
                cls._add_old_op(session, path, skey)
            # If multiple, also check the _removed list from MutableList
            if is_multiple:
                current_value = state.dict.get(key)
                if isinstance(current_value, MutableList) and hasattr(current_value, "_removed"):  # pyright: ignore
                    # Extract paths from the items manually removed from the list
                    # Ignore protected access and potential type issues from generic list
                    removed_paths = _extract_paths_and_keys(current_value._removed, storage_key)  # pyright: ignore
                    for path, skey in removed_paths:
                        cls._add_old_op(session, path, skey)

    @classmethod
    def _after_delete(cls, mapper: "Mapper[Any]", connection: "Any", state: "InstanceState[Any]") -> None:
        session = state.session
        if not session:
            return

        tracked_props = cls.mapped_entities.get(mapper.class_, [])
        for key, storage_key, _ in tracked_props:  # is_multiple not needed here
            # Get the value directly from the state before it's gone
            value = state.dict.get(key)
            # _extract_paths_and_keys handles both single FileObject and lists
            paths_to_delete = _extract_paths_and_keys(value, storage_key)
            for path, skey in paths_to_delete:
                cls._add_old_op(session, path, skey)

    @classmethod
    def _get_stored_object_type(cls, mapper: "Mapper[Any]", key: str) -> Optional["StoredObject"]:
        from advanced_alchemy.types.file_object.data_type import StoredObject

        prop = mapper.get_property(key)
        if isinstance(prop, ColumnProperty) and isinstance(prop.columns[0].type, StoredObject):
            return prop.columns[0].type  # pyright: ignore
        return None

    @classmethod
    def _save_pending_file(cls, session: Session, file_object: "FileObject", storage_key: str) -> Optional[Exception]:
        from collections.abc import Iterable, Iterator
        from pathlib import Path

        from sqlalchemy.orm import object_mapper

        mapper = object_mapper(file_object)
        stored_object_type = cls._get_stored_object_type(mapper, storage_key)
        if not stored_object_type:
            return RuntimeError(f"Could not find StoredObject type for {storage_key}")

        data_bytes: Optional[bytes] = None

        try:
            # 1. Load data into memory (bytes)
            if file_object._pending_content is not None:  # pyright: ignore
                source = file_object._pending_content  # pyright: ignore
                if isinstance(source, bytes):
                    data_bytes = source
                elif isinstance(source, (Iterator, Iterable)):
                    data_bytes = b"".join(source)  # type: ignore
                elif hasattr(source, "read"):
                    read_data = source.read()  # pyright: ignore
                    data_bytes = read_data.encode() if isinstance(read_data, str) else read_data  # pyright: ignore

                else:
                    return TypeError(f"Unsupported sync data type for pending content: {type(source)}")
            elif file_object._pending_source_path is not None:  # pyright: ignore
                source_path = Path(file_object._pending_source_path)  # pyright: ignore
                if not source_path.is_file():
                    msg = f"Source path does not exist: {source_path}"
                    raise FileNotFoundError(msg)
                data_bytes = source_path.read_bytes()
            else:
                return RuntimeError("No pending content/path found.")

            if data_bytes is None:
                return RuntimeError("Failed to load data bytes.")

            # 2. Run Validators
            for validator in stored_object_type.validators:  # pyright: ignore
                validator.validate(file_object, data_bytes, key=storage_key)  # pyright: ignore

            # 3. Run Processors
            processed_data_bytes = data_bytes  # pyright: ignore
            for processor in stored_object_type.processors:  # pyright: ignore
                result = processor.process(file_object, processed_data_bytes, key=storage_key)  # pyright: ignore
                if result is None:
                    msg = f"Processor {type(processor).__name__} returned None."  # pyright: ignore
                    raise RuntimeError(msg)
                processed_data_bytes = result  # pyright: ignore

            # 4. Call FileObject.save with the final processed bytes
            if not file_object.backend:
                file_object.backend = cls._get_backend(storage_key)
            file_object.save(data=processed_data_bytes)  # pyright: ignore

            # Track successful save for potential rollback
            if file_object.target_filename:
                cls._add_new_op_for_rollback(session, file_object.target_filename, storage_key)
            # NOTE: Clearing pending attributes is now handled within file_object.save()
        except Exception as e:  # noqa: BLE001
            return e  # Return the exception to the caller
        return None  # Success

    @classmethod
    async def _save_pending_file_async(
        cls, session: Session, file_object: "FileObject", storage_key: str
    ) -> Optional[Exception]:
        import asyncio
        from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
        from pathlib import Path

        from sqlalchemy.orm import object_mapper

        mapper = object_mapper(file_object)
        stored_object_type = cls._get_stored_object_type(mapper, storage_key)
        if not stored_object_type:
            return RuntimeError(f"Could not find StoredObject type for {storage_key}")

        data_bytes: Optional[bytes] = None

        try:
            # 1. Load data into memory (bytes)
            if file_object._pending_content is not None:  # pyright: ignore
                source = file_object._pending_content  # pyright: ignore
                if isinstance(source, bytes):
                    data_bytes = source
                elif isinstance(source, (AsyncIterator, AsyncIterable)):
                    data_bytes = b"".join([chunk async for chunk in source])
                elif isinstance(source, (Iterator, Iterable)):
                    data_bytes = b"".join(source)  # type: ignore
                elif hasattr(source, "read"):
                    read_data = source.read()  # pyright: ignore
                    if asyncio.iscoroutine(read_data):  # pyright: ignore
                        read_data = await read_data
                    # Use ternary operator for conciseness
                    data_bytes = read_data.encode() if isinstance(read_data, str) else read_data  # pyright: ignore
                else:
                    return TypeError(f"Unsupported data type for pending content: {type(source)}")  # pyright: ignore
            elif file_object._pending_source_path is not None:  # pyright: ignore
                source_path = Path(file_object._pending_source_path)  # pyright: ignore
                if not source_path.is_file():
                    msg = f"Source path does not exist: {source_path}"
                    raise FileNotFoundError(msg)
                # Use asyncio.to_thread for reading path bytes
                data_bytes = await asyncio.to_thread(source_path.read_bytes)
            else:
                msg = "No pending content/path found."
                raise RuntimeError(msg)

            if data_bytes is None:
                return RuntimeError("Failed to load data bytes.")

            # 2. Run Validators (sync)
            for validator in stored_object_type.validators:
                validator.validate(file_object, data_bytes, key=storage_key)  # pyright: ignore

            # 3. Run Processors (sync)
            processed_data_bytes = data_bytes  # pyright: ignore
            for processor in stored_object_type.processors:  # pyright: ignore
                result = processor.process(file_object, processed_data_bytes, key=storage_key)  # pyright: ignore
                if result is None:
                    msg = f"Processor {type(processor).__name__} returned None."  # pyright: ignore
                    raise RuntimeError(msg)
                processed_data_bytes = result  # pyright: ignore

            # 4. Call FileObject.save_async with the final processed bytes
            if not file_object.backend:
                file_object.backend = cls._get_backend(storage_key)
            await file_object.save_async(data=processed_data_bytes)  # pyright: ignore

            # Track successful save for potential rollback
            if file_object.target_filename:
                cls._add_new_op_for_rollback(session, file_object.target_filename, storage_key)

            # NOTE: Clearing pending attributes is now handled within file_object.save_async()

        except Exception as e:  # noqa: BLE001
            return e
        return None

    @classmethod
    def _before_flush(cls, session: "Session", flush_context: Any, instances: Any) -> None:
        from sqlalchemy.orm import attributes

        from advanced_alchemy.types.mutables import MutableList

        errors: list[Exception] = []
        # Combine new and dirty objects for checking
        objects_to_check = list(session.new) + list(session.dirty)

        for instance in objects_to_check:
            # Use attributes.instance_state for clarity
            instance_state: InstanceState[Any] = attributes.instance_state(instance)
            instance_mapper: Optional[Mapper[Any]] = instance_state.mapper
            if not instance_mapper or instance_mapper.class_ not in cls.mapped_entities:
                continue

            tracked_props = cls.mapped_entities[instance_mapper.class_]
            for key, storage_key, is_multiple in tracked_props:
                current_value = instance_state.dict.get(key)
                if not current_value:
                    continue

                if is_multiple:
                    if isinstance(current_value, (list, MutableList)):
                        # Ignore type errors for item within generic loop

                        for item in current_value:  # pyright: ignore
                            # Use the public property to check for pending data
                            if item and item.has_pending_data:  # pyright: ignore
                                err = cls._save_pending_file(session, item, storage_key)  # pyright: ignore
                                if err:
                                    errors.append(err)
                # Use the public property to check for pending data
                elif current_value and current_value.has_pending_data:
                    err = cls._save_pending_file(session, current_value, storage_key)  # pyright: ignore
                    if err:
                        errors.append(err)

        if errors:
            # Consolidate errors and raise
            # Note: This will likely cause the flush to fail and transaction to rollback.
            # Consider logging errors instead if partial success is desired.
            error_messages = "; ".join(str(e) for e in errors)
            msg = f"Errors saving pending files before flush: {error_messages}"
            raise RuntimeError(msg)

    @classmethod
    async def _before_flush_async(cls, session: "Session", flush_context: Any, instances: Any) -> None:
        import asyncio

        from sqlalchemy.orm import attributes

        from advanced_alchemy.types.mutables import MutableList

        aws: list[Coroutine[Any, Any, Optional[Exception]]] = []
        objects_to_check = list(session.new) + list(session.dirty)

        for instance in objects_to_check:
            # Use attributes.instance_state for clarity
            instance_state: InstanceState[Any] = attributes.instance_state(instance)
            instance_mapper: Optional[Mapper[Any]] = instance_state.mapper
            if not instance_mapper or instance_mapper.class_ not in cls.mapped_entities:
                continue

            tracked_props = cls.mapped_entities[instance_mapper.class_]
            for key, storage_key, is_multiple in tracked_props:
                current_value = instance_state.dict.get(key)
                if not current_value:
                    continue

                if is_multiple:
                    if isinstance(current_value, (list, MutableList)):
                        # Ignore type errors for item within generic loop
                        # Schedule async save if needed using the property
                        aws.extend(  # pyright: ignore
                            cls._save_pending_file_async(session, item, storage_key)  # pyright: ignore
                            for item in current_value  # pyright: ignore
                            if item and item.has_pending_data  # pyright: ignore
                        )
                # Schedule async save if needed using the property
                elif current_value and current_value.has_pending_data:
                    aws.append(cls._save_pending_file_async(session, current_value, storage_key))  # pyright: ignore

        if aws:
            # Ignore potential type issues with gathered results in generic context
            results = await asyncio.gather(*aws, return_exceptions=True)  # pyright: ignore
            errors = [res for res in results if isinstance(res, Exception)]  # pyright: ignore
            if errors:
                error_messages = "; ".join(str(e) for e in errors)
                msg = f"Errors saving pending files before async flush: {error_messages}"
                raise RuntimeError(msg)

    @classmethod
    def _after_commit(cls, session: "Session") -> None:
        # First, clear the rollback list, as the commit succeeded
        cls._clear_rollback_ops(session)

        # Now, handle deletions of old files
        ops_dict = cls._get_session_ops_dict(session).copy()
        if not ops_dict:
            cls._clear_session_ops(session)
            return
        # Perform deletions synchronously, grouped by storage key
        for storage_key, paths_set in ops_dict.items():
            if not paths_set:
                continue
            backend = cls._get_backend(storage_key)
            backend.delete_from_storage(list(paths_set))

        cls._clear_session_ops(session)

    @classmethod
    async def _after_commit_async(cls, session: "Session") -> None:
        # First, clear the rollback list, as the commit succeeded
        cls._clear_rollback_ops(session)

        # Now, handle deletions of old files
        ops_dict = cls._get_session_ops_dict(session).copy()
        if not ops_dict:
            cls._clear_session_ops(session)
            return

        for storage_key, paths_set in ops_dict.items():
            if not paths_set:
                continue
            backend = cls._get_backend(storage_key)
            await backend.delete_from_storage_async(list(paths_set))

        cls._clear_session_ops(session)

    @classmethod
    def _after_soft_rollback(cls, session: "Session", previous_transaction: "Optional[SessionTransaction]") -> None:
        # Clear the set for files to be deleted on commit (as commit didn't happen)
        cls._clear_session_ops(session)

        # Handle deletion of newly saved files if configured
        if cls._handle_rollback:
            ops_dict = cls._get_rollback_ops_dict(session).copy()
            if ops_dict:
                # Perform deletions synchronously
                for storage_key, paths_set in ops_dict.items():
                    if not paths_set:
                        continue
                    backend = cls._get_backend(storage_key)
                    backend.delete_from_storage(list(paths_set))

        # Always clear the rollback tracking list after rollback handling
        cls._clear_rollback_ops(session)

    @classmethod
    async def _after_soft_rollback_async(cls, session: "Session") -> None:
        # Clear the set for files to be deleted on commit
        cls._clear_session_ops(session)

        # Handle deletion of newly saved files if configured
        if cls._handle_rollback:
            ops_dict = cls._get_rollback_ops_dict(session).copy()
            if ops_dict:
                # Perform deletions asynchronously
                for storage_key, paths_set in ops_dict.items():
                    if not paths_set:
                        continue
                    backend = cls._get_backend(storage_key)
                    await backend.delete_from_storage_async(list(paths_set))

        # Always clear the rollback tracking list after rollback handling
        cls._clear_rollback_ops(session)

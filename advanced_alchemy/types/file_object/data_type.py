import hashlib
from typing import Any, Callable, Optional, Union

from sqlalchemy import TypeDecorator

from advanced_alchemy.types.file_object.base import (
    AsyncDataLike,
    FileObject,
    FileProcessor,
    FileValidator,
    PathLike,
    StorageBackend,
    storages,
)
from advanced_alchemy.types.json import JsonB
from advanced_alchemy.utils.sync_tools import async_


def default_checksum_handler(value: bytes) -> str:
    """Calculate the checksum of the file.

    Args:
        value: The file data to calculate the checksum of

    Returns:
        The checksum of the file
    """
    return hashlib.md5(value, usedforsecurity=False).hexdigest()


class StorageBucket(TypeDecorator[FileObject]):
    """Custom SQLAlchemy type for storing file metadata and handling uploads.

    Stores file metadata in JSONB and handles file validation, processing,
    and storage operations through a configured storage backend.
    """

    impl = JsonB
    cache_ok = True

    # Default settings
    default_expires_in: int = 3600  # 1 hour

    backend: "StorageBackend"
    compute_checksum: bool
    checksum_handler: Callable[[bytes], str]
    validators: list[FileValidator]
    processors: list[FileProcessor]

    def __init__(
        self,
        backend: Union[str, StorageBackend],
        compute_checksum: bool = True,
        checksum_handler: Optional[Callable[[bytes], str]] = None,
        default_expires_in: Optional[int] = None,
        validators: Optional[list[FileValidator]] = None,
        processors: Optional[list[FileProcessor]] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize StorageBucket type.

        Args:
            backend: Storage backend to use
            compute_checksum: Whether to compute the checksum of the file
            checksum_handler: Callable to compute the checksum of the file
            default_expires_in: Default expiration time for signed URLs
            validators: List of FileValidator instances to run before processing/storage.
            processors: List of FileProcessor instances to run before storage.
            *args: Additional positional arguments for TypeDecorator
            **kwargs: Additional keyword arguments for TypeDecorator

        """
        super().__init__(*args, **kwargs)
        if isinstance(backend, str):
            self.backend = storages.get_backend(backend)
        else:
            storages.register_backend(backend.backend, backend)
            self.backend = backend
        self.compute_checksum = compute_checksum
        self.checksum_handler = checksum_handler or default_checksum_handler
        self.default_expires_in = default_expires_in or self.default_expires_in
        self.validators = validators or []  # New
        self.processors = processors or []  # New

    def process_bind_param(
        self, value: "Optional[Union[FileObject, dict[str, Any]]]", dialect: Any
    ) -> "Optional[dict[str, Any]]":
        """Convert FileInfo object/dict to database JSON format.

        Note: This method expects an already processed FileInfo or its dict representation.
              Use handle_upload() or handle_upload_async() for processing raw uploads.

        Returns:
            A dictionary representing the file metadata, or None if the input value is None.
        """
        if value is None:
            return None
        if isinstance(value, FileObject):
            return value.to_dict()
        # Assuming it's already a dict suitable for JSONB
        return value

    def process_result_value(self, value: "Optional[dict[str, Any]]", dialect: Any) -> "Optional[FileObject]":
        """Convert database JSON format back to FileInfo object.

        Returns:
            FileInfo object or None.
        """
        if value is None:
            return None

        # Inject the backend into the file info - crucial for functionality
        value["backend"] = self.backend
        return FileObject.from_dict(value)

    # --- New Upload Handling Methods ---

    def handle_upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        metadata: Optional[dict[str, Any]] = None,
        storage_path: Optional[PathLike] = None,
    ) -> FileObject:
        """Handles synchronous validation, processing, and storage of file data.

        Args:
            file_data: Raw file data as bytes.
            filename: Original filename.
            content_type: MIME type of the file.
            metadata: Optional additional metadata to store with the file.
            storage_path: Optional specific path/key to store the file under in the backend.
                          If None, defaults to `filename`.

        Returns:
            FileInfo object representing the stored file.

        """
        # 1. Create a temporary FileObject (or just use a dict internally)
        #    FileObject is currently dictionary-like, so we can use it.
        #    We pass file_data separately to validators/processors for now.
        file_object = FileObject(
            filename=filename,
            content_type=content_type,
            size=len(file_data),
            # Can add initial metadata here if needed
        )
        processed_data = file_data  # Start with original data

        # 2. Run Validators
        for validator in self.validators:
            # Assuming validate might need raw data, pass it. Adjust if not needed.
            validator.validate(file_object)  # Pass data if method signature requires it

        # 3. Run Processors
        for processor in self.processors:
            # Processors might modify file_object metadata or potentially the data itself
            # Adjust signature if processor needs to return modified data
            processor.process(file_object)  # Pass/return data if method signature requires it
            # Example if processor modifies data: processed_data = processor.process(file_object, processed_data)

        # 4. Compute Checksum (on potentially processed data)
        file_checksum = self.checksum_handler(processed_data) if self.compute_checksum else None

        # 5. Determine storage path
        final_storage_path = storage_path if storage_path is not None else file_object.get("filename", filename)

        # 6. Merge metadata
        final_metadata = {**file_object.get("metadata", {}), **(metadata or {})}
        if file_checksum:
            final_metadata["checksum"] = file_checksum  # Add checksum to metadata if computed

        # 7. Call Backend Storage (Sync)
        # Use the potentially updated filename/content_type from file_object
        file_info = self.backend.put(
            path=final_storage_path,
            data=processed_data,
            content_type=file_object.get("content_type", content_type),
            metadata=final_metadata,
        )

        # Ensure checksum is in the final FileInfo if computed
        if file_checksum and not file_info.checksum:
            file_info.checksum = file_checksum

        return file_info

    async def handle_upload_async(
        self,
        file_data: AsyncDataLike,  # Accepts various async data types
        filename: str,
        content_type: str,
        metadata: Optional[dict[str, Any]] = None,
        storage_path: Optional[PathLike] = None,
    ) -> FileObject:
        """Handles asynchronous validation, processing, and storage of file data.

        Args:
            file_data: Raw file data as bytes, async iterator, etc.
            filename: Original filename.
            content_type: MIME type of the file.
            metadata: Optional additional metadata to store with the file.
            storage_path: Optional specific path/key to store the file under in the backend.
                          If None, defaults to `filename`.

        Returns:
            FileInfo object representing the stored file.

        """
        # Note: Checksum calculation on async streams might require reading
        # the entire stream into memory or a temporary file first, unless
        # the backend calculates it during upload (like S3).
        # For simplicity, we'll assume checksum is handled by the backend or
        # we read the stream if needed, but this can be complex.

        # Currently, validators and processors are sync. If they become async,
        # you'd need to await them here, possibly using asyncio.gather.
        # For now, we assume they run quickly or we handle potential blocking.

        # If data is bytes, we can handle it synchronously before async put
        if isinstance(file_data, bytes):
            # Run sync validation/processing directly on bytes
            return self.handle_upload(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                metadata=metadata,
                storage_path=storage_path,
            )

        # --- Handling for async streams/iterables ---
        # Create FileObject - Size might be unknown for streams initially
        file_object = FileObject(
            filename=filename,
            content_type=content_type,
            size=0,  # Size might be unknown for streams
        )

        # Run Validators (Sync for now) - They likely won't have access to full stream data easily
        for validator in self.validators:
            # Note: Validators like MaxSizeValidator won't work well on streams
            # without reading the whole stream first.
            await async_(validator.validate)(file_object)

        # Run Processors (Sync for now)
        for processor in self.processors:
            await async_(processor.process)(file_object)

        # Determine storage path
        final_storage_path = storage_path if storage_path is not None else file_object.get("filename", filename)

        # Merge metadata
        final_metadata = {**file_object.get("metadata", {}), **(metadata or {})}

        # Call Backend Storage (Async)
        # Checksum handling for async streams is omitted for brevity - depends on backend/strategy.
        return await self.backend.put_async(
            path=final_storage_path,
            data=file_data,  # Pass the async data directly
            content_type=file_object.get("content_type", content_type),
            metadata=final_metadata,
        )
        # Note: FileInfo size might be updated by the backend after upload

    def put_file(
        self, file_data: bytes, filename: str, content_type: str, metadata: "Optional[dict[str, Any]]" = None
    ) -> "FileObject":
        """Simple wrapper for handle_upload for backward compatibility or direct use.

        Args:
            file_data: Raw file data as bytes.
            filename: Original filename.
            content_type: MIME type.
            metadata: Additional metadata.

        Returns:
            FileInfo object.
        """
        # Delegates to the new handler which includes validation/processing
        return self.handle_upload(file_data=file_data, filename=filename, content_type=content_type, metadata=metadata)

    async def put_file_async(
        self, file_data: bytes, filename: str, content_type: str, metadata: "Optional[dict[str, Any]]" = None
    ) -> "FileObject":
        """Simple async wrapper for handle_upload_async."""
        # Delegates to the new handler which includes validation/processing
        return await self.handle_upload_async(
            file_data=file_data,  # Assumes bytes for this simple wrapper
            filename=filename,
            content_type=content_type,
            metadata=metadata,
        )

    def sign(self, paths: Union[str, list[str]], expires_in: Optional[int] = None) -> Union[str, list[str]]:
        """Get URL for accessing file.

        Returns:
            The signed URL for accessing the file.
        """
        expires_in = expires_in or self.default_expires_in

        return self.backend.sign(paths, expires_in=expires_in)

    async def sign_async(self, paths: Union[str, list[str]], expires_in: Optional[int] = None) -> Union[str, list[str]]:
        """Get URL for accessing file.

        Returns:
            The signed URL for accessing the file.
        """
        expires_in = expires_in or self.default_expires_in

        return await self.backend.sign_async(paths, expires_in=expires_in)

    def delete_file(self, path: str) -> None:
        """Delete file from storage."""
        self.backend.delete(path)

    async def delete_file_async(self, path: str) -> None:
        """Delete file from storage."""
        await self.backend.delete_async(path)

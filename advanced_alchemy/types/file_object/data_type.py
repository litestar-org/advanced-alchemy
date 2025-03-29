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

        Raises:
            ValueError: If backend is invalid or required parameters are missing
        """
        super().__init__(*args, **kwargs)
        if not backend:
            msg = "backend is required"
            raise ValueError(msg)
        if isinstance(backend, str):
            self.backend = storages.get_backend(backend)
        else:
            storages.register_backend(backend.backend, backend)
            self.backend = backend
        self.compute_checksum = compute_checksum
        self.checksum_handler = checksum_handler or default_checksum_handler
        self.default_expires_in = default_expires_in or self.default_expires_in
        self.validators = validators or []
        self.processors = processors or []

    def process_bind_param(
        self, value: "Optional[Union[FileObject, dict[str, Any]]]", dialect: Any
    ) -> "Optional[dict[str, Any]]":
        """Convert FileInfo object/dict to database JSON format.

        Note: This method expects an already processed FileInfo or its dict representation.
              Use handle_upload() or handle_upload_async() for processing raw uploads.

        Args:
            value: The value to process
            dialect: The SQLAlchemy dialect

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

        Args:
            value: The value to process
            dialect: The SQLAlchemy dialect

        Returns:
            FileInfo object or None.
        """
        if value is None:
            return None

        # Inject the backend into the file info - crucial for functionality
        value["backend"] = self.backend
        return FileObject.from_dict(value)

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

        Raises:
            ValueError: If validation fails or required parameters are missing
        """
        if not filename:
            msg = "filename is required"
            raise ValueError(msg)
        if not content_type:
            msg = "content_type is required"
            raise ValueError(msg)
        if not file_data:
            msg = "file_data is required"
            raise ValueError(msg)

        # Create initial file object
        file_object = FileObject(
            filename=filename,
            content_type=content_type,
            size=len(file_data),
            metadata=metadata or {},
        )

        # Run validators
        for validator in self.validators:
            validator.validate(file_object, file_data=file_data)

        # Run processors
        processed_data = file_data
        for processor in self.processors:
            processed_data = processor.process(file_object, file_data=processed_data) or processed_data

        # Compute checksum if enabled
        if self.compute_checksum:
            file_object["checksum"] = self.checksum_handler(processed_data)

        # Determine storage path
        final_storage_path = storage_path if storage_path is not None else filename

        # Store the file
        return self.backend.put(
            path=final_storage_path,
            data=processed_data,
            content_type=content_type,
            metadata=file_object.metadata,
        )

    async def handle_upload_async(
        self,
        file_data: AsyncDataLike,
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

        Raises:
            ValueError: If validation fails or required parameters are missing
        """
        if not filename:
            msg = "filename is required"
            raise ValueError(msg)
        if not content_type:
            msg = "content_type is required"
            raise ValueError(msg)
        if not file_data:
            msg = "file_data is required"
            raise ValueError(msg)

        # Handle bytes synchronously
        if isinstance(file_data, bytes):
            return self.handle_upload(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                metadata=metadata,
                storage_path=storage_path,
            )

        # Create initial file object
        file_object = FileObject(
            filename=filename,
            content_type=content_type,
            size=0,  # Size will be determined by backend
            metadata=metadata or {},
        )

        # Run validators
        for validator in self.validators:
            await async_(validator.validate)(file_object)

        # Run processors
        for processor in self.processors:
            await async_(processor.process)(file_object)

        # Determine storage path
        final_storage_path = storage_path if storage_path is not None else filename

        # Store the file
        return await self.backend.put_async(
            path=final_storage_path,
            data=file_data,
            content_type=content_type,
            metadata=file_object.metadata,
        )

    def put_file(
        self, file_data: bytes, filename: str, content_type: str, metadata: "Optional[dict[str, Any]]" = None
    ) -> "FileObject":
        """Store a file synchronously.

        Args:
            file_data: Raw file data as bytes
            filename: Original filename
            content_type: MIME type of the file
            metadata: Optional additional metadata

        Returns:
            FileObject: The stored file object
        """
        return self.handle_upload(
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            metadata=metadata,
        )

    async def put_file_async(
        self, file_data: AsyncDataLike, filename: str, content_type: str, metadata: "Optional[dict[str, Any]]" = None
    ) -> "FileObject":
        """Store a file asynchronously.

        Args:
            file_data: Raw file data as bytes or async stream
            filename: Original filename
            content_type: MIME type of the file
            metadata: Optional additional metadata

        Returns:
            FileObject: The stored file object
        """
        return await self.handle_upload_async(
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            metadata=metadata,
        )

    def sign(self, paths: Union[str, list[str]], expires_in: Optional[int] = None) -> Union[str, list[str]]:
        """Generate signed URLs for files.

        Args:
            paths: Single path or list of paths
            expires_in: Optional expiration time in seconds

        Returns:
            Signed URL(s)
        """
        return self.backend.sign(paths, expires_in=expires_in or self.default_expires_in)

    async def sign_async(self, paths: Union[str, list[str]], expires_in: Optional[int] = None) -> Union[str, list[str]]:
        """Generate signed URLs for files asynchronously.

        Args:
            paths: Single path or list of paths
            expires_in: Optional expiration time in seconds

        Returns:
            Signed URL(s)
        """
        return await self.backend.sign_async(paths, expires_in=expires_in or self.default_expires_in)

    def delete_file(self, path: str) -> None:
        """Delete a file synchronously.

        Args:
            path: Path to the file
        """
        self.backend.delete(path)

    async def delete_file_async(self, path: str) -> None:
        """Delete a file asynchronously.

        Args:
            path: Path to the file
        """
        await self.backend.delete_async(path)

# ruff: noqa: PLR0904, PLR6301
"""Generic unified storage protocol compatible with multiple backend implementations."""

import mimetypes
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.base import (
        AsyncDataLike,
        DataLike,
        PathLike,
        StorageBackend,
    )


@dataclass
class FileObject:
    """Represents file metadata during processing using a dataclass structure.

    This class provides a unified interface for handling file metadata and operations
    across different storage backends.

    Content or a source path can optionally be provided during initialization via kwargs, store it internally, and add save/save_async methods to persist this pending data using the configured backend.

    Attributes:
        filename: The name of the file.
        content_type: The MIME type of the file. If None, it's guessed from filename,
                      defaulting to 'application/octet-stream'.
        size: The size of the file in bytes, or None if unknown. Defaults to None.
        path: The storage path/key of the file. If None, defaults to filename in __post_init__.
        backend: The storage backend instance. Not included in comparisons or default repr.
        protocol: The protocol used by the storage backend.
        last_modified: Last modification timestamp.
        checksum: MD5 checksum of the file.
        etag: ETag of the file.
        version_id: Version ID of the file.
        metadata: Additional metadata associated with the file.
        extra: Dictionary to store any additional keyword arguments passed during init.
               Used to capture 'content' and 'source_path'.
        _pending_content: Internal storage for content provided at init.
        _pending_source_path: Internal storage for source_path provided at init.
    """

    filename: str
    # Allow content_type to be initially None for guessing
    content_type: Optional[str] = None
    size: "Optional[int]" = None
    path: "Optional[str]" = None
    protocol: "Optional[str]" = None
    last_modified: "Optional[float]" = None
    checksum: "Optional[str]" = None
    etag: "Optional[str]" = None
    version_id: "Optional[str]" = None
    metadata: "dict[str, Any]" = field(default_factory=dict)
    # Capture arbitrary kwargs, including potential 'content' or 'source_path'
    extra: "dict[str, Any]" = field(default_factory=dict)
    backend: "Optional[StorageBackend]" = field(default=None, compare=False, repr=False)

    # Internal fields for pending data, not part of init/repr/compare
    _pending_content: "Optional[Union[DataLike, AsyncDataLike]]" = field(
        default=None, init=False, repr=False, compare=False
    )
    _pending_source_path: "Optional[PathLike]" = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Perform post-initialization validation and setup.

        Handles default path, content type guessing, backend protocol inference,
        and processing of 'content' or 'source_path' from extra kwargs.

        Raises:
            ValueError: If filename is not provided, size is negative, backend/protocol mismatch,
                        or both 'content' and 'source_path' are provided.
        """
        if not self.filename:
            msg = "filename is required"
            raise ValueError(msg)
        if self.size is not None and self.size < 0:
            msg = "size must be non-negative"
            raise ValueError(msg)

        # Default path to filename if not explicitly provided
        if self.path is None:
            self.path = self.filename

        # Guess content_type if not provided
        if self.content_type is None:
            guessed_type, _ = mimetypes.guess_type(self.filename)
            self.content_type = guessed_type or "application/octet-stream"

        # Handle backend and protocol assignment/validation
        if self.backend and self.protocol and self.backend.protocol != self.protocol:
            msg = f"Provided protocol '{self.protocol}' does not match backend protocol '{self.backend.protocol}'"
            raise ValueError(msg)
        if self.backend and not self.protocol:
            self.protocol = self.backend.protocol

        # Process content or source_path from extra kwargs
        content = self.extra.pop("content", None)
        source_path = self.extra.pop("source_path", None)

        if content is not None and source_path is not None:
            msg = "Cannot provide both 'content' and 'source_path' during initialization."
            raise ValueError(msg)

        if content is not None:
            self._pending_content = content
        elif source_path is not None:
            # Ensure source_path is a Path object for consistency
            self._pending_source_path = Path(source_path) if not isinstance(source_path, Path) else source_path

    @property
    def has_pending_data(self) -> bool:
        """Check if the FileObject has pending content or a source path to save."""
        return bool(self._pending_content or self._pending_source_path)

    def update_metadata(self, metadata: "dict[str, Any]") -> None:
        """Update the file metadata.

        Args:
            metadata: New metadata to merge with existing metadata.
        """
        self.metadata.update(metadata)

    def to_dict(self) -> "dict[str, Any]":
        """Convert FileObject to a dictionary for storage or serialization.

        Note: The 'backend' attribute is intentionally excluded as it's often
              not serializable or relevant for storage representations.
              The 'extra' dict is included.

        Returns:
            dict[str, Any]: A dictionary representation of the file information.
        """
        # Use dataclasses.asdict and filter out the backend
        data = asdict(self, dict_factory=lambda x: {k: v for (k, v) in x if k != "backend"})
        # Ensure metadata and extra are included even if empty (asdict might skip if default_factory)
        data.setdefault("metadata", {})
        data.setdefault("extra", {})
        return data

    def get_content(self, *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Get the file content from the storage backend.

        Args:
            options: Optional backend-specific options.

        Raises:
            RuntimeError: If no backend is configured or path is missing.

        Returns:
            bytes: The file content.
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if self.path is None:
            # This should not happen due to __post_init__, but check defensively
            msg = "File path is not set"
            raise RuntimeError(msg)
        return self.backend.get_content(self.path, options=options)

    async def get_content_async(self, *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Get the file content from the storage backend asynchronously.

        Args:
            options: Optional backend-specific options.

        Raises:
            RuntimeError: If no backend is configured or path is missing.

        Returns:
            bytes: The file content.
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if self.path is None:
            msg = "File path is not set"
            raise RuntimeError(msg)
        return await self.backend.get_content_async(self.path, options=options)

    def sign(
        self,
        *,
        expires_in: "Optional[int]" = None,
        for_upload: bool = False,
    ) -> str:
        """Generate a signed URL for the file.

        Args:
            expires_in: Optional expiration time in seconds.
            for_upload: Whether the URL is for upload.

        Returns:
            str: The signed URL.

        Raises:
            RuntimeError: If no backend is configured or path is missing.
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if self.path is None:
            msg = "File path is not set"
            raise RuntimeError(msg)
        result = self.backend.sign(self.path, expires_in=expires_in, for_upload=for_upload)
        if isinstance(result, list):
            if not result:
                msg = "No signed URL generated"
                raise RuntimeError(msg)
            return result[0]
        return result

    async def sign_async(
        self,
        *,
        expires_in: "Optional[int]" = None,
        for_upload: bool = False,
    ) -> str:
        """Generate a signed URL for the file asynchronously.

        Args:
            expires_in: Optional expiration time in seconds.
            for_upload: Whether the URL is for upload.

        Returns:
            str: The signed URL.

        Raises:
            RuntimeError: If no backend is configured or path is missing.
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if self.path is None:
            msg = "File path is not set"
            raise RuntimeError(msg)
        result = await self.backend.sign_async(self.path, expires_in=expires_in, for_upload=for_upload)
        if isinstance(result, list):
            if not result:
                msg = "No signed URL generated"
                raise RuntimeError(msg)
            return result[0]
        return result

    def delete(self) -> None:
        """Delete the file from storage.

        Raises:
            RuntimeError: If no backend is configured or path is missing.
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if self.path is None:
            msg = "File path is not set"
            raise RuntimeError(msg)
        self.backend.delete_from_storage(self.path)

    async def delete_async(self) -> None:
        """Delete the file from storage asynchronously.

        Raises:
            RuntimeError: If no backend is configured or path is missing.
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if self.path is None:
            msg = "File path is not set"
            raise RuntimeError(msg)
        await self.backend.delete_from_storage_async(self.path)

    def save(
        self,
        *,
        data: Optional[DataLike] = None,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the storage backend using this FileObject's metadata.

        If `data` is provided, it is used directly.
        If `data` is None, checks internal _pending_content or _pending_source_path.
        Clears pending attributes after successful save.

        Args:
            data: Optional data to save (bytes, iterator, file-like, Path). If None,
                  internal pending data is used.
            use_multipart: Passed to the backend's save method.
            chunk_size: Passed to the backend's save method.
            max_concurrency: Passed to the backend's save method.

        Returns:
            The updated FileObject instance returned by the backend.

        Raises:
            RuntimeError: If no backend is configured or path is missing, or if no data
                          source (argument or pending) is found.
            TypeError: If trying to save async data synchronously.
            FileNotFoundError: If internal _pending_source_path is used and file not found.
        """
        if not self.backend:
            msg = "No storage backend configured for saving."
            raise RuntimeError(msg)
        if self.path is None:
            msg = "File path is not set for saving."
            raise RuntimeError(msg)

        data_source: Optional[DataLike] = data

        if data_source is None:
            # If data argument not provided, try pending attributes
            if self._pending_content is not None:
                data_source = self._pending_content  # type: ignore[assignment]
            elif self._pending_source_path is not None:
                source_path = Path(self._pending_source_path)
                if not source_path.is_file():
                    msg = f"Source path does not exist or is not a file: {source_path}"
                    raise FileNotFoundError(msg)
                # Pass Path object itself, backend handles reading
                data_source = source_path

        if data_source is None:
            msg = "No data provided and no pending content/path found to save."
            raise TypeError(msg)

        # Check for incompatible async data types
        if isinstance(data_source, (AsyncIterator, AsyncIterable)):
            msg = "Cannot save async data with synchronous save method. Use save_async."
            raise TypeError(msg)

        # The backend's save method is expected to update the FileObject instance in-place
        # and return the updated instance.
        updated_self = self.backend.save_to_storage(
            file_object=self,
            data=data_source,  # Pass the determined data source
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Clear pending attributes after successful save
        self._pending_content = None
        self._pending_source_path = None

        return updated_self

    async def save_async(
        self,
        *,
        data: Optional[AsyncDataLike] = None,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the storage backend asynchronously.

        If `data` is provided, it is used directly.
        If `data` is None, checks internal _pending_content or _pending_source_path.
        Clears pending attributes after successful save.
        Uses asyncio.to_thread for reading _pending_source_path if backend doesn't handle Path directly.

        Args:
            data: Optional data to save (bytes, async iterator, file-like, Path, etc.).
                  If None, internal pending data is used.
            use_multipart: Passed to the backend's async save method.
            chunk_size: Passed to the backend's async save method.
            max_concurrency: Passed to the backend's async save method.

        Returns:
            The updated FileObject instance returned by the backend.

        Raises:
            RuntimeError: If no backend is configured or path is missing, or if no data
                          source (argument or pending) is found.
            FileNotFoundError: If internal _pending_source_path is used and file not found.
            TypeError: If trying to save sync data asynchronously.
        """
        if not self.backend:
            msg = "No storage backend configured for saving."
            raise RuntimeError(msg)
        if self.path is None:
            msg = "File path is not set for saving."
            raise RuntimeError(msg)

        data_source: Optional[AsyncDataLike] = data

        if data_source is None:
            # If data argument not provided, try pending attributes
            if self._pending_content is not None:
                data_source = self._pending_content
            elif self._pending_source_path is not None:
                source_path = Path(self._pending_source_path)
                if not source_path.is_file():
                    msg = f"Source path does not exist or is not a file: {source_path}"
                    raise FileNotFoundError(msg)
                # Pass Path object itself, backend handles reading (asyncly if possible)
                # Note: Reading logic specifically for validation/processing is in the tracker.
                # Here, we just pass the source to the backend.
                data_source = source_path

        if data_source is None:
            msg = "No data provided and no pending content/path found to save."
            raise TypeError(msg)

        # Backend's async save method updates the FileObject instance
        updated_self = await self.backend.save_to_storage_async(
            file_object=self,
            data=data_source,  # Pass the determined data source
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Clear pending attributes after successful save
        self._pending_content = None
        self._pending_source_path = None

        return updated_self

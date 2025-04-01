# ruff: noqa: PLR0904, PLR6301
"""Generic unified storage protocol compatible with multiple backend implementations."""

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy.ext.mutable import MutableList
from typing_extensions import TypeAlias

from advanced_alchemy.types.file_object.base import AsyncDataLike, DataLike, StorageBackend
from advanced_alchemy.types.file_object.registry import storages

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.base import PathLike


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
        source_content: Internal storage for content provided at init.
        source_path: Internal storage for source_path provided at init.
    """

    __slots__ = (
        "_content_type",
        "_filename",
        "_pending_source_content",
        "_pending_source_path",
        "_raw_backend",
        "_resolved_backend",
        "_to_filename",
        "checksum",
        "etag",
        "extra",
        "last_modified",
        "metadata",
        "size",
        "version_id",
    )

    def __init__(
        self,
        backend: "Union[str, StorageBackend]",
        filename: str,
        to_filename: Optional[str] = None,
        content_type: Optional[str] = None,
        size: Optional[int] = None,
        last_modified: Optional[float] = None,
        checksum: Optional[str] = None,
        etag: Optional[str] = None,
        version_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        source_path: "Optional[PathLike]" = None,
        content: "Optional[Union[DataLike, AsyncDataLike]]" = None,
        **kwargs: Any,
    ) -> None:
        """Perform post-initialization validation and setup.

        Handles default path, content type guessing, backend protocol inference,
        and processing of 'content' or 'source_path' from extra kwargs.

        Raises:
            ValueError: If filename is not provided, size is negative, backend/protocol mismatch,
                        or both 'content' and 'source_path' are provided.
        """
        self._filename = filename
        self._to_filename = to_filename
        self._content_type = content_type
        self._raw_backend = backend
        self.size = size
        self._resolved_backend: Optional[StorageBackend] = backend if isinstance(backend, StorageBackend) else None
        self.last_modified = last_modified
        self.checksum = checksum
        self.etag = etag
        self.version_id = version_id
        self.metadata = metadata or {}
        self.extra = kwargs
        self._pending_source_path = Path(source_path) if source_path is not None else None
        self._pending_source_content = content
        if self._pending_source_content is not None and self._pending_source_path is not None:
            msg = "Cannot provide both 'source_content' and 'source_path' during initialization."
            raise ValueError(msg)

    @property
    def backend(self) -> "StorageBackend":
        """Return the storage backend instance."""
        if self._resolved_backend is None:
            self._resolved_backend = (
                storages.get_backend(self._raw_backend) if isinstance(self._raw_backend, str) else self._raw_backend
            )
        return self._resolved_backend

    @property
    def filename(self) -> str:
        """Return the filename of the file."""
        return self.path

    @property
    def content_type(self) -> str:
        """Return the content type of the file."""
        if self._content_type is None:
            guessed_type, _ = mimetypes.guess_type(self._filename)
            self._content_type = guessed_type or "application/octet-stream"
        return self._content_type

    @property
    def protocol(self) -> str:
        """Return the protocol of the file, defaulting to backend protocol if not set."""
        return self.backend.protocol if self.backend else "file"

    @property
    def path(self) -> str:
        """Return the path of the file, defaulting to to_filename if not set."""
        return self._to_filename or self._filename

    @property
    def has_pending_data(self) -> bool:
        """Check if the FileObject has pending content or a source path to save."""
        return bool(self._pending_source_content or self._pending_source_path)

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
        return {
            "filename": self.path,
            "content_type": self.content_type,
            "backend": self.backend.key,
            "size": self.size,
            "protocol": self.protocol,
            "last_modified": self.last_modified,
            "checksum": self.checksum,
            "etag": self.etag,
            "version_id": self.version_id,
            "metadata": self.metadata,
            "extra": self.extra,
        }

    def get_content(self, *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Get the file content from the storage backend.

        Args:
            options: Optional backend-specific options.

        Returns:
            bytes: The file content.
        """
        return self.backend.get_content(self.path, options=options)

    async def get_content_async(self, *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Get the file content from the storage backend asynchronously.

        Args:
            options: Optional backend-specific options.

        Returns:
            bytes: The file content.
        """
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

        Raises:
            RuntimeError: If no signed URL is generated.

        Returns:
            str: The signed URL.
        """
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
            RuntimeError: If no signed URL is generated.
        """
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
        self.backend.delete_object(self.path)

    async def delete_async(self) -> None:
        """Delete the file from storage asynchronously."""
        await self.backend.delete_object_async(self.path)

    def save(
        self,
        data: Optional[DataLike] = None,
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the storage backend using this FileObject's metadata.

        If `data` is provided, it is used directly.
        If `data` is None, checks internal source_content or source_path.
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
            TypeError: If trying to save async data synchronously.
        """

        if data is None and self._pending_source_content is not None:
            data = self._pending_source_content  # type: ignore[assignment]
        elif data is None and self._pending_source_path is not None:
            data = self._pending_source_path

        if data is None:
            msg = "No data provided and no pending content/path found to save."
            raise TypeError(msg)

        # The backend's save method is expected to update the FileObject instance in-place
        # and return the updated instance.
        updated_self = self.backend.save_object(
            file_object=self,
            data=data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Clear pending attributes after successful save
        self._pending_source_content = None
        self._pending_source_path = None

        return updated_self

    async def save_async(
        self,
        data: Optional[AsyncDataLike] = None,
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the storage backend asynchronously.

        If `data` is provided, it is used directly.
        If `data` is None, checks internal source_content or source_path.
        Clears pending attributes after successful save.
        Uses asyncio.to_thread for reading source_path if backend doesn't handle Path directly.

        Args:
            data: Optional data to save (bytes, async iterator, file-like, Path, etc.).
                  If None, internal pending data is used.
            use_multipart: Passed to the backend's async save method.
            chunk_size: Passed to the backend's async save method.
            max_concurrency: Passed to the backend's async save method.

        Returns:
            The updated FileObject instance returned by the backend.

        Raises:
            TypeError: If trying to save sync data asynchronously.
        """

        if data is None and self._pending_source_content is not None:
            data = self._pending_source_content
        elif data is None and self._pending_source_path is not None:
            data = self._pending_source_path

        if data is None:
            msg = "No data provided and no pending content/path found to save."
            raise TypeError(msg)

        # Backend's async save method updates the FileObject instance
        updated_self = await self.backend.save_object_async(
            file_object=self,
            data=data,  # Pass the determined data source
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Clear pending attributes after successful save
        self._pending_source_content = None
        self._pending_source_path = None

        return updated_self


FileObjectList: TypeAlias = MutableList[FileObject]

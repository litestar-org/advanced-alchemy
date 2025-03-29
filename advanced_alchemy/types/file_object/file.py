"""File object implementation for handling file metadata and operations."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional

from advanced_alchemy.types.file_object.base import PathLike, StorageBackend
from advanced_alchemy.types.mutables import FreezableFileBase


class FileValidator:
    """Validator for file objects."""

    def validate(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> None:
        """Validate the file object. Can optionally use raw file data."""


class MaxSizeValidator(FileValidator):
    """Validator to check the size of the file."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size

    def validate(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> None:
        if "size" not in file or file["size"] is None:
            # If size isn't available (e.g., stream), this validator might need file_data
            if file_data is not None and len(file_data) > self.max_size:
                msg = f"File size {len(file_data)} bytes exceeds maximum size of {self.max_size} bytes"
                raise ValueError(msg)
            # Cannot validate size if not provided in metadata and no raw data given
            # Alternatively, could raise an error here if size is mandatory for validation
        elif file.get("size", 0) > self.max_size:
            msg = f"File size {file['size']} bytes exceeds maximum size of {self.max_size} bytes"
            raise ValueError(msg)


class FileProcessor:
    """Processor for file objects."""

    def process(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> Optional[bytes]:
        """Process the file object. Can optionally use and return modified raw file data."""
        return file_data  # Default: return data unmodified


class FileExtensionProcessor(FileProcessor):
    """Processor to check the file extension."""

    def __init__(self, allowed_extensions: list[str]) -> None:
        # Normalize extensions to include dot and be lowercase
        self.allowed_extensions = {f".{ext.lstrip('.').lower()}" for ext in allowed_extensions}

    def process(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> Optional[bytes]:
        ext = Path(file.get("filename", "")).suffix.lower()
        if not ext:
            msg = "File has no extension."
            raise ValueError(msg)
        if ext not in self.allowed_extensions:
            msg = f"File extension '{ext}' not allowed. Allowed: {', '.join(sorted(self.allowed_extensions))}"
            raise ValueError(msg)
        return file_data  # Return data unmodified


class FileObject(FreezableFileBase):
    """Dictionary-like object representing file metadata during processing.

    This class provides a unified interface for handling file metadata and operations
    across different storage backends. It inherits from FreezableFileBase to provide
    mutable dictionary functionality with the ability to freeze the state.

    Attributes:
        filename (str): The name of the file
        content_type (str): The MIME type of the file
        size (int): The size of the file in bytes
        path (str): The storage path/key of the file
        backend (StorageBackend): The storage backend instance
        protocol (str): The protocol used by the storage backend
        last_modified (float): Last modification timestamp
        checksum (str): MD5 checksum of the file
        etag (str): ETag of the file
        version_id (str): Version ID of the file
        metadata (dict): Additional metadata associated with the file
    """

    def __init__(
        self,
        filename: str,
        content_type: str,
        size: int,
        path: Optional[str] = None,
        backend: Optional[StorageBackend] = None,
        protocol: Optional[str] = None,
        last_modified: Optional[float] = None,
        checksum: Optional[str] = None,
        etag: Optional[str] = None,
        version_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a FileObject instance.

        Args:
            filename: Name of the file
            content_type: MIME type of the file
            size: Size of the file in bytes
            path: Optional storage path/key of the file
            backend: Optional storage backend instance
            protocol: Optional protocol used by the storage backend
            last_modified: Optional last modification timestamp
            checksum: Optional MD5 checksum of the file
            etag: Optional ETag of the file
            version_id: Optional version ID of the file
            metadata: Optional additional metadata
            **kwargs: Additional keyword arguments to store in the object
        """
        super().__init__()
        self.update(
            {
                "filename": filename,
                "content_type": content_type,
                "size": size,
                "path": path,
                "backend": backend,
                "protocol": protocol,
                "last_modified": last_modified,
                "checksum": checksum,
                "etag": etag,
                "version_id": version_id,
                "metadata": metadata or {},
                **kwargs,
            }
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileObject":
        """Create a FileObject instance from a dictionary.

        Args:
            data: Dictionary containing file information

        Returns:
            FileObject: A new FileObject instance
        """
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert FileObject to a dictionary for storage.

        Returns:
            dict[str, Any]: A dictionary representation of the file information
        """
        return dict(self)

    def get(self, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend.

        Args:
            options: Optional backend-specific options

        Returns:
            bytes: The file content

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return self["backend"].get(self["path"], options=options)

    async def get_async(self, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend asynchronously.

        Args:
            options: Optional backend-specific options

        Returns:
            bytes: The file content

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return await self["backend"].get_async(self["path"], options=options)

    def get_range(
        self,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        """Get a range of bytes from the file.

        Args:
            start: Starting byte offset
            end: Optional ending byte offset (inclusive)
            length: Optional number of bytes to read

        Returns:
            bytes: The requested byte range

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return self["backend"].get_range(self["path"], start=start, end=end, length=length)

    async def get_range_async(
        self,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        """Get a range of bytes from the file asynchronously.

        Args:
            start: Starting byte offset
            end: Optional ending byte offset (inclusive)
            length: Optional number of bytes to read

        Returns:
            bytes: The requested byte range

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return await self["backend"].get_range_async(self["path"], start=start, end=end, length=length)

    def get_ranges(
        self,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> list[bytes]:
        """Get multiple ranges of bytes from the file.

        Args:
            starts: Sequence of starting byte offsets
            ends: Optional sequence of ending byte offsets (inclusive)
            lengths: Optional sequence of lengths to read

        Returns:
            list[bytes]: The requested byte ranges

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return self["backend"].get_ranges(self["path"], starts=starts, ends=ends, lengths=lengths)

    async def get_ranges_async(
        self,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> list[bytes]:
        """Get multiple ranges of bytes from the file asynchronously.

        Args:
            starts: Sequence of starting byte offsets
            ends: Optional sequence of ending byte offsets (inclusive)
            lengths: Optional sequence of lengths to read

        Returns:
            list[bytes]: The requested byte ranges

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return await self["backend"].get_ranges_async(self["path"], starts=starts, ends=ends, lengths=lengths)

    def sign(
        self,
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> str:
        """Get a signed URL for accessing or uploading the file.

        Args:
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for uploading

        Returns:
            str: The signed URL

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return self["backend"].sign(self["path"], expires_in=expires_in, for_upload=for_upload)

    async def sign_async(
        self,
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> str:
        """Get a signed URL for accessing or uploading the file asynchronously.

        Args:
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for uploading

        Returns:
            str: The signed URL

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return await self["backend"].sign_async(self["path"], expires_in=expires_in, for_upload=for_upload)

    def delete(self) -> None:
        """Delete the file from the storage backend.

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        self["backend"].delete(self["path"])

    async def delete_async(self) -> None:
        """Delete the file from the storage backend asynchronously.

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        await self["backend"].delete_async(self["path"])

    def copy(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy the file to another location in the same backend.

        Args:
            to: Destination path
            overwrite: Whether to overwrite existing files

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        self["backend"].copy(self["path"], to, overwrite=overwrite)

    async def copy_async(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy the file to another location in the same backend asynchronously.

        Args:
            to: Destination path
            overwrite: Whether to overwrite existing files

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        await self["backend"].copy_async(self["path"], to, overwrite=overwrite)

    def rename(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Move the file to another location in the same backend.

        Args:
            to: Destination path
            overwrite: Whether to overwrite existing files

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        self["backend"].rename(self["path"], to, overwrite=overwrite)

    async def rename_async(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Move the file to another location in the same backend asynchronously.

        Args:
            to: Destination path
            overwrite: Whether to overwrite existing files

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        await self["backend"].rename_async(self["path"], to, overwrite=overwrite)

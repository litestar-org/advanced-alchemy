# ruff: noqa: PLR0904, PLR6301
"""Generic unified storage protocol compatible with multiple backend implementations."""

import hashlib
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator, Sequence
from pathlib import Path
from typing import IO, Any, Callable, Optional, TypeVar, Union, cast, overload

from typing_extensions import TypeAlias

from advanced_alchemy._serialization import decode_json, encode_json
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.types.mutables import FreezableFileBase
from advanced_alchemy.utils.module_loader import import_string
from advanced_alchemy.utils.singleton import SingletonMeta

# Type variables
T = TypeVar("T")
StorageBackendT = TypeVar("StorageBackendT", bound="StorageBackend")
PathLike: TypeAlias = Union[str, Path, os.PathLike[Any]]
DataLike: TypeAlias = Union[IO[bytes], Path, bytes, Iterator[bytes], Iterable[bytes]]
AsyncDataLike: TypeAlias = Union[
    IO[bytes], Path, bytes, AsyncIterator[bytes], AsyncIterable[bytes], Iterator[bytes], Iterable[bytes]
]


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
        """Process the file object. Can optionally use and return modified raw file data.

        Args:
            file: The file object to process
            file_data: The raw file data to process
            key: The key of the file object

        Returns:
            The modified raw file data
        """
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


def default_checksum_handler(value: bytes) -> str:
    """Calculate the checksum of the file using MD5.

    Args:
        value: The file data to calculate the checksum of

    Returns:
        The MD5 checksum of the file
    """
    return hashlib.md5(value, usedforsecurity=False).hexdigest()


class ChecksumProcessor(FileProcessor):
    """Processor to calculate and add a checksum to the file object."""

    def __init__(self, checksum_handler: Optional[Callable[[bytes], str]] = None) -> None:
        """Initialize the ChecksumProcessor.

        Args:
            checksum_handler: Optional callable to compute the checksum. Defaults to MD5.
        """
        self.checksum_handler = checksum_handler or default_checksum_handler

    def process(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> Optional[bytes]:
        """Calculate checksum if data is available and add it to the file object.

        Args:
            file: The file object to process (metadata will be updated).
            file_data: The raw file data to calculate the checksum from.
            key: The key of the file object (unused here).

        Returns:
            The original file_data, unmodified.
        """
        if file_data is not None:
            checksum = self.checksum_handler(file_data)
            file["checksum"] = checksum
        # Note: This processor cannot calculate checksum for streams without buffering.
        # Checksum for streams might need to be handled by the backend during upload.
        return file_data


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
        content_type: str = "application/octet-stream",
        size: int = 0,
        path: Optional[str] = None,
        backend: "Optional[StorageBackend]" = None,
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

        Raises:
            ValueError: If required fields are missing or invalid
        """
        if not filename:
            msg = "filename is required"
            raise ValueError(msg)
        if size < 0:
            msg = "size must be non-negative"
            raise ValueError(msg)

        super().__init__()
        self.update(
            {
                "filename": filename,
                "content_type": content_type,
                "size": size,
                "path": path or filename,  # Default to filename if path not provided
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

    @property
    def filename(self) -> str:
        """Get the filename."""
        return self["filename"]

    @property
    def content_type(self) -> str:
        """Get the content type."""
        return self["content_type"]

    @property
    def size(self) -> int:
        """Get the file size."""
        return self["size"]

    @property
    def path(self) -> str:
        """Get the storage path."""
        return self["path"]

    @property
    def backend(self) -> "Optional[StorageBackend]":
        """Get the storage backend."""
        return self.get("backend")

    @property
    def protocol(self) -> Optional[str]:
        """Get the storage protocol."""
        return self.get("protocol")

    @property
    def last_modified(self) -> Optional[float]:
        """Get the last modification timestamp."""
        return self.get("last_modified")

    @property
    def checksum(self) -> Optional[str]:
        """Get the file checksum."""
        return self.get("checksum")

    @property
    def etag(self) -> Optional[str]:
        """Get the file ETag."""
        return self.get("etag")

    @property
    def version_id(self) -> Optional[str]:
        """Get the file version ID."""
        return self.get("version_id")

    @property
    def metadata(self) -> dict[str, Any]:
        """Get the file metadata."""
        return self.get("metadata", {})

    def update_metadata(self, metadata: dict[str, Any]) -> None:
        """Update the file metadata.

        Args:
            metadata: New metadata to merge with existing metadata
        """
        self["metadata"] = {**self.metadata, **metadata}

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

    def get_content(self, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend.

        Args:
            options: Optional backend-specific options

        Raises:
            RuntimeError: If no backend is configured

        Returns:
            bytes: The file content
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return self.backend.get_content(self.path, options=options)

    async def get_content_async(self, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend asynchronously.

        Args:
            options: Optional backend-specific options

        Raises:
            RuntimeError: If no backend is configured

        Returns:
            bytes: The file content
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return await self.backend.get_content_async(self.path, options=options)

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
            ValueError: If range parameters are invalid
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if start < 0:
            msg = "start must be non-negative"
            raise ValueError(msg)
        if end is not None and end < start:
            msg = "end must be greater than or equal to start"
            raise ValueError(msg)
        if length is not None and length <= 0:
            msg = "length must be positive"
            raise ValueError(msg)
        return self.backend.get_range(self.path, start=start, end=end, length=length)

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
            ValueError: If range parameters are invalid
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if start < 0:
            msg = "start must be non-negative"
            raise ValueError(msg)
        if end is not None and end < start:
            msg = "end must be greater than or equal to start"
            raise ValueError(msg)
        if length is not None and length <= 0:
            msg = "length must be positive"
            raise ValueError(msg)
        return await self.backend.get_range_async(self.path, start=start, end=end, length=length)

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
            list[bytes]: List of requested byte ranges

        Raises:
            RuntimeError: If no backend is configured
            ValueError: If range parameters are invalid
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        if not starts:
            msg = "starts must not be empty"
            raise ValueError(msg)
        if ends is not None and len(ends) != len(starts):
            msg = "ends must have same length as starts"
            raise ValueError(msg)
        if lengths is not None and len(lengths) != len(starts):
            msg = "lengths must have same length as starts"
            raise ValueError(msg)
        return self.backend.get_ranges(self.path, starts=starts, ends=ends, lengths=lengths)

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
            list[bytes]: List of requested byte ranges

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return await self.backend.get_ranges_async(self.path, starts=starts, ends=ends, lengths=lengths)

    def sign(
        self,
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> str:
        """Generate a signed URL for the file.

        Args:
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for upload

        Returns:
            str: The signed URL

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
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
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> str:
        """Generate a signed URL for the file asynchronously.

        Args:
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for upload

        Returns:
            str: The signed URL

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
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
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        self.backend.delete(self.path)

    async def delete_async(self) -> None:
        """Delete the file from storage asynchronously.

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        await self.backend.delete_async(self.path)

    def copy_to(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy the file to another location.

        Args:
            to: Destination path
            overwrite: Whether to overwrite existing file

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        self.backend.copy(self.path, to, overwrite=overwrite)

    async def copy_to_async(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy the file to another location asynchronously.

        Args:
            to: Destination path
            overwrite: Whether to overwrite existing file

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        await self.backend.copy_async(self.path, to, overwrite=overwrite)

    def rename_to(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename the file to another location.

        Args:
            to: New path
            overwrite: Whether to overwrite existing file

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        self.backend.rename(self.path, to, overwrite=overwrite)
        self["path"] = str(to)

    async def rename_to_async(self, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename the file to another location asynchronously.

        Args:
            to: New path
            overwrite: Whether to overwrite existing file

        Raises:
            RuntimeError: If no backend is configured
        """

        await self.backend.rename_async(self.path, to, overwrite=overwrite)
        self["path"] = str(to)

    def _has_backend(self) -> None:
        """Check if the file has a backend."""
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)


class StorageRegistry(metaclass=SingletonMeta):
    """A provider for creating and managing threaded portals."""

    def __init__(
        self,
        json_serializer: Callable[[Any], str] = encode_json,
        json_deserializer: Callable[[Union[str, bytes]], Any] = decode_json,
        default_backend: str = "advanced_alchemy.types.file_object.backends.objectstore.ObstoreBackend",
    ) -> None:
        """Initialize the PortalProvider."""
        self._registry: dict[str, StorageBackend] = {}
        self.json_serializer = json_serializer
        self.json_deserializer = json_deserializer
        self.default_backend = cast("type[StorageBackend]", import_string(default_backend))

    def to_json(self, obj: Any) -> str:
        """Convert an object to a JSON string using the configured serializer.

        Returns:
            str: The JSON string representation of the object.
        """
        return self.json_serializer(obj)

    def from_json(self, data: Union[str, bytes]) -> Any:
        """Convert a JSON string to an object using the configured deserializer.

        Returns:
            Any: The deserialized object.
        """
        return self.json_deserializer(data)

    def is_registered(self, key: str) -> bool:
        """Check if a storage backend is registered in the registry.

        Args:
            key: The key of the storage backend

        Returns:
            bool: True if the storage backend is registered, False otherwise.
        """
        return key in self._registry

    def get_backend(self, key: str) -> "StorageBackend":
        """Retrieve a configured storage backend from the registry.

        Returns:
            StorageBackend: The storage backend associated with the given key.

        Raises:
            ImproperConfigurationError: If no storage backend is registered with the given key.
        """
        try:
            return self._registry[key]
        except KeyError as e:
            msg = f"No storage backend registered with key {key}"
            raise ImproperConfigurationError(msg) from e

    @overload
    def register_backend(self, key: str, value: "StorageBackend") -> None: ...
    @overload
    def register_backend(self, key: str, value: str) -> None: ...
    def register_backend(self, key: str, value: "Union[StorageBackend, str]") -> None:
        """Register a new storage backend in the registry."""
        if isinstance(value, str):
            self._registry[key] = self.default_backend(fs=value, key=key)
        else:
            self._registry[key] = value

    def unregister_backend(self, key: str) -> None:
        """Unregister a storage backend from the registry."""
        if key in self._registry:
            del self._registry[key]

    def clear_backends(self) -> None:
        """Clear the registry."""
        self._registry.clear()

    def registered_backends(self) -> list[str]:
        """Return a list of all registered keys."""
        return list(self._registry.keys())


storages = StorageRegistry()


class StorageBackend(ABC):
    """Unified protocol for storage backend implementations supporting both sync and async operations."""

    driver: str
    """The name of the storage backend."""
    protocol: str
    """The protocol used by the storage backend."""

    def __init__(self, fs: Any, key: str, *, options: Optional[dict[str, Any]] = None, **kwargs: Any) -> None:
        """Initialize the storage backend.

        Args:
            fs: The filesystem or storage client
            key: The key of the backend instance
            options: Optional backend-specific options
            **kwargs: Additional keyword arguments
        """
        self.fs = fs
        self.options = options or {}

    @staticmethod
    def _to_path(path: PathLike) -> str:
        """Convert a path-like object to a string.

        Args:
            path: The path to convert

        Returns:
            str: The string representation of the path
        """
        return str(path)

    @abstractmethod
    def get_content(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the content of a file.

        Args:
            path: Path to the file
            options: Optional backend-specific options

        Returns:
            bytes: The file content
        """

    @abstractmethod
    async def get_content_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the content of a file asynchronously.

        Args:
            path: Path to the file
            options: Optional backend-specific options

        Returns:
            bytes: The file content
        """

    @abstractmethod
    def get_range(
        self,
        path: PathLike,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        """Get a range of bytes from a file.

        Args:
            path: Path to the file
            start: Starting byte offset
            end: Optional ending byte offset (inclusive)
            length: Optional number of bytes to read

        Returns:
            bytes: The requested byte range
        """

    @abstractmethod
    async def get_range_async(
        self,
        path: PathLike,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        """Get a range of bytes from a file asynchronously.

        Args:
            path: Path to the file
            start: Starting byte offset
            end: Optional ending byte offset (inclusive)
            length: Optional number of bytes to read

        Returns:
            bytes: The requested byte range
        """

    @abstractmethod
    def get_ranges(
        self,
        path: PathLike,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> list[bytes]:
        """Get multiple ranges of bytes from a file.

        Args:
            path: Path to the file
            starts: Sequence of starting byte offsets
            ends: Optional sequence of ending byte offsets (inclusive)
            lengths: Optional sequence of lengths to read

        Returns:
            list[bytes]: List of requested byte ranges
        """

    @abstractmethod
    async def get_ranges_async(
        self,
        path: PathLike,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> list[bytes]:
        """Get multiple ranges of bytes from a file asynchronously.

        Args:
            path: Path to the file
            starts: Sequence of starting byte offsets
            ends: Optional sequence of ending byte offsets (inclusive)
            lengths: Optional sequence of lengths to read

        Returns:
            list[bytes]: List of requested byte ranges
        """

    @abstractmethod
    def put(
        self,
        path: PathLike,
        data: DataLike,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> FileObject:
        """Store a file.

        Args:
            path: Path to store the file at
            data: The file data to store
            content_type: Optional MIME type of the file
            metadata: Optional additional metadata
            use_multipart: Whether to use multipart upload
            chunk_size: Size of chunks for multipart upload
            max_concurrency: Maximum number of concurrent uploads

        Returns:
            FileObject: The stored file object
        """

    @abstractmethod
    async def put_async(
        self,
        path: PathLike,
        data: AsyncDataLike,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> FileObject:
        """Store a file asynchronously.

        Args:
            path: Path to store the file at
            data: The file data to store
            content_type: Optional MIME type of the file
            metadata: Optional additional metadata
            use_multipart: Whether to use multipart upload
            chunk_size: Size of chunks for multipart upload
            max_concurrency: Maximum number of concurrent uploads

        Returns:
            FileObject: The stored file object
        """

    @abstractmethod
    def delete(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete one or more files.

        Args:
            paths: Path or paths to delete
        """

    @abstractmethod
    async def delete_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete one or more files asynchronously.

        Args:
            paths: Path or paths to delete
        """

    @abstractmethod
    def copy(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy a file.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing file
        """

    @abstractmethod
    async def copy_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy a file asynchronously.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing file
        """

    @abstractmethod
    def rename(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename a file.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing file
        """

    @abstractmethod
    async def rename_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename a file asynchronously.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing file
        """

    @abstractmethod
    def sign(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Generate a signed URL for one or more files.

        Args:
            paths: Path or paths to generate URLs for
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for upload

        Returns:
            str: The signed URL
        """

    @abstractmethod
    async def sign_async(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Generate a signed URL for one or more files asynchronously.

        Args:
            paths: Path or paths to generate URLs for
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for upload

        Returns:
            str: The signed URL
        """

    @abstractmethod
    async def list_async(
        self,
        prefix: Optional[str] = None,
        /,
        **kwargs: Any,
    ) -> list[FileObject]:
        """List files asynchronously.

        Args:
            prefix: Optional prefix to filter by
            **kwargs: Additional keyword arguments

        Returns:
            list[FileObject]: List of files
        """

    @abstractmethod
    def list(
        self,
        prefix: Optional[str] = None,
        /,
        **kwargs: Any,
    ) -> list[FileObject]:
        """List files.

        Args:
            prefix: Optional prefix to filter by
            **kwargs: Additional keyword arguments

        Returns:
            list[FileObject]: List of files
        """

# ruff: noqa: PLR0904
"""Generic unified storage protocol compatible with multiple backend implementations."""

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator, Sequence
from pathlib import Path
from typing import IO, Any, Callable, Optional, TypeVar, Union

from typing_extensions import TypeAlias

from advanced_alchemy._serialization import decode_json, encode_json
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.types.mutables import FreezableFileBase
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

    def get_content(self, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend.

        Args:
            options: Optional backend-specific options

        Raises:
            RuntimeError: If no backend is configured

        Returns:
            bytes: The file content
        """
        if not self.get("backend"):
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        return self["backend"].get(self["path"], options=options)

    async def get_content_async(self, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend asynchronously.

        Args:
            options: Optional backend-specific options

        Raises:
            RuntimeError: If no backend is configured

        Returns:
            bytes: The file content
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

    def copy_to(self, to: PathLike, *, overwrite: bool = True) -> None:
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

    async def copy_to_async(self, to: PathLike, *, overwrite: bool = True) -> None:
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

    def rename_to(self, to: PathLike, *, overwrite: bool = True) -> None:
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

    async def rename_to_async(self, to: PathLike, *, overwrite: bool = True) -> None:
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


class StorageRegistry(metaclass=SingletonMeta):
    """A provider for creating and managing threaded portals."""

    def __init__(
        self,
        json_serializer: Callable[[Any], str] = encode_json,
        json_deserializer: Callable[[Union[str, bytes]], Any] = decode_json,
    ) -> None:
        """Initialize the PortalProvider."""
        self._registry: dict[str, StorageBackend] = {}
        self.json_serializer = json_serializer
        self.json_deserializer = json_deserializer

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

    def register_backend(self, key: str, value: "StorageBackend") -> None:
        """Register a new storage backend in the registry."""
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

    def get_file(self, key: str, path: str) -> bytes:
        """Retrieve a file object from the backend.

        Returns:
            FileMetadata object
        """
        return self.get_backend(key).get_content(path)

    async def get_file_async(self, key: str, path: str) -> bytes:
        """Retrieve a file object from the backend asynchronously.

        Returns:
            FileMetadata object
        """
        return await self.get_backend(key).get_content_async(path)

    def __contains__(self, key: str) -> bool:
        return key in self._registry


storages = StorageRegistry()


class StorageBackend(ABC):
    """Unified protocol for storage backend implementations supporting both sync and async operations."""

    backend: str
    """The name of the storage backend."""
    protocol: str
    """The protocol used by the storage backend."""

    def __init__(self, fs: Any, *, options: Optional[dict[str, Any]] = None, **kwargs: Any) -> None:
        """Initialize the storage backend.

        Args:
            fs: The storage backend instance
            options: Optional backend-specific options
            **kwargs: Additional keyword arguments
        """
        self.fs = fs
        self.options = options

    @staticmethod
    def _to_path(path: PathLike) -> str:
        """Convert a PathLike to a string path.

        Args:
            path: PathLike to convert

        Returns:
            str: The string path
        """
        if isinstance(path, str):
            return path
        return str(path)

    @abstractmethod
    def get_content(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options

        Returns:
            The file content as bytes
        """

    @abstractmethod
    async def get_content_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options

        Returns:
            The file content as bytes
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
        """Return the bytes stored at the specified location in the given byte range.

        Args:
            path: Path to the file
            start: Offset to start reading from
            end: Offset to stop reading at (inclusive)
            length: Number of bytes to read (alternative to end)

        Returns:
            The requested byte range
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
        """Return the bytes stored at the specified location in the given byte range asynchronously.

        Args:
            path: Path to the file
            start: Offset to start reading from
            end: Offset to stop reading at (inclusive)
            length: Number of bytes to read (alternative to end)

        Returns:
            The requested byte range
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
        """Return the bytes stored at the specified location in the given byte ranges.

        Args:
            path: Path to read from
            starts: A sequence of `int` where each offset starts.
            ends: A sequence of `int` where each offset ends (exclusive). Either `ends` or `lengths` must be non-None.
            lengths: A sequence of `int` with the number of bytes of each byte range. Either `ends` or `lengths` must be non-None.

        Returns:
            A sequence of `Bytes`, one for each range. This `Bytes` object implements the
                Python buffer protocol, allowing zero-copy access to the underlying memory
                provided by Rust.
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
        """Return the bytes stored at the specified location in the given byte ranges.

        Args:
            path: Path to read from
            starts: A sequence of `int` where each offset starts.
            ends: A sequence of `int` where each offset ends (exclusive). Either `ends` or `lengths` must be non-None.
            lengths: A sequence of `int` with the number of bytes of each byte range. Either `ends` or `lengths` must be non-None.

        Returns:
            A sequence of `Bytes`, one for each range. This `Bytes` object implements the
                Python buffer protocol, allowing zero-copy access to the underlying memory
                provided by Rust.
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
        """Save data to the specified path.

        Args:
            path: Destination path
            data: The data to save
            content_type: MIME type of the content
            metadata: Additional metadata to store
            use_multipart: Whether to use multipart upload
            chunk_size: Size of chunks for multipart uploads
            max_concurrency: Maximum concurrent uploads

        Returns:
            Information about the saved file
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
        """Save data to the specified path asynchronously.

        Args:
            path: Destination path
            data: The data to save
            content_type: MIME type of the content
            metadata: Additional metadata to store
            use_multipart: Whether to use multipart upload
            chunk_size: Size of chunks for multipart uploads
            max_concurrency: Maximum concurrent uploads

        Returns:
            Information about the saved file
        """

    @abstractmethod
    def delete(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s).

        Args:
            paths: Path or paths to delete
        """

    @abstractmethod
    async def delete_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s) asynchronously.

        Args:
            paths: Path or paths to delete
        """

    @abstractmethod
    def copy(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another in the same storage backend.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """

    @abstractmethod
    async def copy_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another in the same storage backend asynchronously.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """

    @abstractmethod
    def rename(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Move an object from one path to another in the same storage backend.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """

    @abstractmethod
    async def rename_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Move an object from one path to another in the same storage backend asynchronously.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """

    @abstractmethod
    def sign(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Create signed URLs for accessing or uploading a file

        Args:
            paths: The path or paths of the file
            expires_in: The expiration time of the URL in seconds
            http_method: The HTTP method to use for the URL
            for_upload: Whether the URL is for uploading a file

        Returns:
            A URL for accessing the file, or a tuple of (URL, token) for upload URLs
        """

    @abstractmethod
    async def sign_async(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Create a signed URL for accessing or uploading a file asynchronously.

        Args:
            paths: The path or paths of the file
            expires_in: The expiration time of the URL in seconds
            http_method: The HTTP method to use for the URL
            for_upload: Whether the URL is for uploading a file


        Returns:
            A URL for accessing the file, or a tuple of (URL, token) for upload URLs
        """

    @abstractmethod
    async def list_async(
        self,
        prefix: Optional[str] = None,
        *,
        delimiter: Optional[str] = None,
        offset: Optional[str] = None,
        limit: int = 50,
    ) -> list[FileObject]:
        """List objects with the given prefix asynchronously.

        Args:
            prefix: Prefix to filter by
            delimiter: Character to group results by
            offset: Token for pagination
            limit: Maximum number of results

        Returns:
            List of file information objects
        """

    @abstractmethod
    def list(
        self,
        prefix: Optional[str] = None,
        *,
        delimiter: Optional[str] = None,
        offset: Optional[str] = None,
        limit: int = 50,
    ) -> list[FileObject]:
        """List objects with the given prefix.

        Args:
            prefix: Prefix to filter by
            delimiter: Character to group results by
            offset: Token for pagination
            limit: Maximum number of results

        Returns:
            List of file information objects
        """

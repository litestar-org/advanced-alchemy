"""Generic unified storage protocol compatible with multiple backend implementations."""

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator, Sequence
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Optional, TypeVar, Union

from typing_extensions import TypeAlias

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.file import FileObject

# Type variables
T = TypeVar("T")
StorageBackendT = TypeVar("StorageBackendT", bound="StorageBackend")
PathLike: TypeAlias = Union[str, Path, os.PathLike[Any]]
DataLike: TypeAlias = Union[IO[bytes], Path, bytes, Iterator[bytes], Iterable[bytes]]
AsyncDataLike: TypeAlias = Union[
    IO[bytes], Path, bytes, AsyncIterator[bytes], AsyncIterable[bytes], Iterator[bytes], Iterable[bytes]
]


class StorageBackend(ABC):
    """Unified protocol for storage backend implementations supporting both sync and async operations."""

    driver: str
    """The name of the storage backend."""
    protocol: str
    """The protocol used by the storage backend."""
    key: str
    """The key of the backend instance."""

    def __init__(self, key: str, fs: Any, **kwargs: Any) -> None:
        """Initialize the storage backend.

        Args:
            key: The key of the backend instance
            fs: The filesystem or storage client
            **kwargs: Additional keyword arguments
        """
        self.fs = fs
        self.key = key
        self.options = kwargs

    @staticmethod
    def _to_path(path: "PathLike") -> str:
        """Convert a path-like object to a string.

        Args:
            path: The path to convert

        Returns:
            str: The string representation of the path
        """
        return str(path)

    @abstractmethod
    def get_content(self, path: "PathLike", *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the content of a file.

        Args:
            path: Path to the file
            options: Optional backend-specific options

        Returns:
            bytes: The file content
        """

    @abstractmethod
    async def get_content_async(self, path: "PathLike", *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the content of a file asynchronously.

        Args:
            path: Path to the file
            options: Optional backend-specific options

        Returns:
            bytes: The file content
        """

    @abstractmethod
    def save_object(
        self,
        file_object: "FileObject",
        data: "DataLike",
        *,
        use_multipart: "Optional[bool]" = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Store a file using information from a FileObject.

        Args:
            file_object: A FileObject instance containing metadata like path, content_type.
            data: The file data to store.
            use_multipart: Whether to use multipart upload.
            chunk_size: Size of chunks for multipart upload.
            max_concurrency: Maximum number of concurrent uploads.

        Returns:
            FileObject: The stored file object, potentially updated with backend info (size, etag, etc.).
        """

    @abstractmethod
    async def save_object_async(
        self,
        file_object: "FileObject",
        data: AsyncDataLike,
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Store a file asynchronously using information from a FileObject.

        Args:
            file_object: A FileObject instance containing metadata like path, content_type.
            data: The file data to store.
            use_multipart: Whether to use multipart upload.
            chunk_size: Size of chunks for multipart upload.
            max_concurrency: Maximum number of concurrent uploads.

        Returns:
            FileObject: The stored file object, potentially updated with backend info (size, etag, etc.).
        """

    @abstractmethod
    def delete_object(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete one or more files.

        Args:
            paths: Path or paths to delete
        """

    @abstractmethod
    async def delete_object_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete one or more files asynchronously.

        Args:
            paths: Path or paths to delete
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

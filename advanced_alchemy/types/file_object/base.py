"""Base classes and protocols for file object types."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional, Protocol, Union

from typing_extensions import TypeAlias

PathLike: TypeAlias = Union[str, Path]


class StorageBackend(Protocol):
    """Protocol defining the interface for storage backends."""

    def get(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend.

        Args:
            path: The path to the file
            options: Optional backend-specific options

        Returns:
            bytes: The file content
        """
        raise NotImplementedError

    async def get_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Get the file content from the storage backend asynchronously.

        Args:
            path: The path to the file
            options: Optional backend-specific options

        Returns:
            bytes: The file content
        """
        raise NotImplementedError

    def get_range(
        self,
        path: PathLike,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        """Get a range of bytes from the file.

        Args:
            path: The path to the file
            start: Starting byte offset
            end: Optional ending byte offset (inclusive)
            length: Optional number of bytes to read

        Returns:
            bytes: The requested byte range
        """
        raise NotImplementedError

    async def get_range_async(
        self,
        path: PathLike,
        *,
        start: int,
        end: Optional[int] = None,
        length: Optional[int] = None,
    ) -> bytes:
        """Get a range of bytes from the file asynchronously.

        Args:
            path: The path to the file
            start: Starting byte offset
            end: Optional ending byte offset (inclusive)
            length: Optional number of bytes to read

        Returns:
            bytes: The requested byte range
        """
        raise NotImplementedError

    def get_ranges(
        self,
        path: PathLike,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> list[bytes]:
        """Get multiple ranges of bytes from the file.

        Args:
            path: The path to the file
            starts: Sequence of starting byte offsets
            ends: Optional sequence of ending byte offsets (inclusive)
            lengths: Optional sequence of lengths to read

        Returns:
            list[bytes]: The requested byte ranges
        """
        raise NotImplementedError

    async def get_ranges_async(
        self,
        path: PathLike,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> list[bytes]:
        """Get multiple ranges of bytes from the file asynchronously.

        Args:
            path: The path to the file
            starts: Sequence of starting byte offsets
            ends: Optional sequence of ending byte offsets (inclusive)
            lengths: Optional sequence of lengths to read

        Returns:
            list[bytes]: The requested byte ranges
        """
        raise NotImplementedError

    def sign(
        self,
        path: PathLike,
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> str:
        """Get a signed URL for accessing or uploading the file.

        Args:
            path: The path to the file
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for uploading

        Returns:
            str: The signed URL
        """
        raise NotImplementedError

    async def sign_async(
        self,
        path: PathLike,
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> str:
        """Get a signed URL for accessing or uploading the file asynchronously.

        Args:
            path: The path to the file
            expires_in: Optional expiration time in seconds
            for_upload: Whether the URL is for uploading

        Returns:
            str: The signed URL
        """
        raise NotImplementedError

    def delete(self, path: PathLike) -> None:
        """Delete the file from the storage backend.

        Args:
            path: The path to the file
        """
        raise NotImplementedError

    async def delete_async(self, path: PathLike) -> None:
        """Delete the file from the storage backend asynchronously.

        Args:
            path: The path to the file
        """
        raise NotImplementedError

    def copy(self, from_path: PathLike, to_path: PathLike, *, overwrite: bool = True) -> None:
        """Copy the file to another location in the same backend.

        Args:
            from_path: Source path
            to_path: Destination path
            overwrite: Whether to overwrite existing files
        """
        raise NotImplementedError

    async def copy_async(self, from_path: PathLike, to_path: PathLike, *, overwrite: bool = True) -> None:
        """Copy the file to another location in the same backend asynchronously.

        Args:
            from_path: Source path
            to_path: Destination path
            overwrite: Whether to overwrite existing files
        """
        raise NotImplementedError

    def rename(self, from_path: PathLike, to_path: PathLike, *, overwrite: bool = True) -> None:
        """Move the file to another location in the same backend.

        Args:
            from_path: Source path
            to_path: Destination path
            overwrite: Whether to overwrite existing files
        """
        raise NotImplementedError

    async def rename_async(self, from_path: PathLike, to_path: PathLike, *, overwrite: bool = True) -> None:
        """Move the file to another location in the same backend asynchronously.

        Args:
            from_path: Source path
            to_path: Destination path
            overwrite: Whether to overwrite existing files
        """
        raise NotImplementedError

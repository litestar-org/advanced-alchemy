# ruff: noqa: PLR0904
"""Obstore-backed storage backend for file objects."""

import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union, cast

from obstore import sign as obstore_sign
from obstore import sign_async as obstore_sign_async
from obstore._scheme import parse_scheme  # pyright: ignore[reportMissingModuleSource]
from obstore.store import ObjectStore
from typing_extensions import Self

from advanced_alchemy.types.file_object.base import (
    AsyncDataLike,
    DataLike,
    FileInfo,
    PathLike,
    StorageBackend,
)


def get_mtime_equivalent(info: dict[str, Any]) -> Optional[float]:
    """Return standardized mtime from different implementations.

    Args:
        info: Dictionary containing file metadata

    Returns:
        Standardized timestamp or None if not available
    """
    # Check these keys in order of preference
    mtime_keys = (
        "mtime",
        "last_modified",
        "uploaded_at",
        "timestamp",
        "Last-Modified",
        "modified_at",
        "modification_time",
    )
    mtime = next((info[key] for key in mtime_keys if key in info), None)

    if mtime is None or isinstance(mtime, float):
        return mtime
    if isinstance(mtime, datetime):
        return mtime.timestamp()
    if isinstance(mtime, str):
        try:
            return datetime.fromisoformat(mtime.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return None


def scheme_from_url(url: str) -> str:
    """Extract the schema from a URL.

    Args:
        url: URL to parse

    Returns:
        The schema extracted from the URL
    """
    return parse_scheme(url)


def schema_from_type(obj: Any) -> str:  # noqa: PLR0911
    """Extract the schema from an object.

    Args:
        obj: Object to parse

    Returns:
        The schema extracted from the object
    """
    from obstore.store import AzureStore, GCSStore, HTTPStore, LocalStore, MemoryStore, S3Store

    if isinstance(obj, S3Store):
        return "s3"
    if isinstance(obj, AzureStore):
        return "azure"
    if isinstance(obj, GCSStore):
        return "gcs"
    if isinstance(obj, LocalStore):
        return "file"
    if isinstance(obj, HTTPStore):
        return "http"
    if isinstance(obj, MemoryStore):  # type: ignore
        return "memory"
    return "file"


class ObstoreBackend(StorageBackend):
    """Obstore-backed storage backend implementing both sync and async operations."""

    backend = "obstore"

    def __init__(self, fs: Union[ObjectStore, str], name: str) -> None:
        """Initialize ObstoreBackend.

        Args:
            fs: The ObjectStore instance from the obstore package
            name: The name of the backend instance

        """

        if isinstance(fs, str):
            self.protocol = scheme_from_url(fs)
            self.fs = cast("ObjectStore", ObjectStore.from_url(fs))  # type: ignore
        else:
            self.protocol = schema_from_type(fs)
            self.fs = fs
        self.name = name

    def get(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options
        """
        options = options or {}
        obj = self.fs.get(self._to_path(path), **options)
        return obj.bytes().to_bytes()

    async def get_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options
        """
        options = options or {}
        obj = await self.fs.get_async(self._to_path(path), **options)
        return (await obj.bytes_async()).to_bytes()

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
            path: Path to retrieve
            start: Start byte index
            end: End byte index
            length: Number of bytes to retrieve
        """
        obj = self.fs.get_range(self._to_path(path), start=start, end=end, length=length)
        return obj.to_bytes()

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
            path: Path to retrieve
            start: Start byte index
            end: End byte index
            length: Number of bytes to retrieve
        """
        obj = await self.fs.get_range_async(self._to_path(path), start=start, end=end, length=length)
        return obj.to_bytes()

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
            path: Path to retrieve
            starts: Start byte indices
            ends: End byte indices
            lengths: Number of bytes to retrieve
        """
        obj = self.fs.get_ranges(self._to_path(path), starts=starts, ends=ends, lengths=lengths)
        return [o.to_bytes() for o in obj]

    async def get_ranges_async(
        self,
        path: PathLike,
        *,
        starts: Sequence[int],
        ends: Optional[Sequence[int]] = None,
        lengths: Optional[Sequence[int]] = None,
    ) -> list[bytes]:
        """Return the bytes stored at the specified location in the given byte ranges asynchronously.

        Args:
            path: Path to retrieve
            starts: Start byte indices
            ends: End byte indices
            lengths: Number of bytes to retrieve
        """
        obj = await self.fs.get_ranges_async(self._to_path(path), starts=starts, ends=ends, lengths=lengths)
        return [o.to_bytes() for o in obj]

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
    ) -> FileInfo[Self]:
        """Save data to the specified path.

        Args:
            path: Destination path
            data: The data to save
            content_type: MIME type of the content
            metadata: Additional metadata
            use_multipart: Whether to use multipart upload
            chunk_size: Size of each chunk in bytes
            max_concurrency: Maximum number of concurrent uploads

        Returns:
            A FileInfo object representing the saved file
        """
        obj = self.fs.put(
            self._to_path(path),
            data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )
        return FileInfo[Self](
            backend=self,
            name=self.name,
            protocol=self.protocol,
            filename=obj.name,
            path=obj.path,
            size=obj.size,
            checksum=obj.checksum,
            content_type=obj.content_type,
            last_modified=obj.last_modified,
            etag=obj.get("etag"),
            version_id=obj.get("version"),
            metadata=obj.metadata,
        )

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
    ) -> FileInfo[Self]:
        """Save data to the specified path asynchronously.

        Args:
            path: Destination path
            data: The data to save
            content_type: MIME type of the content
            metadata: Additional metadata
            use_multipart: Whether to use multipart upload
            chunk_size: Size of each chunk in bytes
            max_concurrency: Maximum number of concurrent uploads

        Returns:
            A FileInfo object representing the saved file
        """
        obj = await self.fs.put_async(
            self._to_path(path),
            data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )
        return FileInfo[Self](
            backend=self,
            name=self.name,
            protocol=self.protocol,
            size=obj.size,
            checksum=obj.checksum,
            content_type=obj.content_type,
            last_modified=obj.last_modified,
            etag=obj.get("etag"),
            version_id=obj.get("version"),
            metadata=obj.metadata,
        )

    def delete(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the specified paths.

        Args:
            paths: Path or paths to delete
        """
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        self.fs.delete(path_list)

    async def delete_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the specified paths asynchronously.

        Args:
            paths: Path or paths to delete
        """
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        await self.fs.delete_async(path_list)

    def copy(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """
        self.fs.copy(self._to_path(from_), self._to_path(to), overwrite=overwrite)

    async def copy_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another asynchronously.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """
        await self.fs.copy_async(self._to_path(from_), self._to_path(to), overwrite=overwrite)

    def rename(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename an object.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """
        self.fs.rename(self._to_path(from_), self._to_path(to), overwrite=overwrite)

    async def rename_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename an object asynchronously.

        Args:
            from_: Source path
            to: Destination path
            overwrite: Whether to overwrite existing files
        """
        await self.fs.rename_async(self._to_path(from_), self._to_path(to), overwrite=overwrite)

    def sign(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Sign a URL for a given path.

        Args:
            paths: Path to sign
            expires_in: Expiration time in seconds
            for_upload: Whether the URL is for uploading a file

        Returns:
            A URL or list of URLs for accessing the file
        """
        http_method = "PUT" if for_upload else "GET"

        if isinstance(paths, (str, Path, os.PathLike)):
            single_path = self._to_path(paths)
            return obstore_sign(store=self.fs, http_method=http_method, paths=single_path, expires_in=expires_in)  # type: ignore

        path_list = [self._to_path(p) for p in paths]
        return obstore_sign(store=self.fs, http_method=http_method, paths=path_list, expires_in=expires_in)  # type: ignore

    async def sign_async(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Sign a URL for a given path asynchronously.

        Args:
            paths: Path to sign
            expires_in: Expiration time in seconds
            for_upload: Whether the URL is for uploading a file

        Returns:
            A URL or list of URLs for accessing the file
        """
        http_method = "PUT" if for_upload else "GET"

        if isinstance(paths, (str, Path, os.PathLike)):
            single_path = self._to_path(paths)
            return await obstore_sign_async(
                store=self.fs, http_method=http_method, paths=single_path, expires_in=expires_in
            )  # type: ignore

        path_list = [self._to_path(p) for p in paths]
        return await obstore_sign_async(store=self.fs, http_method=http_method, paths=path_list, expires_in=expires_in)  # type: ignore

    async def list_async(
        self,
        prefix: Optional[str] = None,
        *,
        offset: Optional[str] = None,
        limit: int = 50,
    ) -> list[FileInfo[Self]]:
        """List objects with the given prefix asynchronously.

        Args:
            prefix: Prefix to filter by
            offset: Token for pagination
            limit: Maximum number of results

        Returns:
            A list of file information objects
        """
        objs = await self.fs.list_async(prefix=prefix, offset=offset, limit=limit)

        return [
            FileInfo[Self](
                backend=self,
                filename=obj.name,
                path=obj.path,
                uploaded_at=obj.uploaded_at,
                size=obj.size,
                checksum=obj.checksum,
                content_type=obj.content_type,
                last_modified=obj.last_modified,
                etag=obj.etag,
                version_id=obj.version_id,
                metadata=obj.metadata,
            )
            for obj in objs
        ]

    def list(
        self,
        prefix: Optional[str] = None,
        *,
        offset: Optional[str] = None,
        limit: int = 50,
    ) -> list[FileInfo[Self]]:
        """List objects with the given prefix.

        Args:
            prefix: Prefix to filter by
            delimiter: Character to group results by
            offset: Token for pagination
            limit: Maximum number of results

        Returns:
            A list of file information objects
        """
        objs = self.fs.list(prefix=prefix, offset=offset, limit=limit)

        return [
            FileInfo[Self](
                backend=self,
                filename=obj.name,
                path=obj.path,
                uploaded_at=obj.uploaded_at,
                size=obj.size,
                checksum=obj.checksum,
                content_type=obj.content_type,
                last_modified=obj.last_modified,
                etag=obj.etag,
                version_id=obj.version_id,
                metadata=obj.metadata,
            )
            for obj in objs
        ]

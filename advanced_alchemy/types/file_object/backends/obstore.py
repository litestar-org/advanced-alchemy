"""Obstore-backed storage backend for file objects."""

import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.file_object._utils import get_mtime_equivalent, get_or_generate_etag
from advanced_alchemy.types.file_object.base import (
    AsyncDataLike,
    DataLike,
    PathLike,
    StorageBackend,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from advanced_alchemy.types.file_object.file import FileObject

try:
    from obstore import sign as obstore_sign
    from obstore import sign_async as obstore_sign_async
    from obstore.store import ObjectStore, from_url

except ImportError as e:
    raise MissingDependencyError(package="obstore") from e


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
    if isinstance(obj, MemoryStore):
        return "memory"
    return "file"


class ObstoreBackend(StorageBackend):
    """Obstore-backed storage backend implementing both sync and async operations."""

    driver = "obstore"

    def __init__(self, key: str, fs: "Union[ObjectStore, str]", **kwargs: "Any") -> None:
        """Initialize ObstoreBackend.

        Args:
            fs: The ObjectStore instance from the obstore package
            key: The key for the storage backend
            kwargs: Additional keyword arguments to pass to the ObjectStore constructor
        """
        self.fs = from_url(fs, **kwargs) if isinstance(fs, str) else fs  # pyright: ignore
        self.protocol = schema_from_type(self.fs)  # pyright: ignore
        self.key = key
        self.options = kwargs

    def get_content(self, path: "PathLike", *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Return the bytes stored at the specified location.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options
        """
        options = options or {}
        # Filter out unsupported options
        supported_options = {
            k: v for k, v in options.items() if k in {"use_multipart", "chunk_size", "max_concurrency"}
        }
        obj = self.fs.get(self._to_path(path), **supported_options)
        return obj.bytes().to_bytes()  # type: ignore[no-any-return]

    async def get_content_async(self, path: "PathLike", *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options
        """
        options = options or {}
        # Filter out unsupported options
        supported_options = {
            k: v for k, v in options.items() if k in {"use_multipart", "chunk_size", "max_concurrency"}
        }
        obj = await self.fs.get_async(self._to_path(path), **supported_options)
        return (await obj.bytes_async()).to_bytes()  # type: ignore[no-any-return]

    def save_object(
        self,
        file_object: "FileObject",
        data: "DataLike",
        *,
        use_multipart: "Optional[bool]" = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the specified path using info from FileObject.

        Args:
            file_object: FileObject instance with metadata (path, content_type, etc.).
            data: The data to save.
            use_multipart: Whether to use multipart upload.
            chunk_size: Size of each chunk in bytes.
            max_concurrency: Maximum number of concurrent uploads.

        Returns:
            A FileObject object representing the saved file, potentially updated.

        """
        _ = self.fs.put(
            file_object.path,
            data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )
        info = self.fs.head(file_object.path)
        file_object.size = cast("int", info.get("size", file_object.size))  # pyright: ignore
        file_object.last_modified = (
            get_mtime_equivalent(info) or datetime.datetime.now(tz=datetime.timezone.utc).timestamp()  # pyright: ignore
        )
        file_object.etag = get_or_generate_etag(file_object, info, file_object.last_modified)  # pyright: ignore
        # Merge backend metadata if available and different
        backend_meta: dict[str, Any] = info.get("metadata", {})  # pyright: ignore
        if backend_meta and backend_meta != file_object.metadata:
            file_object.update_metadata(backend_meta)  # pyright: ignore

        return file_object

    async def save_object_async(
        self,
        file_object: "FileObject",
        data: "AsyncDataLike",
        *,
        use_multipart: "Optional[bool]" = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the specified path asynchronously using info from FileObject.

        Args:
            file_object: FileObject instance with metadata (path, content_type, etc.).
            data: The data to save.
            use_multipart: Whether to use multipart upload.
            chunk_size: Size of each chunk in bytes.
            max_concurrency: Maximum number of concurrent uploads.

        Returns:
            A FileObject object representing the saved file, potentially updated.

        """
        _ = await self.fs.put_async(
            file_object.path,
            data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )
        info = await self.fs.head_async(file_object.path)
        file_object.size = cast("int", info.get("size", file_object.size))  # pyright: ignore
        file_object.last_modified = (
            get_mtime_equivalent(info) or datetime.datetime.now(tz=datetime.timezone.utc).timestamp()  # pyright: ignore
        )
        file_object.etag = get_or_generate_etag(file_object, info, file_object.last_modified)  # pyright: ignore
        # Merge backend metadata if available and different
        backend_meta: dict[str, Any] = info.get("metadata", {})  # pyright: ignore
        if backend_meta and backend_meta != file_object.metadata:
            file_object.update_metadata(backend_meta)  # pyright: ignore

        return file_object

    def delete_object(self, paths: "Union[PathLike, Sequence[PathLike]]") -> None:
        """Delete the specified paths.

        Args:
            paths: Path or paths to delete
        """
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        self.fs.delete(path_list)

    async def delete_object_async(self, paths: "Union[PathLike, Sequence[PathLike]]") -> None:
        """Delete the specified paths asynchronously.

        Args:
            paths: Path or paths to delete
        """
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        await self.fs.delete_async(path_list)

    def sign(
        self,
        paths: "Union[PathLike, Sequence[PathLike]]",
        *,
        expires_in: "Optional[int]" = None,
        for_upload: bool = False,
    ) -> "Union[str, list[str]]":
        """Create a signed URL for accessing or uploading the file.

        Args:
            paths: The path or list of paths of the file
            expires_in: The expiration time of the URL in seconds
            for_upload: If True, generates a URL suitable for uploads (e.g., presigned POST)

        Returns:
            A URL or list of URLs for accessing the file
        """
        http_method = "PUT" if for_upload else "GET"
        expires_delta = (
            datetime.timedelta(seconds=expires_in) if expires_in is not None else datetime.timedelta(hours=1)
        )
        if isinstance(paths, (str, Path, os.PathLike)):
            single_path = self._to_path(paths)
            try:
                return obstore_sign(store=self.fs, method=http_method, paths=single_path, expires_in=expires_delta)  # type: ignore
            except ValueError as e:
                msg = f"Error signing path {single_path}: {e}"
                raise NotImplementedError(msg) from e

        path_list = [self._to_path(p) for p in paths]
        try:
            return obstore_sign(store=self.fs, method=http_method, paths=path_list, expires_in=expires_delta)  # type: ignore
        except ValueError as e:
            msg = f"Error signing paths {path_list}: {e}"
            raise NotImplementedError(msg) from e

    async def sign_async(
        self,
        paths: "Union[PathLike, Sequence[PathLike]]",
        *,
        expires_in: "Optional[int]" = None,
        for_upload: bool = False,
    ) -> "Union[str, list[str]]":
        """Sign a URL for a given path asynchronously.

        Args:
            paths: Path to sign
            expires_in: Expiration time in seconds
            for_upload: Whether the URL is for uploading a file

        Returns:
            A URL or list of URLs for accessing the file
        """
        http_method = "PUT" if for_upload else "GET"
        expires_delta = (
            datetime.timedelta(seconds=expires_in) if expires_in is not None else datetime.timedelta(hours=1)
        )
        if isinstance(paths, (str, Path, os.PathLike)):
            single_path = self._to_path(paths)
            try:
                return await obstore_sign_async(  # type: ignore
                    store=self.fs,  # pyright: ignore
                    method=http_method,
                    paths=single_path,
                    expires_in=expires_delta,
                )
            except ValueError as e:
                msg = f"Error signing path {single_path}: {e}"
                raise NotImplementedError(msg) from e

        path_list = [self._to_path(p) for p in paths]
        try:
            return await obstore_sign_async(  # type: ignore
                store=self.fs,  # pyright: ignore
                method=http_method,
                paths=path_list,
                expires_in=expires_delta,
            )
        except ValueError as e:
            msg = f"Error signing paths {path_list}: {e}"
            raise NotImplementedError(msg) from e

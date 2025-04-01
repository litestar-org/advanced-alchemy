# ruff: noqa: PLR0904, PLC2701
"""Obstore-backed storage backend for file objects."""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.file_object._utils import get_etag_equivalent, get_mtime_equivalent
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

    def __init__(
        self, fs: "Union[ObjectStore, str]", key: str, *, options: "Optional[dict[str, Any]]" = None, **kwargs: "Any"
    ) -> None:
        """Initialize ObstoreBackend.

        Args:
            fs: The ObjectStore instance from the obstore package
            key: The key for the storage backend
            options: Optional backend-specific options
            kwargs: Additional keyword arguments
        """
        self.fs = from_url(fs) if isinstance(fs, str) else fs
        self.protocol = schema_from_type(self.fs)
        self.key = key
        self.options = options or {}
        self.kwargs = kwargs

    def get_content(self, path: "PathLike", *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Return the bytes stored at the specified location.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options
        """
        options = options or {}
        obj = self.fs.get(self._to_path(path), **options)
        return obj.bytes().to_bytes()  # type: ignore[no-any-return]

    async def get_content_async(self, path: "PathLike", *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options
        """
        options = options or {}
        obj = await self.fs.get_async(self._to_path(path), **options)
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

        # Extract info, though obstore might ignore some
        path_str = self._to_path(file_object.path)
        # Note: obstore.put might not explicitly support content_type/metadata args
        # Check obstore documentation if these are needed or handled differently
        obj_info = self.fs.put(
            path_str,
            data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Update the original FileObject with info returned by obstore
        file_object.size = obj_info.get("size")
        file_object.checksum = obj_info.get("checksum")
        file_object.last_modified = get_mtime_equivalent(obj_info)  # pyright: ignore
        file_object.etag = get_etag_equivalent(dict(obj_info))
        file_object.version_id = obj_info.get("version")
        file_object.update_metadata(dict(obj_info))
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

        # Extract info, though obstore might ignore some
        path_str = self._to_path(file_object.path)
        # Note: obstore.put_async might not explicitly support content_type/metadata args
        # Check obstore documentation if these are needed or handled differently
        obj_info = await self.fs.put_async(
            path_str,
            data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Update the original FileObject with info returned by obstore
        # Assuming obj_info is a dict-like structure or object with attributes
        # Use .get() consistently for safer access
        file_object.size = obj_info.get("size")
        file_object.checksum = obj_info.get("checksum")
        # Pass obj_info as dict to helper function
        file_object.last_modified = get_mtime_equivalent(obj_info)  # pyright: ignore
        file_object.etag = get_etag_equivalent(dict(obj_info))
        file_object.version_id = obj_info.get("version")
        # Merge metadata if returned by backend
        file_object.update_metadata(dict(obj_info))

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

        if isinstance(paths, (str, Path, os.PathLike)):
            single_path = self._to_path(paths)
            return obstore_sign(store=self.fs, http_method=http_method, paths=single_path, expires_in=expires_in)  # type: ignore

        path_list = [self._to_path(p) for p in paths]
        return obstore_sign(store=self.fs, http_method=http_method, paths=path_list, expires_in=expires_in)  # type: ignore

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

        if isinstance(paths, (str, Path, os.PathLike)):
            single_path = self._to_path(paths)
            return await obstore_sign_async(  # type: ignore
                store=self.fs, http_method=http_method, paths=single_path, expires_in=expires_in
            )

        path_list = [self._to_path(p) for p in paths]
        return await obstore_sign_async(store=self.fs, http_method=http_method, paths=path_list, expires_in=expires_in)  # type: ignore

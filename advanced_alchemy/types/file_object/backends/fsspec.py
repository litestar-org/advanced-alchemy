# advanced_alchemy/types/file_object/backends/fsspec.py
# ruff: noqa: PLR0904, SLF001, PLR1702, PLR6301
"""FSSpec-backed storage backend for file objects."""

import datetime
import os
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Sequence
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Optional, Union, cast

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.file_object._utils import get_mtime_equivalent, get_or_generate_etag
from advanced_alchemy.types.file_object.base import (
    PathLike,
    StorageBackend,
)
from advanced_alchemy.types.file_object.file import FileObject
from advanced_alchemy.utils.sync_tools import async_

try:
    # Correct import for AsyncFileSystem and try importing async file handle
    import fsspec  # pyright: ignore[reportMissingTypeStubs]
    from fsspec.asyn import AsyncFileSystem  # pyright: ignore[reportMissingTypeStubs]
except ImportError as e:
    msg = "fsspec"
    raise MissingDependencyError(msg) from e


if TYPE_CHECKING:
    from fsspec import AbstractFileSystem  # pyright: ignore[reportMissingTypeStubs]


class FSSpecBackend(StorageBackend):
    """FSSpec-backed storage backend implementing both sync and async operations."""

    driver = "fsspec"  # Changed backend identifier to driver
    default_expires_in = 3600

    def __init__(
        self,
        fs: "Union[AbstractFileSystem, AsyncFileSystem, str]",
        key: str,
        *,
        options: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize FSSpecBackend.

        Args:
            fs: The FSSpec filesystem instance (sync or async).
            key: The key of the backend instance.
            options: Optional backend-specific options.
            **kwargs: Additional keyword arguments.
        """
        self.fs = fsspec.filesystem(fs, **options or {}) if isinstance(fs, str) else fs  # pyright: ignore
        self.is_async = isinstance(self.fs, AsyncFileSystem)
        protocol = getattr(self.fs, "protocol", None)
        protocol = cast("Optional[str]", protocol[0] if isinstance(protocol, (list, tuple)) else protocol)
        self.protocol = protocol or "file"
        self.key = key
        self.options = options or {}
        self.kwargs = kwargs

    def get_content(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options passed to fsspec's open.
        """
        content = self.fs.cat_file(self._to_path(path), **(options or {}))  # pyright: ignore
        if isinstance(content, str):
            return content.encode("utf-8")
        return cast("bytes", content)

    async def get_content_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options passed to fsspec's open.

        """
        if not self.is_async:
            # Fallback for sync filesystems - Note: get_content is sync, wrapping with async_
            return await async_(self.get_content)(path=path, options=options)
        content = await self.fs._cat_file(self._to_path(path), **(options or {}))  # pyright: ignore
        if isinstance(content, str):
            return content.encode("utf-8")
        return cast("bytes", content)

    def save_object(
        self,
        file_object: FileObject,
        data: Union[bytes, IO[bytes], Path, Iterable[bytes]],
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> FileObject:
        """Save data to the specified path using info from FileObject.

        Args:
            file_object: FileObject instance with metadata (path, content_type, etc.)
            data: The data to save (bytes, byte iterator, file-like object, Path)
            use_multipart: Ignored.
            chunk_size: Size of chunks when reading from IO/Path.
            max_concurrency: Ignored.

        Returns:
            FileObject object representing the saved file, potentially updated.
        """
        if isinstance(data, Path):
            self.fs.put(file_object.path, data)  # pyright: ignore
        else:
            self.fs.pipe(file_object.path, data)  # pyright: ignore

        info = file_object.to_dict()
        fs_info = self.fs.info(file_object.path)  # pyright: ignore
        if isinstance(fs_info, dict):
            info.update(fs_info)  # pyright: ignore
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
        file_object: FileObject,
        data: Union[bytes, IO[bytes], Path, Iterable[bytes], AsyncIterable[bytes]],
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> FileObject:
        """Save data to the specified path asynchronously using info from FileObject.

        Args:
            file_object: FileObject instance with metadata (path, content_type, etc.)
            data: The data to save (bytes, async byte iterator, file-like object, Path)
            use_multipart: Ignored.
            chunk_size: Size of chunks when reading from IO/Path/AsyncIterator.
            max_concurrency: Ignored.



        Returns:
            FileObject object representing the saved file, potentially updated.
        """

        if not self.is_async:
            # Fallback for sync filesystems. Handle async data carefully.
            if isinstance(data, (AsyncIterator, AsyncIterable)) and not isinstance(data, (bytes, str)):
                # Read async stream into memory for sync backend (potential memory issue)
                all_data = b"".join([chunk async for chunk in data])
                return await async_(self.save_object)(file_object=file_object, data=all_data, chunk_size=chunk_size)
            return await async_(self.save_object)(file_object=file_object, data=data, chunk_size=chunk_size)  # type: ignore

        if isinstance(data, Path):
            await self.fs._put(file_object.path, data)  # pyright: ignore
        else:
            await self.fs._pipe(file_object.path, data)  # pyright: ignore
        info = file_object.to_dict()
        fs_info = self.fs._info(file_object.path)  # pyright: ignore
        if isinstance(fs_info, dict):
            info.update(fs_info)  # pyright: ignore
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

    def delete_object(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s).

        Args:
            paths: Path or sequence of paths to delete.
        """
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        self.fs.rm(path_list, recursive=False)  # pyright: ignore

    async def delete_object_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s) asynchronously.

        Args:
            paths: Path or sequence of paths to delete.
        """
        if not self.is_async:
            return await async_(self.delete_object)(paths=paths)

        path_list = (
            [self._to_path(paths)] if isinstance(paths, (str, Path, os.PathLike)) else [self._to_path(p) for p in paths]
        )
        await self.fs._rm(path_list, recursive=False)  # pyright: ignore
        return None

    def sign(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,  # Often not directly supported by generic fsspec sign
    ) -> Union[str, list[str]]:
        """Create signed URLs for accessing files.

        Note: Upload URL generation (`for_upload=True`) is generally not supported
              by fsspec's generic `sign` method. This typically requires
              backend-specific methods (e.g., S3 presigned POST URLs).

        Args:
            paths: The path or paths of the file(s).
            expires_in: The expiration time of the URL in seconds (backend-dependent default).
            for_upload: If True, attempt to generate an upload URL (likely unsupported).

        Returns:
            A signed URL string if a single path is given, or a list of strings
            if multiple paths are provided.

        Raises:
            NotImplementedError: If the backend doesn't support signing or if `for_upload=True`.
        """
        if for_upload:
            msg = "Generating signed URLs for upload is generally not supported by fsspec's generic sign method."
            raise NotImplementedError(msg)
        expires_in = expires_in or self.default_expires_in
        is_single = isinstance(paths, (str, Path, os.PathLike))
        path_list = [self._to_path(paths)] if is_single else [self._to_path(p) for p in paths]  # type: ignore
        if not hasattr(self.fs, "sign"):
            msg = f"Filesystem object {type(self.fs).__name__} does not have a 'sign' method."
            raise NotImplementedError(msg)
        signed_urls: list[str] = []
        try:
            # fsspec sign method might take expiration in seconds
            # Ensure this is a list comprehension, not a generator expression
            signed_urls.extend([self.fs.sign(path_str, expiration=expires_in) for path_str in path_list])  # pyright: ignore
        except NotImplementedError as e:
            # This might be raised by the sign method itself if not implemented for the protocol
            msg = f"Signing URLs not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e

        return signed_urls[0] if is_single else signed_urls  # pyright: ignore

    async def sign_async(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Create signed URLs for accessing files asynchronously.

        See notes in the synchronous `sign` method regarding `for_upload` limitations.

        Args:
            paths: The path or paths of the file(s).
            expires_in: The expiration time of the URL in seconds.
            for_upload: If True, attempt to generate an upload URL (likely unsupported).

        Returns:
            A signed URL string or a list of strings.

        Raises:
            NotImplementedError: If the backend doesn't support async signing or if `for_upload=True`.
        """
        if not self.is_async:
            return await async_(self.sign)(paths=paths, expires_in=expires_in, for_upload=for_upload)

        if for_upload:
            msg = "Generating signed URLs for upload is generally not supported by fsspec's generic sign method."
            raise NotImplementedError(msg)
        expires_in = expires_in or self.default_expires_in
        is_single = isinstance(paths, (str, Path, os.PathLike))
        path_list = [self._to_path(paths)] if is_single else [self._to_path(p) for p in paths]  # type: ignore
        if not hasattr(self.fs, "sign"):
            msg = f"Async filesystem object {type(self.fs).__name__} does not have a 'sign' method."
            raise NotImplementedError(msg)
        signed_urls: list[str] = []
        try:
            signed_urls.extend([await self.fs.sign(path_str, expiration=expires_in) for path_str in path_list])  # pyright: ignore
        except NotImplementedError as e:
            msg = f"Async signing URLs not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e

        return signed_urls[0] if is_single else signed_urls  # pyright: ignore

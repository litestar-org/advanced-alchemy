# advanced_alchemy/types/file_object/backends/fsspec.py
# ruff: noqa: PLR0904, SLF001, PLR1702
"""FSSpec-backed storage backend for file objects."""

import os
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator, Sequence
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Optional, Union, cast

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.file_object._utils import get_mtime_equivalent
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
    from fsspec.spec import AbstractBufferedFile  # pyright: ignore[reportMissingTypeStubs]


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
        options = options or {}
        path_str = self._to_path(path)
        fs = cast("AbstractFileSystem", self.fs)  # Cast for type checker
        with fs.open(path_str, "rb", **options) as f:  # pyright: ignore
            # Ensure f is treated as a file handle supporting read
            # Using AbstractBufferedFile which is common for fsspec file-like objects
            f_handle = cast("AbstractBufferedFile", f)
            return f_handle.read()  # type: ignore[no-any-return]

    async def get_content_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options passed to fsspec's open.

        """
        if not self.is_async:
            # Fallback for sync filesystems - Note: get_content is sync, wrapping with async_
            return await async_(self.get_content)(path=path, options=options)

        options = options or {}
        path_str = self._to_path(path)
        fs = cast("AsyncFileSystem", self.fs)
        async with fs.open(path_str, mode="rb", **options) as f:  # pyright: ignore
            return await f.read()  # type: ignore[no-any-return]

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

        Raises:
            TypeError: If the data type is unsupported.
            FileNotFoundError: If data is a Path and does not exist.

        Returns:
            FileObject object representing the saved file, potentially updated.
        """

        fs = cast("AbstractFileSystem", self.fs)

        with fs.open(file_object.path, "wb") as f:  # pyright: ignore
            # Use AbstractBufferedFile for the opened file handle type hint
            f_handle = cast("AbstractBufferedFile", f)
            if isinstance(data, bytes):
                f_handle.write(data)  # pyright: ignore
                size = len(data)
            elif isinstance(data, (Iterator, Iterable)):
                size = 0
                for chunk in data:
                    f_handle.write(chunk)  # pyright: ignore
                    size += len(chunk)  # type: ignore
            elif isinstance(data, IO):
                size = 0
                while True:
                    chunk = data.read(chunk_size)  # pyright: ignore
                    if not chunk:
                        break
                    f_handle.write(chunk)  # pyright: ignore
                    size += len(chunk)  # type: ignore
            elif isinstance(data, Path):  # pyright: ignore
                if not data.is_file():
                    raise FileNotFoundError(data)
                size = data.stat().st_size
                with data.open("rb") as source_f:
                    while True:
                        chunk = source_f.read(chunk_size)
                        if not chunk:
                            break
                        f_handle.write(chunk)  # pyright: ignore
            else:
                msg = f"Unsupported data type: {type(data)}"  # type: ignore
                raise TypeError(msg)

        # Try to get info after writing
        try:
            info = fs.info(file_object.path)  # pyright: ignore
            if not isinstance(info, dict):
                info: dict[str, Any] = {"size": 0, "mtime": None, "etag": None, "metadata": {}}  # type: ignore[no-redef]
            file_object.size = cast("int", info.get("size", size))  # pyright: ignore
            file_object.last_modified = get_mtime_equivalent(info)  # pyright: ignore
            file_object.etag = info.get("etag")  # pyright: ignore
            # Merge backend metadata if available and different
            backend_meta: dict[str, Any] = info.get("metadata", {})  # pyright: ignore
            if backend_meta and backend_meta != file_object.metadata:
                file_object.update_metadata(backend_meta)  # pyright: ignore

        except (FileNotFoundError, NotImplementedError):
            # Backend couldn't provide info, rely on calculated/provided data
            file_object.size = size

        return file_object

    async def save_object_async(  # noqa: C901, PLR0915
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

        Raises:
            TypeError: If the filesystem is not async or data type is not supported.
            FileNotFoundError: If data is a Path and does not exist.

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

        fs = cast("AsyncFileSystem", self.fs)
        path_str = self._to_path(file_object.path)
        size: Optional[int] = None

        # Let type inference work for f, add ignore for context manager protocol errors
        async with fs.open(path_str, "wb") as f:  # pyright: ignore
            if isinstance(data, bytes):
                await f.write(data)  # pyright: ignore
                size = len(data)
            elif isinstance(data, AsyncIterator):
                size = 0
                async for chunk in data:
                    await f.write(chunk)  # pyright: ignore
                    size += len(chunk)
            elif isinstance(data, (Iterator, Iterable)):  # Sync iterables
                size = 0
                for chunk in data:
                    await f.write(chunk)  # pyright: ignore
                    size += len(chunk)
            elif isinstance(data, IO):  # Sync IO
                size = 0
                while True:
                    chunk = await async_(data.read)(chunk_size)  # pyright: ignore
                    if not chunk:
                        break
                    await f.write(chunk)  # pyright: ignore
                    size += len(chunk)  # pyright: ignore
            elif isinstance(data, Path):
                if not data.is_file():
                    raise FileNotFoundError(data)
                size = data.stat().st_size
                try:
                    import aiofiles

                    async with aiofiles.open(data, mode="rb") as source_f:
                        while True:
                            chunk = await source_f.read(chunk_size)
                            if not chunk:
                                break
                            await f.write(chunk)  # pyright: ignore
                except ImportError:
                    with data.open("rb") as source_f:
                        while True:
                            chunk = await async_(source_f.read)(chunk_size)
                            if not chunk:
                                break
                            await f.write(chunk)  # pyright: ignore
            else:
                msg = f"Unsupported data type: {type(data)}"
                raise TypeError(msg)

        # Initialize file_object properties with defaults or calculated values
        file_object.size = size or 0
        file_object.last_modified = None
        file_object.etag = None
        original_metadata = file_object.metadata  # Keep original metadata unless backend provides updates

        info = await fs.info(path_str)  # pyright: ignore
        if isinstance(info, dict):
            # Update file_object with info from the backend if available and it's a dict
            file_object.size = cast("int", info.get("size", size))  # pyright: ignore
            file_object.last_modified = get_mtime_equivalent(info)  # pyright: ignore
            file_object.etag = info.get("etag")  # pyright: ignore
            # Merge backend metadata if available and different from original
            backend_meta = info.get("metadata", {})  # pyright: ignore
            if backend_meta and backend_meta != original_metadata:
                # Create a new metadata dict starting with original, then update with backend
                updated_metadata = original_metadata.copy() if original_metadata else {}
                updated_metadata.update(backend_meta)  # pyright: ignore
                file_object.metadata = updated_metadata

        return file_object

    def delete_object(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s).

        Args:
            paths: Path or sequence of paths to delete.
        """
        fs = cast("AbstractFileSystem", self.fs)
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        fs.rm(path_list, recursive=False)  # pyright: ignore

    async def delete_object_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s) asynchronously.

        Args:
            paths: Path or sequence of paths to delete.
        """
        if not self.is_async:
            return await async_(self.delete_object)(paths=paths)

        fs = cast("AsyncFileSystem", self.fs)
        path_list = (
            [self._to_path(paths)] if isinstance(paths, (str, Path, os.PathLike)) else [self._to_path(p) for p in paths]
        )
        await fs._rm(path_list, recursive=False)  # pyright: ignore
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
        fs = cast("AbstractFileSystem", self.fs)
        is_single = isinstance(paths, (str, Path, os.PathLike))
        path_list = [self._to_path(paths)] if is_single else [self._to_path(p) for p in paths]  # type: ignore
        if not hasattr(fs, "sign"):
            msg = f"Filesystem object {type(fs).__name__} does not have a 'sign' method."
            raise NotImplementedError(msg)
        signed_urls: list[str] = []
        try:
            # fsspec sign method might take expiration in seconds
            # Ensure this is a list comprehension, not a generator expression
            signed_urls.extend([fs.sign(path_str, expiration=expires_in) for path_str in path_list])  # pyright: ignore
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
        fs = cast("AsyncFileSystem", self.fs)
        is_single = isinstance(paths, (str, Path, os.PathLike))
        path_list = [self._to_path(paths)] if is_single else [self._to_path(p) for p in paths]  # type: ignore
        if not hasattr(fs, "sign"):
            msg = f"Async filesystem object {type(fs).__name__} does not have a 'sign' method."
            raise NotImplementedError(msg)
        signed_urls: list[str] = []
        try:
            signed_urls.extend([await fs.sign(path_str, expiration=expires_in) for path_str in path_list])  # pyright: ignore
        except NotImplementedError as e:
            msg = f"Async signing URLs not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e

        return signed_urls[0] if is_single else signed_urls  # pyright: ignore

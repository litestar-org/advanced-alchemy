# advanced_alchemy/types/file_object/backends/fsspec.py
# ruff: noqa: PLR0904, SLF001
"""FSSpec-backed storage backend for file objects."""

import asyncio
import os
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator, Sequence
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Optional, Union, cast

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.file_object.base import (
    AsyncDataLike,
    DataLike,
    FileObject,
    PathLike,
    StorageBackend,
)
from advanced_alchemy.utils.sync_tools import async_, await_

try:
    # Correct import for AsyncFileSystem and try importing async file handle
    from fsspec.asyn import AsyncFileSystem

    # Attempt to import a specific async file handle type if available
    # This might vary depending on fsspec version and installed backends
    try:
        from fsspec.asyn import AsyncBufferedReader  # Common type, adjust if needed
    except ImportError:
        AsyncBufferedReader = Any  # Fallback if specific type not found
except ImportError as e:
    raise MissingDependencyError("fsspec") from e


if TYPE_CHECKING:
    from fsspec import AbstractFileSystem

    # Keep AbstractBufferedFile for sync context


class FSSpecBackend(StorageBackend):
    """FSSpec-backed storage backend implementing both sync and async operations."""

    driver = "fsspec"  # Changed backend identifier to driver

    def __init__(self, fs: "Union[AbstractFileSystem, AsyncFileSystem]") -> None:
        """Initialize FSSpecBackend.

        Args:
            fs: The FSSpec filesystem instance (sync or async).
        """
        self.is_async = isinstance(fs, AsyncFileSystem)
        self.protocol = getattr(fs, "protocol", "file") if isinstance(fs.protocol, str) else "file"  # type: ignore[union-attr]

    def get_content(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options passed to fsspec's open.
        """
        options = options or {}
        path_str = self._to_path(path)
        fs = cast("AbstractFileSystem", self.fs)  # Cast for type checker
        with fs.open(path_str, "rb", **options) as f:
            # Ensure f is treated as a file handle supporting read
            f_handle = cast("IO[bytes]", f)
            return f_handle.read()

    async def get_content_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options passed to fsspec's open.

        Raises:
            TypeError: If the filesystem is not an AsyncFileSystem.
        """
        if not self.is_async:
            # Fallback for sync filesystems - Note: get_content is sync, wrapping with async_
            return await async_(self.get_content)(path=path, options=options)

        options = options or {}
        path_str = self._to_path(path)
        fs = cast("AsyncFileSystem", self.fs)
        # Use standard async context manager
        async with fs.open(path_str, mode="rb", **options) as f:
            # Explicitly cast to the imported or fallback async file handle type
            f_async = cast("AsyncBufferedReader", f)
            return await f_async.read()

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
            end: End byte index (exclusive). Either end or length should be provided.
            length: Number of bytes to retrieve (alternative to end).
        """
        if self.is_async:
            return await_(self.get_range_async)(path=path, start=start, end=end, length=length)
        path_str = self._to_path(path)
        actual_end = end
        if actual_end is None and length is not None:
            actual_end = start + length

        read_length = -1
        if actual_end is not None:
            read_length = actual_end - start

        fs = cast("AbstractFileSystem", self.fs)
        with fs.open(path_str, "rb") as f:
            f_handle = cast("IO[bytes]", f)
            f_handle.seek(start)
            return f_handle.read(read_length)

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
            end: End byte index (exclusive). Either end or length should be provided.
            length: Number of bytes to retrieve (alternative to end).
        """
        if not self.is_async:
            return await async_(self.get_range)(path=path, start=start, end=end, length=length)

        path_str = self._to_path(path)
        actual_end = end
        if actual_end is None and length is not None:
            actual_end = start + length

        read_length = -1
        if actual_end is not None:
            read_length = actual_end - start

        fs = cast("AsyncFileSystem", self.fs)
        async with fs._open(path_str, "rb") as f:
            f_async = cast("AsyncBufferedReader", f)
            await f_async.seek(start)
            return await f_async.read(read_length)

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
            ends: End byte indices (exclusive). Use ends or lengths.
            lengths: Number of bytes to retrieve for each range. Use ends or lengths.

        Raises:
            ValueError: If both or neither of ends/lengths are provided, or if counts mismatch.
        """
        if (ends is None and lengths is None) or (ends is not None and lengths is not None):
            msg = "Exactly one of 'ends' or 'lengths' must be provided."
            raise ValueError(msg)
        if ends is not None and len(starts) != len(ends):
            msg = "'starts' and 'ends' must have the same number of elements."
            raise ValueError(msg)
        if lengths is not None and len(starts) != len(lengths):
            msg = "'starts' and 'lengths' must have the same number of elements."
            raise ValueError(msg)

        path_str = self._to_path(path)
        result = []
        read_lengths = [end - start for start, end in zip(starts, ends)] if ends is not None else lengths

        fs = cast("AbstractFileSystem", self.fs)
        with fs.open(path_str, "rb") as f:
            f_handle = cast("IO[bytes]", f)
            for start, length in zip(starts, read_lengths):
                f_handle.seek(start)
                result.append(f_handle.read(length))

        return result

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
            ends: End byte indices (exclusive). Use ends or lengths.
            lengths: Number of bytes to retrieve for each range. Use ends or lengths.

        Raises:
            ValueError: If both or neither of ends/lengths are provided, or if counts mismatch.
        """
        if not self.is_async:
            # Fallback to sync version, wrapped
            return await async_(self.get_ranges)(path=path, starts=starts, ends=ends, lengths=lengths)

        if (ends is None and lengths is None) or (ends is not None and lengths is not None):
            msg = "Exactly one of 'ends' or 'lengths' must be provided."
            raise ValueError(msg)
        if ends is not None and len(starts) != len(ends):
            msg = "'starts' and 'ends' must have the same number of elements."
            raise ValueError(msg)
        if lengths is not None and len(starts) != len(lengths):
            msg = "'starts' and 'lengths' must have the same number of elements."
            raise ValueError(msg)

        path_str = self._to_path(path)
        result = []
        read_lengths = [end - start for start, end in zip(starts, ends)] if ends is not None else lengths

        fs = cast("AsyncFileSystem", self.fs)
        async with fs.open(path_str, "rb") as f:
            f_async = cast("AsyncBufferedReader", f)
            for start, length in zip(starts, read_lengths):
                await f_async.seek(start)
                result.append(await f_async.read(length))

        return result

    def put(
        self,
        path: PathLike,
        data: DataLike,
        *,
        content_type: Optional[str] = None,  # Often ignored by fsspec, depends on backend
        metadata: Optional[dict[str, Any]] = None,  # Often ignored by fsspec, depends on backend
        use_multipart: Optional[bool] = None,  # Ignored - fsspec handles internally
        chunk_size: int = 5 * 1024 * 1024,  # Used for IO/Path reading
        max_concurrency: int = 12,  # Ignored - fsspec handles internally
    ) -> FileObject:
        """Save data to the specified path.

        Args:
            path: Destination path
            data: The data to save (bytes, byte iterator, file-like object, Path)
            content_type: MIME type (often ignored by fsspec)
            metadata: Additional metadata (often ignored by fsspec)
            use_multipart: Ignored.
            chunk_size: Size of chunks when reading from IO/Path.
            max_concurrency: Ignored.

        Raises:
            TypeError: If the data type is unsupported.
            FileNotFoundError: If data is a Path and does not exist.

        Returns:
            FileInfo object representing the saved file.
        """
        path_str = self._to_path(path)
        fs = cast("AbstractFileSystem", self.fs)
        with fs.open(path_str, "wb") as f:
            if isinstance(data, bytes):
                f.write(data)
                size = len(data)
            elif isinstance(data, (Iterator, Iterable)):
                size = 0
                for chunk in data:
                    if not isinstance(chunk, bytes):
                        msg = f"Iterator/Iterable must yield bytes, got {type(chunk)}"
                        raise TypeError(msg)
                    f.write(chunk)
                    size += len(chunk)
            elif isinstance(data, IO):
                size = 0
                while True:
                    chunk = data.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    size += len(chunk)
            elif isinstance(data, Path):
                if not data.is_file():
                    raise FileNotFoundError(data)
                size = data.stat().st_size
                with data.open("rb") as source_f:
                    while True:
                        chunk = source_f.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
            else:
                msg = f"Unsupported data type: {type(data)}"
                raise TypeError(msg)

        # Try to get info after writing, but may not be reliable for all backends
        try:
            info = fs.info(path_str)
        except (FileNotFoundError, NotImplementedError):
            info = {}

        return FileObject(
            filename=os.path.basename(path_str),
            path=path_str,
            size=info.get("size", size),  # Use calculated size if info doesn't provide
            content_type=content_type or info.get("contentType"),
            last_modified=info.get("mtime"),  # Or other relevant time key
            etag=info.get("etag"),
            metadata=metadata or info.get("metadata", {}),  # Merge if possible
            backend=self,
            protocol=self.protocol,
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
    ) -> FileObject:
        """Save data to the specified path asynchronously.

        Args:
            path: Destination path
            data: The data to save (bytes, async byte iterator, file-like object, Path)
            content_type: MIME type (often ignored by fsspec)
            metadata: Additional metadata (often ignored by fsspec)
            use_multipart: Ignored.
            chunk_size: Size of chunks when reading from IO/Path/AsyncIterator.
            max_concurrency: Ignored.

        Raises:
            TypeError: If the filesystem is not async or data type is not supported.
            FileNotFoundError: If data is a Path and does not exist.

        Returns:
            FileInfo object representing the saved file.
        """
        if not self.is_async:
            # Fallback for sync filesystems. Handle async data carefully.
            if isinstance(data, (AsyncIterator, AsyncIterable)) and not isinstance(data, (bytes, str)):
                # Read async stream into memory for sync backend (potential memory issue)
                all_data = b"".join([chunk async for chunk in data])
                return await async_(self.put)(
                    path=path, data=all_data, content_type=content_type, metadata=metadata, chunk_size=chunk_size
                )
            # If data is sync-compatible
            return await async_(self.put)(
                path=path, data=data, content_type=content_type, metadata=metadata, chunk_size=chunk_size
            )

        fs = cast("AsyncFileSystem", self.fs)
        path_str = self._to_path(path)
        size: int = 0  # Initialize size

        async with fs.open(path_str, "wb") as f:
            f_async = cast("AsyncBufferedReader", f)
            if isinstance(data, bytes):
                await f_async.write(data)
                size = len(data)
            elif isinstance(data, AsyncIterator):
                size = 0
                async for chunk in data:
                    if not isinstance(chunk, bytes):
                        msg = f"AsyncIterator must yield bytes, got {type(chunk)}"
                        raise TypeError(msg)
                    await f_async.write(chunk)
                    size += len(chunk)
            elif isinstance(data, (Iterator, Iterable)):  # Sync iterables
                size = 0
                for chunk in data:
                    if not isinstance(chunk, bytes):
                        msg = f"Iterator/Iterable must yield bytes, got {type(chunk)}"
                        raise TypeError(msg)
                    await f_async.write(chunk)  # Write might block if fs.open doesn't handle sync data well
                    size += len(chunk)
            elif isinstance(data, IO):  # Sync IO
                size = 0
                # Run sync read in thread executor to avoid blocking event loop
                loop = asyncio.get_running_loop()
                while True:
                    chunk = await loop.run_in_executor(None, data.read, chunk_size)
                    if not chunk:
                        break
                    await f_async.write(chunk)
                    size += len(chunk)
            elif isinstance(data, Path):
                if not data.is_file():
                    raise FileNotFoundError(data)
                size = data.stat().st_size
                # Use aiofiles for async file reading if available, otherwise thread executor
                try:
                    import aiofiles

                    async with aiofiles.open(data, mode="rb") as source_f:
                        while True:
                            chunk = await source_f.read(chunk_size)
                            if not chunk:
                                break
                            await f_async.write(chunk)
                except ImportError:
                    # Fallback to thread executor for sync open/read
                    loop = asyncio.get_running_loop()
                    with data.open("rb") as source_f:
                        while True:
                            chunk = await loop.run_in_executor(None, source_f.read, chunk_size)
                            if not chunk:
                                break
                            await f_async.write(chunk)
            else:
                msg = f"Unsupported data type: {type(data)}"
                raise TypeError(msg)

        # Try to get info after writing
        try:
            info = await fs.info(path_str)
        except (FileNotFoundError, NotImplementedError):
            info = {}

        return FileObject(
            filename=os.path.basename(path_str),
            path=path_str,
            size=info.get("size", size),  # Use calculated size if info doesn't provide
            content_type=content_type or info.get("contentType"),
            last_modified=info.get("mtime"),
            etag=info.get("etag"),
            metadata=metadata or info.get("metadata", {}),
            backend=self,
            protocol=self.protocol,
        )

    def delete(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s).

        Args:
            paths: Path or sequence of paths to delete.
        """
        fs = cast("AbstractFileSystem", self.fs)
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        # Use fs.rm, which often handles lists. Fallback might be needed.
        try:
            fs.rm(path_list, recursive=False)  # recursive=False for files
        except FileNotFoundError:
            pass  # Ignore if any path is already deleted
        except NotImplementedError:
            # Fallback: delete one by one
            print(
                f"Warning: fs.rm not implemented or doesn't support lists for {self.protocol}. Deleting individually."
            )
            for path_str in path_list:
                try:
                    fs.rm(path_str, recursive=False)
                except FileNotFoundError:
                    pass
                except NotImplementedError as e:
                    print(f"Warning: fs.rm not implemented for {self.protocol}. Delete failed for {path_str}")
                    raise NotImplementedError from e  # Re-raise if single delete also fails

    async def delete_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the object(s) at the specified location(s) asynchronously.

        Args:
            paths: Path or sequence of paths to delete.

        Raises:
            TypeError: If the filesystem is not async.
        """
        if not self.is_async:
            return await async_(self.delete)(paths=paths)

        fs = cast("AsyncFileSystem", self.fs)
        if isinstance(paths, (str, Path, os.PathLike)):
            path_list = [self._to_path(paths)]
        else:
            path_list = [self._to_path(p) for p in paths]

        try:
            await fs.rm(path_list, recursive=False)
        except FileNotFoundError:
            pass
        except NotImplementedError:
            print(
                f"Warning: async fs.rm not implemented or doesn't support lists for {self.protocol}. Deleting individually."
            )
            for path_str in path_list:
                try:
                    await fs.rm(path_str, recursive=False)
                except FileNotFoundError:
                    pass
                except NotImplementedError as e:
                    print(
                        f"Warning: async fs.rm not implemented for {self.protocol}. Async delete failed for {path_str}"
                    )
                    raise NotImplementedError from e

    def copy(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another in the same storage backend.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite the destination if it exists. Note: fsspec's `cp` overwrite behavior might vary.

        Raises:
             NotImplementedError: If the backend doesn't support copy.
             FileExistsError: If destination exists and overwrite is False (behavior might vary).
        """
        from_str = self._to_path(from_)
        to_str = self._to_path(to)
        fs = cast("AbstractFileSystem", self.fs)

        if not overwrite and fs.exists(to_str):
            raise FileExistsError(f"Destination {to_str} exists and overwrite is False.")

        try:
            # recursive=False implies copying a single file
            # Use cp_file if available and more explicit, else cp
            if hasattr(fs, "cp_file"):
                fs.cp_file(from_str, to_str)
            else:
                fs.cp(from_str, to_str, recursive=False)
        except FileExistsError as e:  # Catch if fs.cp itself raises this despite our check
            if not overwrite:
                raise FileExistsError(f"Destination {to_str} exists and overwrite is False.") from e
            # If overwrite is True, ignore the error if backend raises it, maybe log warning
            print(f"Warning: Backend raised FileExistsError for {to_str} even with overwrite=True")
        except NotImplementedError as e:
            msg = f"Copy operation not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:  # Catch other potential errors during copy
            print(f"Error during sync copy from {from_str} to {to_str}: {e}")
            raise

    async def copy_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another in the same storage backend asynchronously.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite the destination if it exists.

        Raises:
            TypeError: If the filesystem is not async.
            NotImplementedError: If the backend doesn't support async copy.
            FileExistsError: If destination exists and overwrite is False.
        """
        if not self.is_async:
            return await async_(self.copy)(from_=from_, to=to, overwrite=overwrite)

        fs = cast("AsyncFileSystem", self.fs)
        from_str = self._to_path(from_)
        to_str = self._to_path(to)

        if not overwrite and await fs.exists(to_str):
            raise FileExistsError(f"Destination {to_str} exists and overwrite is False.")

        try:
            if hasattr(fs, "cp_file"):
                await fs.cp_file(from_str, to_str)
            else:
                await fs.cp(from_str, to_str, recursive=False)
        except FileExistsError as e:
            if not overwrite:
                raise FileExistsError(f"Destination {to_str} exists and overwrite is False.") from e
            print(f"Warning: Async backend raised FileExistsError for {to_str} even with overwrite=True")
        except NotImplementedError as e:
            msg = f"Async copy operation not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:  # Catch other potential errors
            print(f"Error during async copy from {from_str} to {to_str}: {e}")
            raise

    def rename(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Move an object from one path to another in the same storage backend.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite the destination if it exists. Note: fsspec's `mv` overwrite behavior might vary.

        Raises:
             NotImplementedError: If the backend doesn't support move/rename.
             FileExistsError: If destination exists and overwrite is False.
        """
        from_str = self._to_path(from_)
        to_str = self._to_path(to)
        fs = cast("AbstractFileSystem", self.fs)

        if not overwrite and fs.exists(to_str):
            raise FileExistsError(f"Destination {to_str} exists and overwrite is False.")

        try:
            # Use mv_file if available, else mv
            if hasattr(fs, "mv_file"):
                fs.mv_file(from_str, to_str)
            else:
                fs.mv(from_str, to_str, recursive=False)
        except FileExistsError as e:
            if not overwrite:
                raise FileExistsError(f"Destination {to_str} exists and overwrite is False.") from e
            print(f"Warning: Backend raised FileExistsError for {to_str} during rename even with overwrite=True")
        except NotImplementedError as e:
            msg = f"Rename/move operation not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:
            print(f"Error during sync rename from {from_str} to {to_str}: {e}")
            raise

    async def rename_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Move an object from one path to another in the same storage backend asynchronously.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite the destination if it exists.

        Raises:
            TypeError: If the filesystem is not async.
            NotImplementedError: If the backend doesn't support async move/rename.
            FileExistsError: If destination exists and overwrite is False.
        """
        if not self.is_async:
            return await async_(self.rename)(from_=from_, to=to, overwrite=overwrite)

        fs = cast("AsyncFileSystem", self.fs)
        from_str = self._to_path(from_)
        to_str = self._to_path(to)

        if not overwrite and await fs.exists(to_str):
            raise FileExistsError(f"Destination {to_str} exists and overwrite is False.")

        try:
            if hasattr(fs, "mv_file"):
                await fs.mv_file(from_str, to_str)
            else:
                await fs.mv(from_str, to_str, recursive=False)
        except FileExistsError as e:
            if not overwrite:
                raise FileExistsError(f"Destination {to_str} exists and overwrite is False.") from e
            print(f"Warning: Async backend raised FileExistsError for {to_str} during rename even with overwrite=True")
        except NotImplementedError as e:
            msg = f"Async rename/move operation not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:
            print(f"Error during async rename from {from_str} to {to_str}: {e}")
            raise

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
            ValueError: If input is invalid.
        """
        if for_upload:
            msg = "Generating signed URLs for upload is generally not supported by fsspec's generic sign method."
            raise NotImplementedError(msg)

        fs = cast("AbstractFileSystem", self.fs)
        is_single = isinstance(paths, (str, Path, os.PathLike))
        path_list = [self._to_path(paths)] if is_single else [self._to_path(p) for p in paths]

        signed_urls = []
        try:
            # Check if sign method exists before calling
            if not hasattr(fs, "sign"):
                msg = f"Filesystem object {type(fs).__name__} does not have a 'sign' method."
                raise NotImplementedError(msg)

            for path_str in path_list:
                # fsspec sign method might take expiration in seconds
                signed_url = fs.sign(path_str, expiration=expires_in)
                signed_urls.append(signed_url)
        except NotImplementedError as e:
            # This might be raised by the sign method itself if not implemented for the protocol
            msg = f"Signing URLs not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:
            print(f"Error during sync signing for paths {path_list}: {e}")
            raise

        return signed_urls[0] if is_single else signed_urls

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
            TypeError: If the filesystem is not async.
            NotImplementedError: If the backend doesn't support async signing or if `for_upload=True`.
            ValueError: If input is invalid.
        """
        if not self.is_async:
            return await async_(self.sign)(paths=paths, expires_in=expires_in, for_upload=for_upload)

        if for_upload:
            msg = "Generating signed URLs for upload is generally not supported by fsspec's generic sign method."
            raise NotImplementedError(msg)

        fs = cast("AsyncFileSystem", self.fs)
        is_single = isinstance(paths, (str, Path, os.PathLike))
        path_list = [self._to_path(paths)] if is_single else [self._to_path(p) for p in paths]

        signed_urls = []
        try:
            if not hasattr(fs, "sign"):
                msg = f"Async filesystem object {type(fs).__name__} does not have a 'sign' method."
                raise NotImplementedError(msg)

            for path_str in path_list:
                signed_url = await fs.sign(path_str, expiration=expires_in)
                signed_urls.append(signed_url)
        except NotImplementedError as e:
            msg = f"Async signing URLs not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:
            print(f"Error during async signing for paths {path_list}: {e}")
            raise

        return signed_urls[0] if is_single else signed_urls

    async def list_async(
        self,
        prefix: Optional[str] = None,
        *,
        delimiter: Optional[str] = None,  # Often handled by detail=True in fsspec ls
        offset: Optional[str] = None,  # fsspec ls doesn't directly support offset token
        limit: int = -1,  # fsspec ls doesn't directly support limit
    ) -> list[FileObject]:
        """List objects asynchronously.

        Note: fsspec `ls` has limitations:
            - `delimiter` for hierarchical listing is often achieved by listing with `detail=True`
              and then filtering/processing the results, not a direct API parameter.
            - `offset` (continuation token) is not generally supported.
            - `limit` is not generally supported; filtering happens after retrieving all results.

        Args:
            prefix: List objects starting with this prefix.
            delimiter: If provided, treat as a directory separator (behavior simulated).
            offset: Ignored.
            limit: If > 0, limit the number of results *after* retrieving all matches (inefficient).

        Returns:
            List of FileInfo objects representing files/directories.
        """
        if not self.is_async:
            return await async_(self.list)(prefix=prefix, delimiter=delimiter, offset=offset, limit=limit)

        fs = cast("AsyncFileSystem", self.fs)
        prefix = prefix or ""

        try:
            # Use detail=True to get metadata needed for FileObject
            # FSSpec's ls might return directories as well, depending on backend
            raw_listing = await fs.ls(prefix, detail=True)
        except FileNotFoundError:
            return []  # Prefix doesn't exist
        except NotImplementedError as e:
            msg = f"Async list operation not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:
            print(f"Error during async list for prefix '{prefix}': {e}")
            raise

        file_objects = []
        common_prefixes = set()  # To handle delimiter simulation

        for item_info in raw_listing:
            # item_info format can vary, typically a dict with 'name', 'size', 'type'
            item_path = item_info.get("name")
            if not item_path:
                continue  # Skip entries without a name/path

            # Simulate delimiter behavior
            if delimiter:
                relative_path = item_path[len(prefix) :].lstrip("/")
                if delimiter in relative_path:
                    # It's nested deeper than the delimiter allows, capture the common prefix
                    common_prefix = prefix + relative_path.split(delimiter, 1)[0] + delimiter
                    common_prefixes.add(common_prefix)
                    continue  # Skip this detailed item, we'll add the prefix later

            item_type = item_info.get("type")
            # We primarily want files, but might include directories if not using delimiter
            if item_type == "directory" and delimiter:  # Skip directories explicitly if using delimiter
                continue

            # Construct FileObject
            file_obj = FileObject(
                filename=os.path.basename(item_path),
                path=item_path,
                size=item_info.get("size", 0),
                content_type=item_info.get("contentType"),  # May not be available
                last_modified=item_info.get("mtime"),  # Or other time keys
                etag=item_info.get("etag"),
                metadata=item_info,  # Store the raw info as metadata for now
                backend=self,
                protocol=self.protocol,
            )
            file_objects.append(file_obj)

        # Add common prefixes if using delimiter
        if delimiter:
            for common_prefix_path in sorted(list(common_prefixes)):
                # Represent prefixes as FileObjects with size 0 and specific content type? Or filter them out?
                # For now, let's add them as directory-like entries.
                file_objects.append(
                    FileObject(
                        filename=os.path.basename(common_prefix_path.rstrip(delimiter)),
                        path=common_prefix_path,
                        size=0,
                        content_type="application/x-directory",  # Indicate it's a common prefix
                        backend=self,
                        protocol=self.protocol,
                    )
                )

        # Apply limit *after* getting all results (inefficient but fsspec limitation)
        if 0 < limit < len(file_objects):  # Corrected limit application
            file_objects = file_objects[:limit]

        return file_objects

    def list(
        self,
        prefix: Optional[str] = None,
        *,
        delimiter: Optional[str] = None,
        offset: Optional[str] = None,
        limit: int = -1,
    ) -> list[FileObject]:
        """List objects synchronously.

        See notes in the asynchronous `list_async` method regarding limitations.

        Args:
            prefix: List objects starting with this prefix.
            delimiter: If provided, treat as a directory separator.
            offset: Ignored.
            limit: If > 0, limit the number of results after retrieval.

        Returns:
            List of FileInfo objects.
        """
        prefix = prefix or ""
        fs = cast("AbstractFileSystem", self.fs)

        try:
            raw_listing = fs.ls(prefix, detail=True)
        except FileNotFoundError:
            return []
        except NotImplementedError as e:
            msg = f"List operation not supported by {self.protocol} backend."
            raise NotImplementedError(msg) from e
        except Exception as e:
            print(f"Error during sync list for prefix '{prefix}': {e}")
            raise

        file_objects = []
        common_prefixes = set()

        for item_info in raw_listing:
            item_path = item_info.get("name")
            if not item_path:
                continue

            if delimiter:
                relative_path = item_path[len(prefix) :].lstrip("/")
                if delimiter in relative_path:
                    common_prefix = prefix + relative_path.split(delimiter, 1)[0] + delimiter
                    common_prefixes.add(common_prefix)
                    continue

            item_type = item_info.get("type")
            if item_type == "directory" and delimiter:
                continue

            file_obj = FileObject(
                filename=os.path.basename(item_path),
                path=item_path,
                size=item_info.get("size", 0),
                content_type=item_info.get("contentType"),
                last_modified=item_info.get("mtime"),
                etag=item_info.get("etag"),
                metadata=item_info,
                backend=self,
                protocol=self.protocol,
            )
            file_objects.append(file_obj)

        if delimiter:
            for common_prefix_path in sorted(list(common_prefixes)):
                file_objects.append(
                    FileObject(
                        filename=os.path.basename(common_prefix_path.rstrip(delimiter)),
                        path=common_prefix_path,
                        size=0,
                        content_type="application/x-directory",
                        backend=self,
                        protocol=self.protocol,
                    )
                )

        if 0 < limit < len(file_objects):  # Corrected limit application
            file_objects = file_objects[:limit]

        return file_objects

# advanced_alchemy/types/file_object/backends/fsspec.py
# ruff: noqa: PLR0904
"""FSSpec-backed storage backend for file objects."""

import os
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator, Sequence
from pathlib import Path
from typing import IO, Any, Optional, Union, cast

from fsspec import AbstractFileSystem
from fsspec.asyn import AsyncFileSystem
from typing_extensions import Self

from advanced_alchemy.types.file_object.base import (
    AsyncDataLike,
    DataLike,
    FileInfo,
    PathLike,
    StorageBackend,
)


class FSSpecBackend(StorageBackend):
    """FSSpec-backed storage backend implementing both sync and async operations."""

    backend = "fsspec"  # Added backend identifier

    def __init__(self, fs: "Union[AbstractFileSystem, AsyncFileSystem]") -> None:
        """Initialize FSSpecBackend.

        Args:
            fs: The FSSpec filesystem instance (sync or async).
        """
        super().__init__(fs=fs)  # Pass fs to parent constructor
        # self.fs is already set by super().__init__
        self.is_async = isinstance(fs, AsyncFileSystem)
        # Determine protocol - use getattr for safety as 'protocol' isn't guaranteed
        self.protocol = getattr(fs, "protocol", "file") if isinstance(fs.protocol, str) else "file"  # type: ignore[union-attr]

    def get(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options passed to fsspec's open.
        """
        options = options or {}
        path_str = self._to_path(path)
        with self.fs.open(path_str, "rb", **options) as f:
            return f.read()

    async def get_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        """Return the bytes stored at the specified location asynchronously.

        Args:
            path: Path to retrieve
            options: Optional backend-specific options passed to fsspec's open.
        """
        if not self.is_async:
            # Fallback for sync filesystems
            return self.get(path, options=options)

        options = options or {}
        path_str = self._to_path(path)
        if not isinstance(self.fs, AsyncFileSystem):
            raise TypeError("fs must be an AsyncFileSystem")
        async with self.fs.open_async(path_str, mode="rb", **options) as f:
            return await f.read()

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
        path_str = self._to_path(path)
        actual_end = end
        if actual_end is None and length is not None:
            actual_end = start + length
        elif actual_end is not None and length is not None:
            # Prefer 'end' if both are given, or raise error? fsspec usually takes 'end'.
            pass

        # fsspec's read method takes length, not end offset.
        read_length = -1  # Read all from start if end/length not specified
        if actual_end is not None:
            read_length = actual_end - start

        with self.fs.open(path_str, "rb") as f:
            f.seek(start)
            return f.read(read_length)

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
            return self.get_range(path, start=start, end=end, length=length)

        path_str = self._to_path(path)
        actual_end = end
        if actual_end is None and length is not None:
            actual_end = start + length
        elif actual_end is not None and length is not None:
            pass  # Prefer 'end'

        read_length = -1
        if actual_end is not None:
            read_length = actual_end - start

        fs = cast("AsyncFileSystem", self.fs)
        async with fs.open(path_str, "rb") as f:
            await f.seek(start)
            return await f.read(read_length)

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
        read_lengths: Sequence[int]

        if ends is not None:
            read_lengths = [end - start for start, end in zip(starts, ends)]
        else:  # lengths must not be None here due to initial check
            read_lengths = lengths  # type: ignore[assignment]

        with self.fs.open(path_str, "rb") as f:
            for start, length in zip(starts, read_lengths):
                f.seek(start)
                result.append(f.read(length))

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
            return self.get_ranges(path, starts=starts, ends=ends, lengths=lengths)

        if (ends is None and lengths is None) or (ends is not None and lengths is not None):
            raise ValueError("Exactly one of 'ends' or 'lengths' must be provided.")
        if ends is not None and len(starts) != len(ends):
            raise ValueError("'starts' and 'ends' must have the same number of elements.")
        if lengths is not None and len(starts) != len(lengths):
            raise ValueError("'starts' and 'lengths' must have the same number of elements.")

        path_str = self._to_path(path)
        result = []
        read_lengths: Sequence[int]

        if ends is not None:
            read_lengths = [end - start for start, end in zip(starts, ends)]
        else:  # lengths must not be None here
            read_lengths = lengths  # type: ignore[assignment]

        fs = cast("AsyncFileSystem", self.fs)
        async with fs.open(path_str, "rb") as f:
            for start, length in zip(starts, read_lengths):
                await f.seek(start)
                result.append(await f.read(length))

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
    ) -> FileInfo[Self]:
        """Save data to the specified path.

        Args:
            path: Destination path
            data: The data to save (bytes, byte iterator, file-like object, Path)
            content_type: MIME type (often ignored by fsspec)
            metadata: Additional metadata (often ignored by fsspec)
            use_multipart: Ignored.
            chunk_size: Size of chunks when reading from IO/Path.
            max_concurrency: Ignored.

        Returns:
            A FileInfo object representing the saved file.
        """
        path_str = self._to_path(path)
        mode = "wb"  # Always write bytes

        # fsspec's open generally handles bytes/iterables directly
        if isinstance(data, (bytes, bytearray, Iterator, Iterable)) and not isinstance(data, str):
            with self.fs.open(path_str, mode) as f:
                if isinstance(data, (bytes, bytearray)):
                    f.write(data)
                else:  # Iterator/Iterable
                    for chunk in data:
                        f.write(chunk)
        elif isinstance(data, IO):  # File-like object
            with self.fs.open(path_str, mode) as f:
                while True:
                    chunk = data.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
        elif isinstance(data, Path):  # Local file path
            with open(data, "rb") as src, self.fs.open(path_str, mode) as dst:
                while True:
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break
                    dst.write(chunk)
        else:
            raise TypeError(f"Unsupported data type for put: {type(data)}")

        # Get file stats - use fs.info for consistency
        info = self.fs.info(path_str)
        size = info.get("size", -1)  # Use -1 to indicate potentially unknown size
        # Try to get a reliable modification time
        last_modified_raw = info.get("mtime", info.get("last_modified", info.get("updated_at")))
        last_modified = float(last_modified_raw) if last_modified_raw is not None else None

        return FileInfo(
            protocol=self.protocol,
            name=path_str,  # Use the full path as name for fsspec
            size=size,
            last_modified=last_modified,
            content_type=content_type,  # Pass through, might be None
            metadata=metadata,  # Pass through, might be None
            backend=self,
            # Checksum/ETag/VersionID are usually backend-specific, try to get if available
            checksum=info.get("checksum", info.get("md5", info.get("ETag", None))),  # Best effort
            etag=info.get("ETag", info.get("etag", None)),
            version_id=info.get("version_id", info.get("versionId", None)),
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
            data: The data to save (bytes, async byte iterator, file-like, Path)
            content_type: MIME type (often ignored by fsspec)
            metadata: Additional metadata (often ignored by fsspec)
            use_multipart: Ignored.
            chunk_size: Size of chunks when reading from IO/Path.
            max_concurrency: Ignored.


        Returns:
            A FileInfo object representing the saved file.
        """
        if not self.is_async:
            # Fallback for sync filesystems, but need to handle async data carefully
            # This might involve reading async stream into memory, which isn't ideal.
            # A better approach might be needed depending on expected usage with sync fs.
            if isinstance(data, (AsyncIterator, AsyncIterable)) and not isinstance(data, (bytes, bytearray, str)):
                # Example: Read async iterable into memory for sync backend
                all_data = b"".join([chunk async for chunk in data])
                return self.put(path, all_data, content_type=content_type, metadata=metadata, chunk_size=chunk_size)
            # If data is already sync-compatible (bytes, sync iter, IO, Path)
            return self.put(path, data, content_type=content_type, metadata=metadata, chunk_size=chunk_size)  # type: ignore

        path_str = self._to_path(path)
        fs = cast("AsyncFileSystem", self.fs)
        mode = "wb"

        if isinstance(data, (bytes, bytearray)):
            async with fs.open(path_str, mode) as f:
                await f.write(data)
        elif isinstance(data, (AsyncIterator, AsyncIterable)) and not isinstance(data, (str, bytes, bytearray)):
            async with fs.open(path_str, mode) as f:
                async for chunk in data:
                    await f.write(chunk)
        elif isinstance(data, (Iterator, Iterable)) and not isinstance(data, (str, bytes, bytearray)):
            # Handle sync iterables with async backend
            async with fs.open(path_str, mode) as f:
                for chunk in data:  # Iterate synchronously
                    await f.write(chunk)  # Write asynchronously
        elif isinstance(data, IO):  # Sync file-like object
            async with fs.open(path_str, mode) as f:
                while True:
                    chunk = data.read(chunk_size)  # Read synchronously
                    if not chunk:
                        break
                    await f.write(chunk)  # Write asynchronously
        elif isinstance(data, Path):  # Local file path
            with open(data, "rb") as src:  # Read sync
                async with fs.open(path_str, mode) as dst:  # Write async
                    while True:
                        chunk = src.read(chunk_size)
                        if not chunk:
                            break
                        await dst.write(chunk)
        else:
            raise TypeError(f"Unsupported data type for put_async: {type(data)}")

        # Get file stats - use fs.info for consistency
        info = await fs.info(path_str)
        size = info.get("size", -1)
        last_modified_raw = info.get("mtime", info.get("last_modified", info.get("updated_at")))
        last_modified = float(last_modified_raw) if last_modified_raw is not None else None

        return FileInfo(
            protocol=self.protocol,
            name=path_str,
            size=size,
            last_modified=last_modified,
            content_type=content_type,
            metadata=metadata,
            backend=self,
            checksum=info.get("checksum", info.get("md5", info.get("ETag", None))),
            etag=info.get("ETag", info.get("etag", None)),
            version_id=info.get("version_id", info.get("versionId", None)),
        )

    def delete(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the specified paths.

        Args:
            paths: Path or sequence of paths to delete.
        """
        if isinstance(paths, (str, Path, os.PathLike)):
            paths = [paths]  # Ensure it's a list

        paths_str = [self._to_path(p) for p in paths]
        # Use fs.rm which can often handle lists efficiently
        self.fs.rm(paths_str, recursive=False)  # Assuming non-recursive delete for files

    async def delete_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        """Delete the specified paths asynchronously.

        Args:
            paths: Path or sequence of paths to delete.
        """
        if not self.is_async:
            self.delete(paths)
            return

        if isinstance(paths, (str, Path, os.PathLike)):
            paths = [paths]

        paths_str = [self._to_path(p) for p in paths]
        fs = cast("AsyncFileSystem", self.fs)
        # Use fs.rm which can often handle lists efficiently
        await fs.rm(paths_str, recursive=False)  # Assuming non-recursive delete for files

    def copy(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite if 'to' exists. fsspec cp usually overwrites by default.
        """
        from_str = self._to_path(from_)
        to_str = self._to_path(to)

        # fsspec's cp might handle overwrite logic differently depending on backend.
        # Explicit check adds safety for backends where it doesn't overwrite.
        if not overwrite and self.fs.exists(to_str):
            msg = f"Destination {to_str} already exists and overwrite=False"
            raise FileExistsError(msg)

        # Rely on fsspec's copy implementation
        self.fs.cp_file(from_str, to_str)  # Use cp_file for clarity if copying single file

    async def copy_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Copy an object from one path to another asynchronously.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite if 'to' exists.
        """
        if not self.is_async:
            self.copy(from_, to, overwrite=overwrite)
            return

        from_str = self._to_path(from_)
        to_str = self._to_path(to)
        fs = cast("AsyncFileSystem", self.fs)

        if not overwrite and await fs.exists(to_str):
            msg = f"Destination {to_str} already exists and overwrite=False"
            raise FileExistsError(msg)

        await fs.cp_file(from_str, to_str)

    def rename(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename/move an object from one path to another.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite if 'to' exists. fsspec mv often overwrites.
        """
        from_str = self._to_path(from_)
        to_str = self._to_path(to)

        # Explicit check for safety, though mv might handle it
        if not overwrite and self.fs.exists(to_str):
            msg = f"Destination {to_str} already exists and overwrite=False"
            raise FileExistsError(msg)

        # Rely on fsspec's move implementation
        self.fs.mv(from_str, to_str)

    async def rename_async(self, from_: PathLike, to: PathLike, *, overwrite: bool = True) -> None:
        """Rename/move an object from one path to another asynchronously.

        Args:
            from_: Source path.
            to: Destination path.
            overwrite: Whether to overwrite if 'to' exists.
        """
        if not self.is_async:
            self.rename(from_, to, overwrite=overwrite)
            return

        from_str = self._to_path(from_)
        to_str = self._to_path(to)
        fs = cast("AsyncFileSystem", self.fs)

        if not overwrite and await fs.exists(to_str):
            msg = f"Destination {to_str} already exists and overwrite=False"
            raise FileExistsError(msg)

        await fs.mv(from_str, to_str)

    def sign(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,  # Often not directly supported by generic fsspec sign
    ) -> Union[str, list[str]]:
        """Generate signed URLs for the specified paths (if supported by backend).

        Args:
            paths: Path or sequence of paths to sign.
            expires_in: Expiration time in seconds.
            for_upload: If the URL is for uploading (less common for generic fsspec sign).

        Returns:
            Signed URL string or list of strings.

        Raises:
            NotImplementedError: If the underlying fsspec filesystem doesn't support signing.
        """
        if not hasattr(self.fs, "sign"):
            raise NotImplementedError(f"The filesystem '{self.protocol}' does not support signing URLs.")

        if isinstance(paths, (str, Path, os.PathLike)):
            return self.fs.sign(self._to_path(paths), expiration=expires_in)  # type: ignore[no-any-return]

        # If fs.sign takes a list, use it, otherwise loop
        try:
            # Attempt to pass the list directly if supported (more efficient)
            return self.fs.sign([self._to_path(p) for p in paths], expiration=expires_in)  # type: ignore[no-any-return]
        except TypeError:
            # Fallback to signing one by one
            return [self.fs.sign(self._to_path(path), expiration=expires_in) for path in paths]  # type: ignore[no-any-return]

    async def sign_async(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        """Generate signed URLs asynchronously (if supported by backend).

        Args:
            paths: Path or sequence of paths to sign.
            expires_in: Expiration time in seconds.
            for_upload: If the URL is for uploading.

        Returns:
            Signed URL string or list of strings.

        Raises:
            NotImplementedError: If the underlying fsspec filesystem doesn't support async signing.
        """
        if not self.is_async:
            # Fallback for sync filesystems that support signing
            return self.sign(paths, expires_in=expires_in, for_upload=for_upload)

        fs = cast("AsyncFileSystem", self.fs)
        if not hasattr(fs, "sign"):
            msg = f"The filesystem '{self.protocol}' does not support async signing URLs."
            raise NotImplementedError(msg)

        if isinstance(paths, (str, Path, os.PathLike)):
            # Assuming async sign method exists if fs is AsyncFileSystem and has 'sign'
            return await fs.sign(self._to_path(paths), expiration=expires_in)  # type: ignore[no-any-return,attr-defined]

        # If fs.sign takes a list, use it, otherwise loop (less likely for async?)
        try:
            return await fs.sign([self._to_path(p) for p in paths], expiration=expires_in)  # type: ignore[no-any-return,attr-defined]
        except TypeError:
            # Async fallback - potentially less efficient
            results = []
            for path in paths:
                results.append(await fs.sign(self._to_path(path), expiration=expires_in))  # type: ignore[attr-defined]
            return results

    async def list_async(
        self,
        prefix: Optional[str] = None,
        *,
        delimiter: Optional[str] = None,  # Often handled by detail=True in fsspec ls
        offset: Optional[str] = None,  # fsspec ls doesn't directly support offset token
        limit: int = -1,  # fsspec ls doesn't directly support limit
    ) -> list[FileInfo[Self]]:
        """List objects asynchronously.

        Note: fsspec `ls` doesn't directly support `offset` or `limit` like some cloud APIs.
              This implementation performs basic filtering after retrieving results.
              For large listings, consider backend-specific pagination if available through fsspec options.
              The `delimiter` functionality is often implicitly handled by requesting details.

        Args:
            prefix: Path prefix to filter by.
            delimiter: Ignored (fsspec often uses directory structure implicitly).
            offset: Filter results lexically greater than this value (basic post-filtering).
            limit: Maximum number of results to return (post-filtering).

        Returns:
            List of FileInfo objects.
        """
        if not self.is_async:
            return self.list(prefix=prefix, delimiter=delimiter, offset=offset, limit=limit)

        fs = cast("AsyncFileSystem", self.fs)
        # Use detail=True to get size, mtime etc. efficiently if backend supports it
        try:
            listing = await fs.ls(prefix or "", detail=True)
        except TypeError:  # Some backends might not support detail=True in ls
            listing_paths = await fs.ls(prefix or "")
            # Manually get info for each path - less efficient
            listing = []
            for p in listing_paths:
                try:
                    info_dict = await fs.info(p)
                    listing.append(info_dict)
                except FileNotFoundError:  # Handle potential race conditions or inconsistencies
                    continue

        result = []
        count = 0
        # Sort listing by name to enable consistent offset filtering
        sorted_listing = sorted(listing, key=lambda x: x.get("name", ""))

        for info in sorted_listing:
            name = info.get("name", "")
            file_type = info.get("type", "file")  # fsspec uses 'type'

            # Basic offset filtering
            if offset and name <= offset:
                continue

            # Stop if limit reached (and limit is positive)
            if limit > 0 and count >= limit:
                break

            # Skip directories if a delimiter-like behavior is desired implicitly
            if file_type == "directory":
                continue

            size = info.get("size", -1)
            last_modified_raw = info.get("mtime", info.get("last_modified", info.get("updated_at")))
            last_modified = float(last_modified_raw) if last_modified_raw is not None else None

            result.append(
                FileInfo(
                    protocol=self.protocol,
                    name=name,  # fsspec ls with detail=True provides the full path
                    size=size,
                    last_modified=last_modified,
                    content_type=info.get("content_type", info.get("ContentType")),  # Try common variations
                    metadata=info.get("metadata"),  # May or may not be populated
                    backend=self,
                    checksum=info.get("checksum", info.get("md5", info.get("ETag", None))),
                    etag=info.get("ETag", info.get("etag", None)),
                    version_id=info.get("version_id", info.get("versionId", None)),
                )
            )
            count += 1

        return result

    def list(
        self,
        prefix: Optional[str] = None,
        *,
        delimiter: Optional[str] = None,
        offset: Optional[str] = None,
        limit: int = -1,
    ) -> list[FileInfo[Self]]:
        """List objects synchronously.

        Args:
            prefix: Path prefix to filter by.
            delimiter: Ignored.
            offset: Filter results lexically greater than this value.
            limit: Maximum number of results.

        Returns:
            List of FileInfo objects.
        """
        # Use detail=True for efficiency if supported
        try:
            listing = self.fs.ls(prefix or "", detail=True)
        except TypeError:  # Fallback if detail=True not supported
            listing_paths = self.fs.ls(prefix or "")
            listing = [self.fs.info(p) for p in listing_paths if self.fs.exists(p)]  # Check exists for safety

        result = []
        count = 0
        # Sort listing by name for consistent offset filtering
        sorted_listing = sorted(listing, key=lambda x: x.get("name", ""))

        for info in sorted_listing:
            name = info.get("name", "")
            file_type = info.get("type", "file")

            if offset and name <= offset:
                continue

            if limit > 0 and count >= limit:
                break

            if file_type == "directory":
                continue

            size = info.get("size", -1)
            last_modified_raw = info.get("mtime", info.get("last_modified", info.get("updated_at")))
            last_modified = float(last_modified_raw) if last_modified_raw is not None else None

            result.append(
                FileInfo(
                    protocol=self.protocol,
                    name=name,
                    size=size,
                    last_modified=last_modified,
                    content_type=info.get("content_type", info.get("ContentType")),
                    metadata=info.get("metadata"),
                    backend=self,
                    checksum=info.get("checksum", info.get("md5", info.get("ETag", None))),
                    etag=info.get("ETag", info.get("etag", None)),
                    version_id=info.get("version_id", info.get("versionId", None)),
                )
            )
            count += 1

        return result

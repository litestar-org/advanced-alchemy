import asyncio
import io
from typing import Any, Dict, Optional, TracebackType, cast

from fsspec import AbstractFileSystem

# Re-use the StorageObjectProtocol definition from above
# (or import it if defined in a separate file)
# ... [StorageObjectProtocol definition] ...


class StoredFile(io.IOBase):
    """Represents a file stored using fsspec.

    This class provides a file-like interface for reading stored files.
    It supports both synchronous and asynchronous operations through
    the underlying fsspec filesystem.

    Attributes:
        fs: The fsspec filesystem instance
        path: Path to the file in the filesystem
        metadata: Optional metadata associated with the file
    """

    def __init__(self, fs: AbstractFileSystem, path: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.fs = fs
        self.path = path
        self._metadata = metadata or {}
        self._file: Optional[io.BufferedRandom] = None

    @property
    def name(self) -> str:
        """Get the file name from the path."""
        return self.path.split("/")[-1]

    @property
    def filename(self) -> str:
        """Get the original filename from metadata or fallback to path name."""
        return self._metadata.get("filename", self.name)

    @property
    def content_type(self) -> str:
        """Get the content type from metadata or fallback to octet-stream."""
        return self._metadata.get("content_type", "application/octet-stream")

    @property
    def metadata(self) -> dict[str, Any]:
        """Get the file metadata."""
        return self._metadata

    def get_file(self) -> io.BufferedRandom:
        """Get or create the file object for reading.

        Returns:
            The file object.
        """
        if self._file is None or self._file.closed:
            self._file = cast("io.BufferedRandom", self.fs.open(self.path, "rb"))
        return self._file

    def read(self, size: int = -1) -> bytes:
        """Read content from the file.

        Args:
            size: Number of bytes to read. -1 means read all (default).

        Returns:
            The read content as bytes.
        """
        f = self.get_file()
        return f.read(size)

    def readinto(self, b: bytearray) -> int:
        """Read bytes into a pre-allocated bytes-like object b.

        Returns:
            Number of bytes read.
        """
        f = self.get_file()
        return f.readinto(b)

    def close(self) -> None:
        """Close the file if open."""
        if self._file is not None and not self._file.closed:
            self._file.close()

    def seekable(self) -> bool:
        """Check if the file supports seeking."""
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        """Change stream position.

        Args:
            offset: Offset from whence
            whence: Reference point (0=start, 1=current, 2=end)

        Returns:
            The new absolute position.
        """
        f = self.get_file()
        return f.seek(offset, whence)

    def tell(self) -> int:
        """Return current stream position."""
        f = self.get_file()
        return f.tell()

    def writable(self) -> bool:  # noqa: PLR6301
        """Check if the file is writable.

        Returns:
            False, as this class is read-only.
        """
        return False

    def readable(self) -> bool:  # noqa: PLR6301
        """Check if the file is readable.

        Returns:
            True, as this class is read-only.
        """
        return True

    def __enter__(self) -> "StoredFile":
        """Context manager entry.

        Returns:
            self, as this class is read-only.
        """
        return self

    def __exit__(
        self,
        exc_type: "Optional[type[BaseException]]",
        exc_val: "Optional[BaseException]",
        exc_tb: "Optional[TracebackType]",
    ) -> None:
        """Context manager exit."""
        self.close()

    def __del__(self) -> None:
        """Ensure file is closed on deletion."""
        self.close()


class AsyncStoredFile(StoredFile):
    """
    Represents a file stored in a backend, providing an async-first,
    file-like interface conforming to io.IOBase.

    This class interacts with a backend storage object via the
    StorageObjectProtocol. It supports both asynchronous (`aread`, `aclose`)
    and synchronous (`read`, `close`) operations.

    Note:
        Using synchronous methods (`read`, `seek`, `tell`, `close`) within an
        asynchronous event loop might block the loop depending on the backend
        implementation and how async operations are run synchronously.
        Prefer async methods (`aread`, `aseek`, `atell`, `aclose`) in async code.

    Attributes:
        name (str): The identifier/name from the backend object.
        filename (str): The original filename, extracted from metadata.
                        Defaults to 'unnamed'.
        content_type (str): The content type, extracted from metadata.
                            Defaults to 'application/octet-stream'.
        size (int): The total size of the file in bytes.
    """

    def __init__(self, fs: StorageObjectProtocol) -> None:
        """
        Initializes the AsyncStoredFile.

        Args:
            backend_object: An object conforming to the StorageObjectProtocol.

        Raises:
            TypeError: If backend_object does not conform to the protocol.
            asyncio.TimeoutError: If fetching initial metadata times out.
            Exception: Propagated from backend_object's get_metadata call.
        """
        if not isinstance(fs, AbstractFileSystem):
            raise TypeError("fs must be an AbstractFileSystem")

        self.fs = fs
        self._pos: int = 0
        self._closed: bool = False
        self._metadata: Dict[str, Any] = {}
        self._loop = asyncio.get_event_loop()  # Get loop at init time

        # Fetch essential info synchronously during init (might block briefly)
        # Consider making init async if metadata fetch is very slow
        try:
            # Run async metadata fetch in a way compatible with sync/async init
            if self._loop.is_running():
                # If called from within an async context, avoid run_until_complete
                # This part is tricky and might need adjustment based on usage pattern.
                # A common pattern is an async factory function instead of sync init.
                # For simplicity here, we assume init might block if run async.
                # A dedicated async_init method is often cleaner.
                # Let's try running in executor if loop is running.
                # Note: This still might not be ideal. An async factory is better.
                future = asyncio.run_coroutine_threadsafe(self._backend_obj.get_metadata(), self._loop)
                self._metadata = future.result(timeout=10)  # Add reasonable timeout
            else:
                self._metadata = self._loop.run_until_complete(self._backend_obj.get_metadata())
        except Exception as e:
            # Clean up potentially created backend object if init fails?
            # Depends on backend_object's lifecycle management.
            print(f"Error fetching metadata during init: {e}")
            # We might need size even if metadata fails, let's try to get it
            # but essential properties might be missing below.
            # Or re-raise? Let's re-raise for clearer failure.
            raise RuntimeError(f"Failed to initialize AsyncStoredFile: {e}") from e

        self.name = self._backend_obj.name
        self.size = self._backend_obj.size
        self.filename = self._metadata.get("filename", "unnamed")
        self.content_type = self._metadata.get("content_type", "application/octet-stream")

    # --- Async Methods (Preferred) ---

    async def read_async(self, n: int = -1) -> bytes:
        """
        Asynchronously reads up to n bytes from the current position.

        If n is negative or omitted, reads until EOF.

        Returns:
            Bytes read from the file. Returns b'' if EOF is reached.
        """
        if self.closed:
            raise ValueError("I/O operation on closed file")
        if n == 0:
            return b""

        current_pos = self._pos
        bytes_to_read: Optional[int]
        if n < 0:
            bytes_to_read = self.size - current_pos
            end: Optional[int] = None  # Read to end
        else:
            bytes_to_read = min(n, self.size - current_pos)
            end = current_pos + bytes_to_read

        if bytes_to_read <= 0:
            return b""

        try:
            data = await self._backend_obj.read_range(current_pos, end)
            read_len = len(data)
            self._pos += read_len
            return data
        except Exception as e:
            # Catch specific backend errors if possible
            raise IOError(f"Async read failed: {e}") from e

    async def seek_async(self, offset: int, whence: int = io.SEEK_SET) -> int:
        """
        Asynchronously changes the stream position.

        Args:
            offset: The byte offset.
            whence: Reference point for the offset (io.SEEK_SET, io.SEEK_CUR,
                    io.SEEK_END).

        Returns:
            The new absolute position.

        Raises:
            ValueError: If whence is invalid or the resulting position is negative.
            IOError: If the operation fails.
        """
        if self.closed:
            raise ValueError("I/O operation on closed file")

        new_pos: int
        if whence == io.SEEK_SET:
            new_pos = offset
        elif whence == io.SEEK_CUR:
            new_pos = self._pos + offset
        elif whence == io.SEEK_END:
            new_pos = self.size + offset
        else:
            raise ValueError(f"Invalid whence value: {whence}")

        if new_pos < 0:
            raise ValueError("Negative seek position")

        # Allow seeking past EOF, position clamps on read
        self._pos = new_pos
        return self._pos

    async def tell_async(self) -> int:
        """Asynchronously returns the current stream position."""
        if self.closed:
            raise ValueError("I/O operation on closed file")
        return self._pos

    async def close_async(self) -> None:
        """Asynchronously closes the file and releases resources."""
        if not self._closed:
            self._closed = True
            try:
                await self.fs.close_async()
            except Exception as e:
                # Log error but proceed with closing the wrapper
                print(f"Warning: Error during backend aclose: {e}")
            # Release reference to backend object
            # self._backend_obj = None # Keep ref for potential reopen? No, close means close.

    async def get_public_url_async(self) -> Optional[str]:
        """Asynchronously attempts to get a publicly accessible URL."""
        if self.closed:
            raise ValueError("I/O operation on closed file")
        try:
            return await self.fs.get_public_url_async()
        except Exception as e:
            raise IOError(f"Failed to get public URL: {e}") from e

    async def __aenter__(self) -> "AsyncStoredFile":
        if self.closed:
            raise ValueError("I/O operation on closed file")
        # Perform any async setup if needed, e.g., ensure connection
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close_async()


# Required imports if not already present at the top
# You might need to `pip install anyio` or `trio` for more robust sync/async wrappers
# if the simple `_run_sync` helper proves insufficient.

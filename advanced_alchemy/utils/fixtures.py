"""Utilities for loading fixture data from JSON, JSONL, and CSV files."""

import csv
import gzip
import io
import zipfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Union

from advanced_alchemy.utils.deprecation import deprecated
from advanced_alchemy.utils.serialization import decode_json
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import AbstractContextManager
    from typing import TextIO

    from anyio import Path as AsyncPath

__all__ = ("FixtureCompression", "FixtureFormat", "open_fixture", "open_fixture_async", "open_fixture_sync")

FixtureFormat = Literal["json", "jsonl", "csv"]
"""Fixture file format: ``"json"`` (array), ``"jsonl"`` (one JSON value per line), or ``"csv"`` (header row plus rows)."""
FixtureCompression = Literal["gzip", "zip"]
"""Fixture compression: ``"gzip"`` (``.gz``) or ``"zip"`` (``.zip``); ``None`` means uncompressed."""

_FORMAT_PRIORITY: "tuple[FixtureFormat, ...]" = ("json", "jsonl", "csv")
_COMPRESSION_SUFFIXES: "dict[FixtureCompression, str]" = {"gzip": ".gz", "zip": ".zip"}
_TEXT_ENCODING = "utf-8-sig"
_READ_ERRORS = (OSError, zipfile.BadZipFile, gzip.BadGzipFile, EOFError, zlib.error)


def open_fixture_sync(fixtures_path: "Union[Path, AsyncPath]", fixture_name: str) -> Any:
    """Load a JSON, JSONL, or CSV fixture synchronously.

    Supports plain files, gzip-compressed files (``.gz``), and zip archives (``.zip``).
    Formats are resolved in priority order: ``json`` > ``jsonl`` > ``csv``. Both
    lowercase and uppercase fixture names are checked according to format and
    compression rules. Text is decoded using ``utf-8-sig``.

    Unsharded ``json`` fixtures return the decoded top-level JSON value unchanged.
    Unsharded ``jsonl`` and ``csv`` fixtures return a list of decoded records or
    dictionaries.

    Args:
        fixtures_path: Directory path containing fixture files. Can be a
            :class:`pathlib.Path` or :class:`anyio.Path` instance.
        fixture_name: Fixture base name without file extension.

    Raises:
        FileNotFoundError: If no matching fixture file exists.
        OSError: If an I/O or decompression error occurs while reading the file.
        ValueError: If a zip archive contains no matching member, a JSONL line
            contains invalid JSON, or a JSON fixture read as records is not an array.

    Returns:
        Any: Decoded JSON data or a list of records.

    Examples:
        >>> from pathlib import Path
        >>> fixtures_path = Path("./fixtures")
        >>> data = open_fixture_sync(fixtures_path, "users")
        >>> print(data)
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    """
    files = _FixtureLocator(Path(fixtures_path), fixture_name).resolve()
    if len(files) == 1 and files[0].shard_index is None:
        return files[0].read()
    return [record for fixture_file in files for record in fixture_file.iter_records()]


async def open_fixture_async(fixtures_path: "Union[Path, AsyncPath]", fixture_name: str) -> Any:
    """Load a JSON, JSONL, or CSV fixture asynchronously.

    Offloads synchronous fixture resolution, decompression, and parsing to a
    worker thread via :func:`~advanced_alchemy.utils.sync_tools.async_`.

    Args:
        fixtures_path: Directory path containing fixture files. Can be a
            :class:`pathlib.Path` or :class:`anyio.Path` instance.
        fixture_name: Fixture base name without file extension.

    Raises:
        FileNotFoundError: If no matching fixture file exists.
        OSError: If an I/O or decompression error occurs while reading the file.
        ValueError: If a zip archive contains no matching member, a JSONL line
            contains invalid JSON, or a JSON fixture read as records is not an array.

    Returns:
        Any: Decoded JSON data or a list of records.

    Examples:
        >>> from pathlib import Path
        >>> fixtures_path = Path("./fixtures")
        >>> data = await open_fixture_async(fixtures_path, "users")
        >>> print(data)
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    """
    return await async_(open_fixture_sync)(Path(str(fixtures_path)), fixture_name)


@deprecated("1.13.0", removal_in="2.0", alternative="open_fixture_sync", kind="function")
def open_fixture(fixtures_path: "Union[Path, AsyncPath]", fixture_name: str) -> Any:
    """Load a JSON, JSONL, or CSV fixture synchronously.

    Deprecated since 1.13.0 and scheduled for removal in 2.0. Use
    :func:`open_fixture_sync` instead.

    Args:
        fixtures_path: Directory path containing fixture files. Can be a
            :class:`pathlib.Path` or :class:`anyio.Path` instance.
        fixture_name: Fixture base name without file extension.

    Raises:
        FileNotFoundError: If no matching fixture file exists.
        OSError: If an I/O or decompression error occurs while reading the file.
        ValueError: If a zip archive contains no matching member, a JSONL line
            contains invalid JSON, or a JSON fixture read as records is not an array.

    Returns:
        Any: Decoded JSON data or a list of records.
    """
    return open_fixture_sync(fixtures_path, fixture_name)


class _FixtureFile:
    """Streaming reader for a single plain, gzipped, or zipped fixture file."""

    __slots__ = ("compression", "file_format", "fixture_name", "path", "shard_index")

    def __init__(
        self,
        path: "Path",
        fixture_name: str,
        file_format: FixtureFormat,
        compression: "Optional[FixtureCompression]",
        shard_index: "Optional[int]",
    ) -> None:
        """Initialize a fixture file descriptor.

        Args:
            path: Path to the fixture file on disk.
            fixture_name: Logical fixture name without extension.
            file_format: Fixture format (``"json"``, ``"jsonl"``, or ``"csv"``).
            compression: Compression kind (``"gzip"``, ``"zip"``, or ``None``).
            shard_index: Optional 1-based shard index, or ``None`` when unsharded.
        """
        self.path = path
        self.fixture_name = fixture_name
        self.file_format = file_format
        self.compression = compression
        self.shard_index = shard_index

    def read(self) -> Any:
        """Read and decode the entire fixture file.

        Raises:
            OSError: If reading or decompressing the fixture file fails.
            ValueError: If a zip archive has no matching member or JSONL content is invalid.

        Returns:
            Any: The decoded JSON value or a list of records for JSONL/CSV files.
        """
        if self.file_format in ("jsonl", "csv"):
            return list(self.iter_records())
        try:
            with self._open_text() as handle:
                content = handle.read()
        except _READ_ERRORS as exc:
            msg = f"Error reading fixture file {self.path}: {exc}"
            raise OSError(msg) from exc
        return decode_json(content)

    def iter_records(self) -> "Generator[Any, None, None]":
        """Stream decoded records from the fixture file one at a time.

        Raises:
            OSError: If reading or decompressing the fixture file fails.
            ValueError: If a ``json`` file does not contain a top-level array,
                a zip archive has no matching member, or a JSONL line is invalid JSON.

        Yields:
            Any: Each decoded record in the fixture file.
        """
        if self.file_format == "json":
            value = self.read()
            if not isinstance(value, list):
                msg = f"Fixture {self.fixture_name!r} file {self.path} must contain a JSON array, got {type(value).__name__}"
                raise ValueError(msg)
            yield from value
            return

        try:
            with self._open_text() as handle:
                if self.file_format == "csv":
                    yield from csv.DictReader(handle)
                else:
                    for lineno, line in enumerate(handle, start=1):
                        if not line.strip():
                            continue
                        yield self._decode_line(line, lineno)
        except _READ_ERRORS as exc:
            msg = f"Error reading fixture file {self.path}: {exc}"
            raise OSError(msg) from exc

    def _open_text(self) -> "AbstractContextManager[TextIO]":
        """Open the fixture file as a streaming UTF-8-SIG text handle.

        Returns:
            AbstractContextManager[TextIO]: A text stream context manager.
        """
        newline = "" if self.file_format == "csv" else None
        if self.compression == "gzip":
            return gzip.open(self.path, mode="rt", encoding=_TEXT_ENCODING, newline=newline)
        if self.compression == "zip":
            with zipfile.ZipFile(self.path, mode="r") as archive:
                member = archive.open(self._select_zip_member(archive), mode="r")
            return io.TextIOWrapper(member, encoding=_TEXT_ENCODING, newline=newline)
        return self.path.open(mode="r", encoding=_TEXT_ENCODING, newline=newline)

    def _select_zip_member(self, archive: zipfile.ZipFile) -> str:
        """Select the matching member name inside a zip fixture archive.

        Args:
            archive: Open zip archive handle.

        Raises:
            ValueError: If the archive contains no file ending with the fixture suffix.

        Returns:
            str: Selected zip member name.
        """
        suffix = f".{self.file_format}"
        members = [name for name in archive.namelist() if name.endswith(suffix)]
        if not members:
            msg = f"No {self.file_format.upper()} files found in zip archive: {self.path}"
            raise ValueError(msg)
        for candidate in (self.path.stem, f"{self.fixture_name}{suffix}"):
            if candidate in members:
                return candidate
        return members[0]

    def _decode_line(self, line: str, lineno: int) -> Any:
        """Decode one JSONL line and attach file path and line number on failure.

        Args:
            line: Raw line text from the JSONL file.
            lineno: 1-based line number within the file.

        Raises:
            ValueError: If the line is not valid JSON.

        Returns:
            Any: The decoded JSON value for the line.
        """
        try:
            return decode_json(line)
        except Exception as exc:
            msg = f"Invalid JSON in fixture file {self.path} at line {lineno}"
            raise ValueError(msg) from exc


class _FixtureLocator:
    """Locator that resolves fixture files by format priority and compression."""

    __slots__ = ("base_path", "fixture_name")

    def __init__(self, base_path: "Path", fixture_name: str) -> None:
        """Initialize a fixture locator.

        Args:
            base_path: Directory path containing fixture files.
            fixture_name: Logical fixture name without extension.
        """
        self.base_path = base_path
        self.fixture_name = fixture_name

    def resolve(self) -> "list[_FixtureFile]":
        """Resolve the highest-priority fixture file for the configured name.

        Raises:
            FileNotFoundError: If no matching fixture file is found.

        Returns:
            list[_FixtureFile]: Ordered list containing the resolved fixture file.
        """
        for file_format in _FORMAT_PRIORITY:
            candidates = self._unsharded_candidates(file_format)
            if candidates:
                return candidates[:1]
        msg = (
            f"Could not find the {self.fixture_name} fixture "
            "(tried .json, .jsonl, .csv with optional .gz/.zip compression, numbered shards, and case variations)"
        )
        raise FileNotFoundError(msg)

    def _unsharded_candidates(self, file_format: FixtureFormat) -> "list[_FixtureFile]":
        """Collect existing unsharded fixture candidates for a format in priority order.

        Args:
            file_format: Fixture format to probe.

        Returns:
            list[_FixtureFile]: Existing deduplicated candidate fixture files.
        """
        upper_name = self.fixture_name.upper()
        variants: list[tuple[str, Optional[FixtureCompression]]] = [
            (f"{self.fixture_name}.{file_format}", None),
        ]
        if file_format == "csv":
            variants.append((f"{upper_name}.{file_format}", None))
        for comp, suffix in _COMPRESSION_SUFFIXES.items():
            variants.append((f"{upper_name}.{file_format}{suffix}", comp))
            variants.append((f"{self.fixture_name}.{file_format}{suffix}", comp))

        candidates: list[_FixtureFile] = []
        seen: set[Union[tuple[int, int], str]] = set()
        for name, compression in variants:
            path = self.base_path / name
            if not path.is_file():
                continue
            identity = self._identity(path)
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append(_FixtureFile(path, self.fixture_name, file_format, compression, None))
        return candidates

    @staticmethod
    def _identity(path: "Path") -> "Union[tuple[int, int], str]":
        """Return a filesystem identity key for deduplicating equivalent paths.

        Args:
            path: Existing file path.

        Returns:
            Union[tuple[int, int], str]: Device/inode pair when available, else path string.
        """
        stat = path.stat()
        if stat.st_ino:
            return (stat.st_dev, stat.st_ino)
        return str(path)

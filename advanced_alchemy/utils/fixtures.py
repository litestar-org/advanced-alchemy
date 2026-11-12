"""Utilities for loading and writing fixture data in JSON, JSONL, and CSV formats."""

import contextlib
import csv
import gzip
import io
import re
import warnings
import zipfile
import zlib
from collections.abc import AsyncIterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Union

from advanced_alchemy.utils.deprecation import deprecated
from advanced_alchemy.utils.serialization import decode_json, encode_json
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator, Iterable, Iterator
    from contextlib import AbstractContextManager
    from typing import IO, BinaryIO, TextIO

    from anyio import Path as AsyncPath
    from typing_extensions import TypeGuard

__all__ = (
    "FixtureCompression",
    "FixtureFormat",
    "iter_fixture_async",
    "iter_fixture_sync",
    "open_fixture",
    "open_fixture_async",
    "open_fixture_sync",
    "write_fixture_async",
    "write_fixture_sync",
)

FixtureFormat = Literal["json", "jsonl", "csv"]
"""Fixture file format: ``"json"`` (array), ``"jsonl"`` (one JSON value per line), or ``"csv"`` (header row plus rows)."""
FixtureCompression = Literal["gzip", "zip"]
"""Fixture compression: ``"gzip"`` (``.gz``) or ``"zip"`` (``.zip``); ``None`` means uncompressed."""

_FORMAT_PRIORITY: "tuple[FixtureFormat, ...]" = ("json", "jsonl", "csv")
_COMPRESSION_SUFFIXES: "dict[FixtureCompression, str]" = {"gzip": ".gz", "zip": ".zip"}
_SUFFIX_COMPRESSIONS: "dict[str, FixtureCompression]" = {".gz": "gzip", ".zip": "zip"}
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


def iter_fixture_sync(
    fixtures_path: "Union[Path, AsyncPath]", fixture_name: str, *, batch_size: int = 1000
) -> "Iterator[list[Any]]":
    """Stream decoded fixture records in non-empty batches synchronously.

    Validates ``batch_size`` and resolves the fixture file or numbered shards
    eagerly at call time, then yields non-empty batches of at most
    ``batch_size`` records across shard boundaries. Closing the returned
    iterator early releases any open file handle immediately.

    Args:
        fixtures_path: Directory path containing fixture files. Can be a
            :class:`pathlib.Path` or :class:`anyio.Path` instance.
        fixture_name: Fixture base name without file extension.
        batch_size: Maximum number of records per yielded batch. Must be at least 1.

    Raises:
        FileNotFoundError: If no matching fixture file exists.
        OSError: If an I/O or decompression error occurs while reading a file.
        ValueError: If ``batch_size`` is less than 1, both an unsharded file and
            numbered shards exist, shard validation fails, a zip archive contains
            no matching member, a JSONL line contains invalid JSON, or a JSON
            fixture is not an array.

    Returns:
        Iterator[list[Any]]: Iterator yielding non-empty lists of records.
    """
    return _FixtureLocator(Path(fixtures_path), fixture_name).iter_batches(batch_size)


async def iter_fixture_async(
    fixtures_path: "Union[Path, AsyncPath]", fixture_name: str, *, batch_size: int = 1000
) -> "AsyncIterator[list[Any]]":
    """Stream decoded fixture records in non-empty batches asynchronously.

    Offloads fixture resolution, batch reads, and generator teardown to worker
    threads via :func:`~advanced_alchemy.utils.sync_tools.async_`. Validation
    and resolution run on the first iteration step. Callers exiting early must
    call ``aclose()`` or consume the iterator completely so underlying file
    handles are closed promptly.

    Args:
        fixtures_path: Directory path containing fixture files. Can be a
            :class:`pathlib.Path` or :class:`anyio.Path` instance.
        fixture_name: Fixture base name without file extension.
        batch_size: Maximum number of records per yielded batch. Must be at least 1.

    Raises:
        FileNotFoundError: If no matching fixture file exists.
        OSError: If an I/O or decompression error occurs while reading a file.
        ValueError: If ``batch_size`` is less than 1, both an unsharded file and
            numbered shards exist, shard validation fails, a zip archive contains
            no matching member, a JSONL line contains invalid JSON, or a JSON
            fixture is not an array.

    Yields:
        list[Any]: Non-empty batch of decoded records.
    """
    locator = _FixtureLocator(Path(str(fixtures_path)), fixture_name)
    batches = await async_(locator.iter_batches)(batch_size)
    try:
        while True:
            batch = await async_(_FixtureLocator.next_batch)(batches)
            if batch is None:
                return
            yield batch
    finally:
        await async_(batches.close)()


def write_fixture_sync(
    fixtures_path: "Union[Path, AsyncPath]",
    fixture_name: str,
    records: "Iterable[Any]",
    *,
    file_format: FixtureFormat = "json",
    compression: "Optional[FixtureCompression]" = None,
    max_bytes: "Optional[int]" = None,
    max_records: "Optional[int]" = None,
) -> "list[Path]":
    """Write fixture records synchronously in JSON, JSONL, or CSV format.

    Streams encoded records into temporary ``.tmp`` files, removes any existing
    fixture files matching ``fixture_name`` across all formats, compressions,
    and shard layouts upon completion, and atomically renames temporary files
    into place.

    Args:
        fixtures_path: Target directory path for fixture files. Created if it
            does not exist. Can be a :class:`pathlib.Path` or :class:`anyio.Path`.
        fixture_name: Fixture base name without file extension.
        records: Iterable of records to write.
        file_format: Output format (``"json"``, ``"jsonl"``, or ``"csv"``).
        compression: Optional compression (``"gzip"``, ``"zip"``, or ``None``).
        max_bytes: Optional maximum on-disk byte size per shard. Must be at least 1.
        max_records: Optional maximum record count per shard. Must be at least 1.

    Raises:
        ValueError: If ``file_format``, ``compression``, ``max_bytes``, or
            ``max_records`` is invalid, or if CSV records introduce keys absent
            from the header.
        TypeError: If ``file_format`` is ``"csv"`` and a record is not a mapping.
        OSError: If writing, deleting stale files, or renaming files fails.

    Returns:
        list[Path]: Final written fixture paths in shard order.

    Examples:
        >>> from pathlib import Path
        >>> fixtures_path = Path("./fixtures")
        >>> paths = write_fixture_sync(
        ...     fixtures_path,
        ...     "users",
        ...     [{"id": 1, "name": "Alice"}],
        ...     file_format="jsonl",
        ...     compression="gzip",
        ... )
    """
    writer = _FixtureWriter(
        Path(str(fixtures_path)),
        fixture_name,
        file_format=file_format,
        compression=compression,
        max_bytes=max_bytes,
        max_records=max_records,
    )
    try:
        writer.write_many(records)
        return writer.commit()
    except BaseException:
        writer.abort()
        raise


async def write_fixture_async(
    fixtures_path: "Union[Path, AsyncPath]",
    fixture_name: str,
    records: "Union[Iterable[Any], AsyncIterable[Any]]",
    *,
    file_format: FixtureFormat = "json",
    compression: "Optional[FixtureCompression]" = None,
    max_bytes: "Optional[int]" = None,
    max_records: "Optional[int]" = None,
    batch_size: int = 1000,
) -> "list[Path]":
    """Write fixture records asynchronously in JSON, JSONL, or CSV format.

    Streams records from a synchronous or asynchronous iterable in batches of
    ``batch_size`` into temporary ``.tmp`` files, offloads writer construction,
    batch writes, commit, and abort to worker threads via
    :func:`~advanced_alchemy.utils.sync_tools.async_`, removes stale fixture
    files matching ``fixture_name`` on completion, and atomically renames
    temporary files into place.

    Args:
        fixtures_path: Target directory path for fixture files. Created if it
            does not exist. Can be a :class:`pathlib.Path` or :class:`anyio.Path`.
        fixture_name: Fixture base name without file extension.
        records: Synchronous or asynchronous iterable of records to write.
        file_format: Output format (``"json"``, ``"jsonl"``, or ``"csv"``).
        compression: Optional compression (``"gzip"``, ``"zip"``, or ``None``).
        max_bytes: Optional maximum on-disk byte size per shard. Must be at least 1.
        max_records: Optional maximum record count per shard. Must be at least 1.
        batch_size: Maximum number of records buffered before offloading a batch
            write to a worker thread. Must be at least 1.

    Raises:
        ValueError: If ``batch_size``, ``file_format``, ``compression``,
            ``max_bytes``, or ``max_records`` is invalid, or if CSV records
            introduce keys absent from the header.
        TypeError: If ``file_format`` is ``"csv"`` and a record is not a mapping.
        OSError: If writing, deleting stale files, or renaming files fails.

    Returns:
        list[Path]: Final written fixture paths in shard order.

    Examples:
        >>> from pathlib import Path
        >>> async def stream_users():
        ...     yield {"id": 1, "name": "Alice"}
        >>> paths = await write_fixture_async(
        ...     Path("./fixtures"),
        ...     "users",
        ...     stream_users(),
        ...     file_format="jsonl",
        ...     compression="gzip",
        ... )
    """
    if batch_size < 1:
        msg = f"batch_size must be at least 1, got {batch_size}"
        raise ValueError(msg)
    writer = await async_(_FixtureWriter)(
        Path(str(fixtures_path)),
        fixture_name,
        file_format=file_format,
        compression=compression,
        max_bytes=max_bytes,
        max_records=max_records,
    )
    try:
        batch: list[Any] = []
        if isinstance(records, AsyncIterable):
            async for record in records:
                batch.append(record)
                if len(batch) >= batch_size:
                    await async_(writer.write_many)(batch)
                    batch = []
        else:
            for record in records:
                batch.append(record)
                if len(batch) >= batch_size:
                    await async_(writer.write_many)(batch)
                    batch = []
        if batch:
            await async_(writer.write_many)(batch)
        return await async_(writer.commit)()
    except BaseException:
        await async_(writer.abort)()
        raise


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

    @staticmethod
    def next_batch(batches: "Iterator[list[Any]]") -> "Optional[list[Any]]":
        """Return the next batch from a batch iterator, or ``None`` when exhausted.

        Args:
            batches: Synchronous batch iterator.

        Returns:
            Optional[list[Any]]: Next batch of records, or ``None`` at end of stream.
        """
        return next(batches, None)

    def resolve(self) -> "list[_FixtureFile]":
        """Resolve the highest-priority fixture file or shards for the configured name.

        Raises:
            FileNotFoundError: If no matching fixture file or shard is found.
            ValueError: If both an unsharded file and numbered shards exist for the
                resolved format, or if shard validation fails.

        Returns:
            list[_FixtureFile]: Ordered list containing the resolved fixture file or shards.
        """
        for file_format in _FORMAT_PRIORITY:
            candidates = self._unsharded_candidates(file_format)
            shards = self._shards(file_format)
            if candidates and shards:
                paths = ", ".join(str(fixture_file.path) for fixture_file in [*candidates, *shards])
                msg = f"Fixture {self.fixture_name!r} has both an unsharded file and numbered shards: {paths}"
                raise ValueError(msg)
            if shards:
                return shards
            if candidates:
                return candidates[:1]
        msg = (
            f"Could not find the {self.fixture_name} fixture "
            "(tried .json, .jsonl, .csv with optional .gz/.zip compression, numbered shards, and case variations)"
        )
        raise FileNotFoundError(msg)

    def iter_batches(self, batch_size: int) -> "Generator[list[Any], None, None]":
        """Validate ``batch_size`` and resolve files eagerly, then stream record batches.

        Args:
            batch_size: Maximum number of records per yielded batch. Must be at least 1.

        Raises:
            ValueError: If ``batch_size`` is less than 1, or if fixture/shard resolution fails.
            FileNotFoundError: If no matching fixture file or shard is found.

        Returns:
            Generator[list[Any], None, None]: Generator yielding non-empty record batches.
        """
        if batch_size < 1:
            msg = f"batch_size must be at least 1, got {batch_size}"
            raise ValueError(msg)
        return self._batches(self.resolve(), batch_size)

    def existing_paths(self) -> "list[Path]":
        """Return every existing unsharded or sharded path matching the fixture name.

        Skips shard index validation so broken, gapped, or duplicate layouts can
        still be discovered for cleanup before replacing a fixture.

        Returns:
            list[Path]: Sorted deduplicated fixture file paths in ``base_path``.
        """
        if not self.base_path.is_dir():
            return []
        seen: set[Union[tuple[int, int], str]] = set()
        paths: list[Path] = []
        for file_format in _FORMAT_PRIORITY:
            for fixture_file in [*self._unsharded_candidates(file_format), *self._shard_matches(file_format)]:
                identity = self._identity(fixture_file.path)
                if identity not in seen:
                    seen.add(identity)
                    paths.append(fixture_file.path)
        return sorted(paths)

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

    def _shard_matches(self, file_format: FixtureFormat) -> "list[_FixtureFile]":
        """Collect matching numbered shard files for a format without index validation.

        Args:
            file_format: Fixture format to probe.

        Returns:
            list[_FixtureFile]: Deduplicated matching shard descriptors in directory sort order.
        """
        if not self.base_path.is_dir():
            return []
        pattern = re.compile(
            rf"^(?P<name>{re.escape(self.fixture_name)}|{re.escape(self.fixture_name.upper())})"
            rf"\.(?P<index>\d+)\.(?P<fmt>json|jsonl|csv)(?P<comp>\.gz|\.zip)?$"
        )
        matches: list[_FixtureFile] = []
        seen: set[Union[tuple[int, int], str]] = set()
        for path in sorted(self.base_path.iterdir()):
            match = pattern.match(path.name)
            if match is None or match["fmt"] != file_format or not path.is_file():
                continue
            identity = self._identity(path)
            if identity in seen:
                continue
            seen.add(identity)
            compression = _SUFFIX_COMPRESSIONS.get(match["comp"] or "")
            matches.append(_FixtureFile(path, self.fixture_name, file_format, compression, int(match["index"])))
        return matches

    def _shards(self, file_format: FixtureFormat) -> "list[_FixtureFile]":
        """Validate and return numbered shards for a format in numeric index order.

        Args:
            file_format: Fixture format to validate.

        Raises:
            ValueError: If duplicate shard indexes exist, index 0 is present, or any
                shard index in ``1..N`` is missing.

        Returns:
            list[_FixtureFile]: Validated shard descriptors sorted by shard index.
        """
        by_index: dict[int, list[_FixtureFile]] = {}
        for fixture_file in self._shard_matches(file_format):
            if fixture_file.shard_index is None:
                continue
            by_index.setdefault(fixture_file.shard_index, []).append(fixture_file)
        if not by_index:
            return []

        indexes = sorted(by_index)
        for index in indexes:
            group = by_index[index]
            if len(group) > 1:
                paths = ", ".join(str(fixture_file.path) for fixture_file in group)
                msg = f"Fixture {self.fixture_name!r} has multiple shards with index {index}: {paths}"
                raise ValueError(msg)

        if indexes[0] == 0:
            paths = ", ".join(str(fixture_file.path) for fixture_file in by_index[0])
            msg = f"Fixture {self.fixture_name!r} shard indexes start at 1, found index 0: {paths}"
            raise ValueError(msg)

        missing_indexes = sorted(set(range(1, indexes[-1] + 1)) - set(indexes))
        if missing_indexes:
            missing = ", ".join(str(index) for index in missing_indexes)
            paths = ", ".join(str(by_index[index][0].path) for index in indexes)
            msg = f"Fixture {self.fixture_name!r} is missing shard index(es) {missing}: {paths}"
            raise ValueError(msg)

        return [by_index[index][0] for index in indexes]

    def _batches(self, files: "list[_FixtureFile]", batch_size: int) -> "Generator[list[Any], None, None]":
        """Yield non-empty batches of at most ``batch_size`` records across resolved files.

        Args:
            files: Ordered fixture file descriptors to stream.
            batch_size: Positive maximum batch size.

        Yields:
            list[Any]: Non-empty list of decoded records.
        """
        batch: list[Any] = []
        for fixture_file in files:
            records = fixture_file.iter_records()
            try:
                for record in records:
                    batch.append(record)
                    if len(batch) == batch_size:
                        yield batch
                        batch = []
            finally:
                records.close()
        if batch:
            yield batch

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


class _FixtureWriter:
    """Streaming writer for plain, gzipped, and zipped fixture files."""

    __slots__ = (
        "_archive",
        "_closed",
        "_final_paths",
        "_force_rollover",
        "_header",
        "_pending",
        "_raw",
        "_record_count",
        "_shard_records",
        "_sink",
        "_temp_paths",
        "base_path",
        "compression",
        "file_format",
        "fixture_name",
        "max_bytes",
        "max_records",
    )

    def __init__(
        self,
        base_path: "Path",
        fixture_name: str,
        *,
        file_format: FixtureFormat,
        compression: "Optional[FixtureCompression]",
        max_bytes: "Optional[int]",
        max_records: "Optional[int]",
    ) -> None:
        """Initialize a streaming fixture writer and validate options before disk access.

        Args:
            base_path: Target directory path for written fixture files.
            fixture_name: Logical fixture name without extension.
            file_format: Output format (``"json"``, ``"jsonl"``, or ``"csv"``).
            compression: Optional compression (``"gzip"``, ``"zip"``, or ``None``).
            max_bytes: Optional maximum on-disk byte size per shard.
            max_records: Optional maximum record count per shard.

        Raises:
            ValueError: If any format, compression, or shard limit argument is invalid.
        """
        if file_format not in ("json", "jsonl", "csv"):
            msg = f"Unsupported fixture format {file_format!r}; expected 'json', 'jsonl', or 'csv'"
            raise ValueError(msg)
        if compression not in (None, "gzip", "zip"):
            msg = f"Unsupported fixture compression {compression!r}; expected 'gzip', 'zip', or None"
            raise ValueError(msg)
        if max_bytes is not None and max_bytes < 1:
            msg = f"max_bytes must be at least 1, got {max_bytes}"
            raise ValueError(msg)
        if max_records is not None and max_records < 1:
            msg = f"max_records must be at least 1, got {max_records}"
            raise ValueError(msg)

        self.base_path = base_path
        self.fixture_name = fixture_name
        self.file_format: FixtureFormat = file_format
        self.compression: Optional[FixtureCompression] = compression
        self.max_bytes = max_bytes
        self.max_records = max_records
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._archive: Optional[zipfile.ZipFile] = None
        self._closed = False
        self._final_paths: list[Path] = []
        self._force_rollover = False
        self._header: Optional[list[Any]] = None
        self._pending = 0
        self._raw: Optional[BinaryIO] = None
        self._record_count = 0
        self._shard_records = 0
        self._sink: Optional[Union[IO[bytes], gzip.GzipFile]] = None
        self._temp_paths: list[Path] = []

    @property
    def sharded(self) -> bool:
        """Return whether numbered shard output is enabled."""
        return self.max_bytes is not None or self.max_records is not None

    def write(self, record: Any) -> None:
        """Encode and stream a single record to the current shard.

        Args:
            record: Record value to serialize and write.

        Raises:
            RuntimeError: If the writer has already been committed or aborted.
            TypeError: If writing CSV and ``record`` is not a mapping.
            ValueError: If writing CSV and ``record`` introduces keys absent from the header.
        """
        if self._closed:
            msg = "Fixture writer is closed"
            raise RuntimeError(msg)
        if self._raw is None:
            self._open_shard()
        self._record_count += 1
        chunk = self._encode(record, first_in_shard=self._shard_records == 0)
        if self._shard_records > 0 and self._roll_over_needed_after_flush(len(chunk)):
            self._close_shard()
            self._open_shard()
            chunk = self._encode(record, first_in_shard=True)
        if self._shard_records == 0 and self.max_bytes is not None:
            projected = self._projected_size(len(chunk))
            if projected > self.max_bytes:
                warnings.warn(
                    f"Record {self._record_count} of fixture {self.fixture_name!r} exceeds "
                    f"max_bytes={self.max_bytes} on its own (projected {projected} bytes); "
                    "writing it to its own shard",
                    UserWarning,
                    stacklevel=2,
                )
                self._force_rollover = True
        self._require_sink().write(chunk)
        self._pending += len(chunk)
        self._shard_records += 1

    def write_many(self, records: "Iterable[Any]") -> None:
        """Stream every record from an iterable into the writer.

        Args:
            records: Iterable of records to write.
        """
        for record in records:
            self.write(record)

    def commit(self) -> "list[Path]":
        """Finalize output, delete stale fixture files, and rename temp files into place.

        Returns:
            list[Path]: Final written fixture file paths in shard order.
        """
        if self._raw is None and not self._final_paths:
            self._open_shard()
        self._close_shard()
        for path in _FixtureLocator(self.base_path, self.fixture_name).existing_paths():
            path.unlink(missing_ok=True)
        for temp, final in zip(self._temp_paths, self._final_paths):
            temp.replace(final)
        self._closed = True
        return list(self._final_paths)

    def abort(self) -> None:
        """Close any open streams and delete temporary files idempotently."""
        self._closed = True
        if self._sink is not None:
            with contextlib.suppress(Exception):
                self._sink.close()
        if self._archive is not None:
            with contextlib.suppress(Exception):
                self._archive.close()
        if self._raw is not None:
            with contextlib.suppress(Exception):
                self._raw.close()
        self._sink = None
        self._archive = None
        self._raw = None
        for temp in self._temp_paths:
            temp.unlink(missing_ok=True)

    def _final_path(self, index: int) -> "Path":
        """Compute the final destination path for a 1-based shard index."""
        suffix = _COMPRESSION_SUFFIXES.get(self.compression, "") if self.compression is not None else ""
        if self.sharded:
            return self.base_path / f"{self.fixture_name}.{index:03d}.{self.file_format}{suffix}"
        return self.base_path / f"{self.fixture_name}.{self.file_format}{suffix}"

    def _open_shard(self) -> None:
        """Open the next temporary shard stream with deterministic compression settings."""
        final = self._final_path(len(self._final_paths) + 1)
        temp = final.with_name(f"{final.name}.tmp")
        self._final_paths.append(final)
        self._temp_paths.append(temp)
        self._raw = temp.open("wb")
        if self.compression == "gzip":
            self._sink = gzip.GzipFile(filename="", mode="wb", fileobj=self._raw, mtime=0)
        elif self.compression == "zip":
            self._archive = zipfile.ZipFile(self._raw, mode="w", compression=zipfile.ZIP_DEFLATED)
            info = zipfile.ZipInfo(final.name[: -len(".zip")], date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            self._sink = self._archive.open(info, mode="w", force_zip64=True)
        else:
            self._sink = self._raw
        self._shard_records = 0
        self._pending = 0
        self._force_rollover = False

    def _close_shard(self) -> None:
        """Write closing delimiters if needed and close the active shard streams."""
        sink = self._require_sink()
        if self.file_format == "json":
            sink.write(b"[]\n" if self._shard_records == 0 else b"\n]\n")
        raw = self._require_raw()
        if sink is not raw:
            sink.close()
        if self._archive is not None:
            self._archive.close()
        raw.close()
        self._sink = None
        self._archive = None
        self._raw = None

    def _encode(self, record: Any, *, first_in_shard: bool) -> bytes:
        """Encode one record into UTF-8 bytes without mutating shard counters."""
        if self.file_format == "json":
            prefix = b"[\n" if first_in_shard else b",\n"
            return prefix + encode_json(record).encode("utf-8")
        if self.file_format == "jsonl":
            return (encode_json(record) + "\n").encode("utf-8")
        if not self._is_mapping(record):
            msg = f"CSV fixture records must be mappings, got {type(record).__name__}"
            raise TypeError(msg)
        if self._header is None:
            self._header = list(record.keys())
        header_keys = set(self._header)
        extra = [key for key in record if key not in header_keys]
        if extra:
            msg = (
                f"CSV record {self._record_count} of fixture {self.fixture_name!r} "
                f"has keys not in the header: {extra!r}"
            )
            raise ValueError(msg)
        header_row = self._encode_csv_row(self._header) if first_in_shard else ""
        data_row = self._encode_csv_row([record.get(key, "") for key in self._header])
        return (header_row + data_row).encode("utf-8")

    @staticmethod
    def _is_mapping(value: Any) -> "TypeGuard[Mapping[Any, Any]]":
        """Narrow an arbitrary record to a typed mapping for static type checkers."""
        return isinstance(value, Mapping)

    def _encode_csv_row(self, values: "Iterable[Any]") -> str:
        """Format a single CSV row using Python's excel dialect."""
        buffer = io.StringIO()
        csv.writer(buffer).writerow(values)
        return buffer.getvalue()

    def _require_sink(self) -> "Union[IO[bytes], gzip.GzipFile]":
        """Return the active byte sink handle or raise if the writer is closed."""
        if self._sink is None:
            msg = "Fixture writer is closed"
            raise RuntimeError(msg)
        return self._sink

    def _require_raw(self) -> "BinaryIO":
        """Return the active underlying binary file handle or raise if closed."""
        if self._raw is None:
            msg = "Fixture writer is closed"
            raise RuntimeError(msg)
        return self._raw

    def _projected_size(self, chunk_size: int) -> int:
        """Estimate the on-disk shard size in bytes after writing ``chunk_size`` bytes."""
        raw_pos = self._require_raw().tell()
        if self.compression is None:
            return raw_pos + chunk_size + 64
        pending = self._pending + chunk_size
        if self.compression == "gzip":
            reserve = 64
        else:
            member_name = self._final_paths[-1].name[: -len(".zip")]
            reserve = 256 + 2 * len(member_name.encode("utf-8"))
        return raw_pos + pending + 5 * (pending // 16383 + 1) + reserve

    def _roll_over_needed_after_flush(self, chunk_size: int) -> bool:
        """Determine whether to open a new shard before writing, flushing gzip if needed."""
        if self._force_rollover:
            return True
        if self.max_records is not None and self._shard_records >= self.max_records:
            return True
        if self.max_bytes is not None:
            projected = self._projected_size(chunk_size)
            if projected > self.max_bytes and self.compression == "gzip" and self._pending > 0:
                self._require_sink().flush()
                self._pending = 0
                projected = self._projected_size(chunk_size)
            return projected > self.max_bytes
        return False

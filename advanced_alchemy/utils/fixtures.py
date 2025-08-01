import gzip
import zipfile
from functools import partial
from typing import TYPE_CHECKING, Any, Union

from advanced_alchemy._serialization import decode_json
from advanced_alchemy.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from pathlib import Path

    from anyio import Path as AsyncPath

__all__ = ("open_fixture", "open_fixture_async")


def open_fixture(fixtures_path: "Union[Path, AsyncPath]", fixture_name: str) -> Any:
    """Loads JSON file with the specified fixture name.

    Supports plain JSON files, gzipped JSON files (.json.gz), and zipped JSON files (.json.zip).
    The function automatically detects the file format based on file extension and handles
    decompression transparently. Supports both lowercase and uppercase variations for better
    compatibility with database exports.

    Args:
        fixtures_path: The path to look for fixtures. Can be a :class:`pathlib.Path` or
            :class:`anyio.Path` instance.
        fixture_name: The fixture name to load (without file extension).

    Raises:
        FileNotFoundError: If no fixture file is found with any supported extension.
        OSError: If there's an error reading or decompressing the file.
        ValueError: If the JSON content is invalid.
        zipfile.BadZipFile: If the zip file is corrupted.
        gzip.BadGzipFile: If the gzip file is corrupted.

    Returns:
        Any: The parsed JSON data from the fixture file.

    Examples:
        >>> from pathlib import Path
        >>> fixtures_path = Path("./fixtures")
        >>> data = open_fixture(
        ...     fixtures_path, "users"
        ... )  # loads users.json, users.json.gz, or users.json.zip
        >>> print(data)
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    """
    from pathlib import Path

    base_path = Path(fixtures_path)

    # Try different file extensions in order of preference
    # Include both case variations for better compatibility with database exports
    file_variants = [
        (base_path / f"{fixture_name}.json", "plain"),
        (base_path / f"{fixture_name.upper()}.json.gz", "gzip"),  # Uppercase first (common for exports)
        (base_path / f"{fixture_name}.json.gz", "gzip"),
        (base_path / f"{fixture_name.upper()}.json.zip", "zip"),
        (base_path / f"{fixture_name}.json.zip", "zip"),
    ]

    for fixture_path, file_type in file_variants:
        if fixture_path.exists():
            try:
                f_data: str
                if file_type == "plain":
                    with fixture_path.open(mode="r", encoding="utf-8") as f:
                        f_data = f.read()
                elif file_type == "gzip":
                    with fixture_path.open(mode="rb") as f:
                        compressed_data = f.read()
                    f_data = gzip.decompress(compressed_data).decode("utf-8")
                elif file_type == "zip":
                    with zipfile.ZipFile(fixture_path, mode="r") as zf:
                        # Look for JSON file inside zip
                        json_files = [name for name in zf.namelist() if name.endswith(".json")]
                        if not json_files:
                            msg = f"No JSON files found in zip archive: {fixture_path}"
                            raise ValueError(msg)

                        # Use the first JSON file found, or prefer one matching the fixture name
                        json_file = next((name for name in json_files if name == f"{fixture_name}.json"), json_files[0])

                        with zf.open(json_file, mode="r") as f:
                            f_data = f.read().decode("utf-8")
                else:
                    continue  # Skip unknown file types

                return decode_json(f_data)
            except (OSError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
                msg = f"Error reading fixture file {fixture_path}: {exc}"
                raise OSError(msg) from exc

    # No valid fixture file found
    msg = f"Could not find the {fixture_name} fixture (tried .json, .json.gz, .json.zip with case variations)"
    raise FileNotFoundError(msg)


async def open_fixture_async(fixtures_path: "Union[Path, AsyncPath]", fixture_name: str) -> Any:
    """Loads JSON file with the specified fixture name asynchronously.

    Supports plain JSON files, gzipped JSON files (.json.gz), and zipped JSON files (.json.zip).
    The function automatically detects the file format based on file extension and handles
    decompression transparently. Supports both lowercase and uppercase variations for better
    compatibility with database exports. For compressed files, decompression is performed
    synchronously in a thread pool to avoid blocking the event loop.

    Args:
        fixtures_path: The path to look for fixtures. Can be a :class:`pathlib.Path` or
            :class:`anyio.Path` instance.
        fixture_name: The fixture name to load (without file extension).

    Raises:
        MissingDependencyError: If the `anyio` library is not installed.
        FileNotFoundError: If no fixture file is found with any supported extension.
        OSError: If there's an error reading or decompressing the file.
        ValueError: If the JSON content is invalid.
        zipfile.BadZipFile: If the zip file is corrupted.
        gzip.BadGzipFile: If the gzip file is corrupted.

    Returns:
        Any: The parsed JSON data from the fixture file.

    Examples:
        >>> from anyio import Path as AsyncPath
        >>> fixtures_path = AsyncPath("./fixtures")
        >>> data = await open_fixture_async(
        ...     fixtures_path, "users"
        ... )  # loads users.json, users.json.gz, or users.json.zip
        >>> print(data)
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    """
    try:
        from anyio import Path as AsyncPath
    except ImportError as exc:
        msg = "The `anyio` library is required to use this function. Please install it with `pip install anyio`."
        raise MissingDependencyError(msg) from exc

    from advanced_alchemy.utils.sync_tools import async_

    def _read_zip_file(path: "AsyncPath", name: str) -> str:
        """Helper function to read zip files."""
        with zipfile.ZipFile(str(path), mode="r") as zf:
            # Look for JSON file inside zip
            json_files = [file for file in zf.namelist() if file.endswith(".json")]
            if not json_files:
                error_msg = f"No JSON files found in zip archive: {path}"
                raise ValueError(error_msg)

            # Use the first JSON file found, or prefer one matching the fixture name
            json_file = next((file for file in json_files if file == f"{name}.json"), json_files[0])

            with zf.open(json_file, mode="r") as f:
                return f.read().decode("utf-8")

    base_path = AsyncPath(fixtures_path)

    # Try different file extensions in order of preference
    # Include both case variations for better compatibility with database exports
    file_variants = [
        (base_path / f"{fixture_name}.json", "plain"),
        (base_path / f"{fixture_name.upper()}.json.gz", "gzip"),  # Uppercase first (common for exports)
        (base_path / f"{fixture_name}.json.gz", "gzip"),
        (base_path / f"{fixture_name.upper()}.json.zip", "zip"),
        (base_path / f"{fixture_name}.json.zip", "zip"),
    ]

    for fixture_path, file_type in file_variants:
        if await fixture_path.exists():
            try:
                f_data: str
                if file_type == "plain":
                    async with await fixture_path.open(mode="r", encoding="utf-8") as f:
                        f_data = await f.read()
                elif file_type == "gzip":
                    # Read gzipped files using binary pattern
                    async with await fixture_path.open(mode="rb") as f:  # type: ignore[assignment]
                        compressed_data: bytes = await f.read()  # type: ignore[assignment]

                    # Decompress in thread pool to avoid blocking
                    def _decompress_gzip(data: bytes) -> str:
                        return gzip.decompress(data).decode("utf-8")

                    f_data = await async_(partial(_decompress_gzip, compressed_data))()
                elif file_type == "zip":
                    # Read zipped files in thread pool to avoid blocking
                    f_data = await async_(partial(_read_zip_file, fixture_path, fixture_name))()
                else:
                    continue  # Skip unknown file types

                return decode_json(f_data)
            except (OSError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
                msg = f"Error reading fixture file {fixture_path}: {exc}"
                raise OSError(msg) from exc

    # No valid fixture file found
    msg = f"Could not find the {fixture_name} fixture (tried .json, .json.gz, .json.zip with case variations)"
    raise FileNotFoundError(msg)

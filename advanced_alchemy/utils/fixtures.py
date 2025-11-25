import csv
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
    """Loads JSON or CSV file with the specified fixture name.

    Supports plain files, gzipped files (.json.gz, .csv.gz), and zipped files (.json.zip, .csv.zip).
    The function automatically detects the file format based on file extension and handles
    decompression transparently. JSON files take priority over CSV files. Supports both
    lowercase and uppercase variations for better compatibility with database exports.

    For CSV files, returns a list of dictionaries using csv.DictReader where each row
    becomes a dictionary with column headers as keys. Note that CSV values are always
    strings, unlike JSON which preserves data types.

    Args:
        fixtures_path: The path to look for fixtures. Can be a :class:`pathlib.Path` or
            :class:`anyio.Path` instance.
        fixture_name: The fixture name to load (without file extension).

    Raises:
        FileNotFoundError: If no fixture file is found with any supported extension.
        OSError: If there's an error reading or decompressing the file.
        ValueError: If the JSON content is invalid, or if a zip file doesn't contain
                    the expected JSON/CSV files.
        zipfile.BadZipFile: If the zip file is corrupted.
        gzip.BadGzipFile: If the gzip file is corrupted.
        csv.Error: If the CSV content is malformed.

    Returns:
        Any: The parsed data from the fixture file (JSON data or list of dictionaries from CSV).

    Examples:
        >>> from pathlib import Path
        >>> fixtures_path = Path("./fixtures")

        # Load JSON fixture
        >>> data = open_fixture(fixtures_path, "users")
        # loads users.json, users.json.gz, or users.json.zip
        >>> print(data)
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        # Load CSV fixture
        >>> data = open_fixture(fixtures_path, "states")
        # loads states.csv, states.csv.gz, or states.csv.zip
        >>> print(data)
        [{"abbreviation": "AL", "name": "Alabama"}, {"abbreviation": "AK", "name": "Alaska"}]
    """
    from pathlib import Path

    base_path = Path(fixtures_path)

    # Try different file extensions in order of preference
    # Include both case variations for better compatibility with database exports
    # JSON formats take priority over CSV for backward compatibility
    file_variants = [
        (base_path / f"{fixture_name}.json", "json_plain"),
        (base_path / f"{fixture_name.upper()}.json.gz", "json_gzip"),  # Uppercase first (common for exports)
        (base_path / f"{fixture_name}.json.gz", "json_gzip"),
        (base_path / f"{fixture_name.upper()}.json.zip", "json_zip"),
        (base_path / f"{fixture_name}.json.zip", "json_zip"),
        (base_path / f"{fixture_name}.csv", "csv_plain"),
        (base_path / f"{fixture_name.upper()}.csv.gz", "csv_gzip"),
        (base_path / f"{fixture_name}.csv.gz", "csv_gzip"),
        (base_path / f"{fixture_name.upper()}.csv.zip", "csv_zip"),
        (base_path / f"{fixture_name}.csv.zip", "csv_zip"),
    ]

    for fixture_path, file_type in file_variants:
        if fixture_path.exists():
            try:
                # JSON handling
                if file_type == "json_plain":
                    with fixture_path.open(mode="r", encoding="utf-8") as f:
                        f_data = f.read()
                    return decode_json(f_data)
                if file_type == "json_gzip":
                    with fixture_path.open(mode="rb") as f:
                        compressed_data = f.read()
                    f_data = gzip.decompress(compressed_data).decode("utf-8")
                    return decode_json(f_data)
                if file_type == "json_zip":
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
                    return decode_json(f_data)

                # CSV handling
                if file_type == "csv_plain":
                    with fixture_path.open(mode="r", encoding="utf-8", newline="") as f:
                        reader = csv.DictReader(f)
                        return list(reader)
                if file_type == "csv_gzip":
                    with fixture_path.open(mode="rb") as f:
                        compressed_data = f.read()
                    f_data = gzip.decompress(compressed_data).decode("utf-8")
                    reader = csv.DictReader(f_data.splitlines())
                    return list(reader)
                if file_type == "csv_zip":
                    with zipfile.ZipFile(fixture_path, mode="r") as zf:
                        # Look for CSV file inside zip
                        csv_files = [name for name in zf.namelist() if name.endswith(".csv")]
                        if not csv_files:
                            msg = f"No CSV files found in zip archive: {fixture_path}"
                            raise ValueError(msg)

                        # Use the first CSV file found, or prefer one matching the fixture name
                        csv_file = next((name for name in csv_files if name == f"{fixture_name}.csv"), csv_files[0])

                        with zf.open(csv_file, mode="r") as f:
                            f_data = f.read().decode("utf-8")
                    reader = csv.DictReader(f_data.splitlines())
                    return list(reader)
                continue  # Skip unknown file types
            except (OSError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
                msg = f"Error reading fixture file {fixture_path}: {exc}"
                raise OSError(msg) from exc

    # No valid fixture file found
    msg = f"Could not find the {fixture_name} fixture (tried .json, .json.gz, .json.zip, .csv, .csv.gz, .csv.zip with case variations)"
    raise FileNotFoundError(msg)


def _read_zip_file(path: "AsyncPath", name: str) -> str:
    """Helper function to read JSON zip files."""
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


def _read_csv_zip_file(path: "AsyncPath", name: str) -> "list[dict[str, Any]]":
    """Helper function to read CSV zip files."""
    with zipfile.ZipFile(str(path), mode="r") as zf:
        # Look for CSV file inside zip
        csv_files = [file for file in zf.namelist() if file.endswith(".csv")]
        if not csv_files:
            error_msg = f"No CSV files found in zip archive: {path}"
            raise ValueError(error_msg)

        # Use the first CSV file found, or prefer one matching the fixture name
        csv_file = next((file for file in csv_files if file == f"{name}.csv"), csv_files[0])

        with zf.open(csv_file, mode="r") as f:
            f_data = f.read().decode("utf-8")

    reader = csv.DictReader(f_data.splitlines())
    return list(reader)


async def open_fixture_async(fixtures_path: "Union[Path, AsyncPath]", fixture_name: str) -> Any:
    """Loads JSON or CSV file with the specified fixture name asynchronously.

    Supports plain files, gzipped files (.json.gz, .csv.gz), and zipped files (.json.zip, .csv.zip).
    The function automatically detects the file format based on file extension and handles
    decompression transparently. JSON files take priority over CSV files. Supports both
    lowercase and uppercase variations for better compatibility with database exports.
    For compressed files and CSV parsing, operations are performed in a thread pool to
    avoid blocking the event loop.

    For CSV files, returns a list of dictionaries using csv.DictReader where each row
    becomes a dictionary with column headers as keys. Note that CSV values are always
    strings, unlike JSON which preserves data types.

    Args:
        fixtures_path: The path to look for fixtures. Can be a :class:`pathlib.Path` or
            :class:`anyio.Path` instance.
        fixture_name: The fixture name to load (without file extension).

    Raises:
        MissingDependencyError: If the `anyio` library is not installed.
        FileNotFoundError: If no fixture file is found with any supported extension.
        OSError: If there's an error reading or decompressing the file.
        ValueError: If the JSON content is invalid, or if a zip file doesn't contain
                    the expected JSON/CSV files.
        zipfile.BadZipFile: If the zip file is corrupted.
        gzip.BadGzipFile: If the gzip file is corrupted.
        csv.Error: If the CSV content is malformed.

    Returns:
        Any: The parsed data from the fixture file (JSON data or list of dictionaries from CSV).

    Examples:
        >>> from anyio import Path as AsyncPath
        >>> fixtures_path = AsyncPath("./fixtures")

        # Load JSON fixture
        >>> data = await open_fixture_async(fixtures_path, "users")
        # loads users.json, users.json.gz, or users.json.zip
        >>> print(data)
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        # Load CSV fixture
        >>> data = await open_fixture_async(fixtures_path, "states")
        # loads states.csv, states.csv.gz, or states.csv.zip
        >>> print(data)
        [{"abbreviation": "AL", "name": "Alabama"}, {"abbreviation": "AK", "name": "Alaska"}]
    """
    try:
        from anyio import Path as AsyncPath
    except ImportError as exc:
        msg = "The `anyio` library is required to use this function. Please install it with `pip install anyio`."
        raise MissingDependencyError(msg) from exc

    from advanced_alchemy.utils.sync_tools import async_

    base_path = AsyncPath(fixtures_path)

    # Try different file extensions in order of preference
    # Include both case variations for better compatibility with database exports
    # JSON formats take priority over CSV for backward compatibility
    file_variants = [
        (base_path / f"{fixture_name}.json", "json_plain"),
        (base_path / f"{fixture_name.upper()}.json.gz", "json_gzip"),  # Uppercase first (common for exports)
        (base_path / f"{fixture_name}.json.gz", "json_gzip"),
        (base_path / f"{fixture_name.upper()}.json.zip", "json_zip"),
        (base_path / f"{fixture_name}.json.zip", "json_zip"),
        (base_path / f"{fixture_name}.csv", "csv_plain"),
        (base_path / f"{fixture_name.upper()}.csv.gz", "csv_gzip"),
        (base_path / f"{fixture_name}.csv.gz", "csv_gzip"),
        (base_path / f"{fixture_name.upper()}.csv.zip", "csv_zip"),
        (base_path / f"{fixture_name}.csv.zip", "csv_zip"),
    ]

    for fixture_path, file_type in file_variants:
        if await fixture_path.exists():
            try:
                # JSON handling
                if file_type == "json_plain":
                    async with await fixture_path.open(mode="r", encoding="utf-8") as f:
                        f_data = await f.read()
                    return decode_json(f_data)
                if file_type == "json_gzip":
                    # Read gzipped files using binary pattern
                    async with await fixture_path.open(mode="rb") as f:  # type: ignore[assignment]
                        compressed_json: bytes = await f.read()  # type: ignore[assignment]

                    # Decompress in thread pool to avoid blocking
                    def _decompress_gzip(data: bytes) -> str:
                        return gzip.decompress(data).decode("utf-8")

                    f_data = await async_(partial(_decompress_gzip, compressed_json))()
                    return decode_json(f_data)
                if file_type == "json_zip":
                    # Read zipped files in thread pool to avoid blocking
                    f_data = await async_(partial(_read_zip_file, fixture_path, fixture_name))()
                    return decode_json(f_data)

                # CSV handling
                if file_type == "csv_plain":
                    async with await fixture_path.open(mode="r", encoding="utf-8") as f:
                        f_data = await f.read()

                    # Parse CSV in thread pool to avoid blocking
                    def _parse_csv(data: str) -> "list[dict[str, Any]]":
                        reader = csv.DictReader(data.splitlines())
                        return list(reader)

                    return await async_(partial(_parse_csv, f_data))()
                if file_type == "csv_gzip":
                    async with await fixture_path.open(mode="rb") as f:  # type: ignore[assignment]
                        compressed_csv: bytes = await f.read()  # type: ignore[assignment]

                    def _decompress_and_parse_csv(data: bytes) -> "list[dict[str, Any]]":
                        decompressed = gzip.decompress(data).decode("utf-8")
                        reader = csv.DictReader(decompressed.splitlines())
                        return list(reader)

                    return await async_(partial(_decompress_and_parse_csv, compressed_csv))()
                if file_type == "csv_zip":
                    return await async_(partial(_read_csv_zip_file, fixture_path, fixture_name))()
            except (OSError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
                msg = f"Error reading fixture file {fixture_path}: {exc}"
                raise OSError(msg) from exc

    # No valid fixture file found
    msg = f"Could not find the {fixture_name} fixture (tried .json, .json.gz, .json.zip, .csv, .csv.gz, .csv.zip with case variations)"
    raise FileNotFoundError(msg)

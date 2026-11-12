"""Tests for advanced_alchemy.utils.fixtures module."""

import csv
import gzip
import io
import json
import os
import sys
import tempfile
import zipfile
import zlib
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any, get_args

import pytest

from advanced_alchemy.utils import fixtures as fixtures_module
from advanced_alchemy.utils.fixtures import (
    FixtureCompression,
    FixtureFormat,
    _FixtureFile,
    _FixtureLocator,
    iter_fixture_async,
    iter_fixture_sync,
    open_fixture,
    open_fixture_async,
    open_fixture_sync,
    write_fixture_sync,
)


@pytest.fixture
def sample_data() -> "list[dict[str, Any]]":
    """Sample JSON data for testing."""
    return [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    ]


@pytest.fixture
def sample_csv_data() -> "list[dict[str, str]]":
    """Sample CSV data for testing (note: CSV values are strings)."""
    return [
        {"id": "1", "name": "Alice", "email": "alice@example.com"},
        {"id": "2", "name": "Bob", "email": "bob@example.com"},
        {"id": "3", "name": "Charlie", "email": "charlie@example.com"},
    ]


@pytest.fixture
def temp_fixtures_dir(
    sample_data: "list[dict[str, Any]]", sample_csv_data: "list[dict[str, str]]"
) -> "Generator[Path, None, None]":
    """Create temporary directory with test fixtures in various formats."""
    with tempfile.TemporaryDirectory() as temp_dir:
        fixtures_path = Path(temp_dir)

        # Create plain JSON fixture
        json_file = fixtures_path / "users.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, indent=2)

        # Create gzipped JSON fixture
        gz_file = fixtures_path / "users_gz.json.gz"
        with gzip.open(gz_file, "wt", encoding="utf-8") as f:
            json.dump(sample_data, f, indent=2)

        # Create zipped JSON fixture (single file)
        zip_file = fixtures_path / "users_zip.json.zip"
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("users_zip.json", json.dumps(sample_data, indent=2))

        # Create zipped JSON fixture with multiple files (should pick the first)
        multi_zip_file = fixtures_path / "users_multi.json.zip"
        with zipfile.ZipFile(multi_zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("other.json", json.dumps([{"other": "data"}]))
            zf.writestr("users_multi.json", json.dumps(sample_data, indent=2))

        # Create zipped JSON fixture with preferred name match
        preferred_zip_file = fixtures_path / "users_preferred.json.zip"
        with zipfile.ZipFile(preferred_zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("other.json", json.dumps([{"other": "data"}]))
            zf.writestr("users_preferred.json", json.dumps(sample_data, indent=2))

        # Create empty zip file (should raise error)
        empty_zip_file = fixtures_path / "empty.json.zip"
        with zipfile.ZipFile(empty_zip_file, "w", zipfile.ZIP_DEFLATED):
            pass  # Empty zip

        # Create zip with no JSON files
        no_json_zip_file = fixtures_path / "no_json.json.zip"
        with zipfile.ZipFile(no_json_zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("readme.txt", "No JSON files here")

        # Create plain CSV fixture
        csv_file = fixtures_path / "users_csv.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            if sample_csv_data:
                writer = csv.DictWriter(f, fieldnames=sample_csv_data[0].keys())
                writer.writeheader()
                writer.writerows(sample_csv_data)

        # Create gzipped CSV fixture
        gz_csv_file = fixtures_path / "users_csv_gz.csv.gz"
        with gzip.open(gz_csv_file, "wt", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sample_csv_data[0].keys())
            writer.writeheader()
            writer.writerows(sample_csv_data)

        # Create zipped CSV fixture (single file)
        zip_csv_file = fixtures_path / "users_csv_zip.csv.zip"
        with zipfile.ZipFile(zip_csv_file, "w", zipfile.ZIP_DEFLATED) as zf:
            csv_content = io.StringIO()
            writer = csv.DictWriter(csv_content, fieldnames=sample_csv_data[0].keys())
            writer.writeheader()
            writer.writerows(sample_csv_data)
            zf.writestr("users_csv_zip.csv", csv_content.getvalue())

        # Create zipped CSV fixture with multiple files (should pick matching name)
        multi_zip_csv_file = fixtures_path / "users_csv_multi.csv.zip"
        with zipfile.ZipFile(multi_zip_csv_file, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add a different CSV first
            other_content = io.StringIO()
            other_writer = csv.DictWriter(other_content, fieldnames=["other"])
            other_writer.writeheader()
            other_writer.writerow({"other": "data"})
            zf.writestr("other.csv", other_content.getvalue())

            # Add the actual fixture
            csv_content = io.StringIO()
            writer = csv.DictWriter(csv_content, fieldnames=sample_csv_data[0].keys())
            writer.writeheader()
            writer.writerows(sample_csv_data)
            zf.writestr("users_csv_multi.csv", csv_content.getvalue())

        # Create empty CSV zip file (should raise error)
        empty_csv_zip = fixtures_path / "empty_csv.csv.zip"
        with zipfile.ZipFile(empty_csv_zip, "w", zipfile.ZIP_DEFLATED):
            pass

        # Create zip with no CSV files
        no_csv_zip = fixtures_path / "no_csv.csv.zip"
        with zipfile.ZipFile(no_csv_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("readme.txt", "No CSV files here")

        yield fixtures_path


def _write_fixture(path: Path, text: str) -> None:
    """Write text as a plain, gzip, or zip fixture chosen by the file suffix."""
    data = text.encode("utf-8")
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(data))
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(path.stem, data)
    else:
        path.write_bytes(data)


class TestOpenFixture:
    """Test cases for synchronous open_fixture function."""

    def test_open_plain_json_fixture(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test loading plain JSON fixture."""
        result = open_fixture_sync(temp_fixtures_dir, "users")
        assert result == sample_data

    def test_open_gzipped_fixture(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test loading gzipped JSON fixture."""
        result = open_fixture_sync(temp_fixtures_dir, "users_gz")
        assert result == sample_data

    def test_open_zipped_fixture(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test loading zipped JSON fixture."""
        result = open_fixture_sync(temp_fixtures_dir, "users_zip")
        assert result == sample_data

    def test_open_zipped_fixture_multiple_files(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading zipped JSON fixture with multiple files, should prefer matching name."""
        result = open_fixture_sync(temp_fixtures_dir, "users_multi")
        assert result == sample_data

    def test_open_zipped_fixture_preferred_name(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading zipped JSON fixture prefers file with matching name."""
        result = open_fixture_sync(temp_fixtures_dir, "users_preferred")
        assert result == sample_data

    def test_case_insensitive_support(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test case-insensitive fixture loading (uppercase takes priority for compressed files)."""
        # Create uppercase gzipped file
        uppercase_gz_file = temp_fixtures_dir / "TESTCASE.json.gz"
        with gzip.open(uppercase_gz_file, "wt", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # Test that uppercase is found
        result = open_fixture_sync(temp_fixtures_dir, "testcase")
        assert result == sample_data

        # Create lowercase version and test priority (uppercase should still win)
        lowercase_gz_file = temp_fixtures_dir / "testcase.json.gz"
        lowercase_data = [{"different": "data"}]
        with gzip.open(lowercase_gz_file, "wt", encoding="utf-8") as f:
            json.dump(lowercase_data, f)

        # Should still load uppercase version first
        result = open_fixture_sync(temp_fixtures_dir, "testcase")
        assert result == sample_data  # Original data, not lowercase_data

        # Remove uppercase, should fallback to lowercase
        uppercase_gz_file.unlink()
        result = open_fixture_sync(temp_fixtures_dir, "testcase")
        assert result == lowercase_data

    def test_file_format_priority(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test that plain JSON is preferred over compressed formats."""
        # Create all three formats for the same fixture name
        json_file = temp_fixtures_dir / "priority.json"
        gz_file = temp_fixtures_dir / "priority.json.gz"
        zip_file = temp_fixtures_dir / "priority.json.zip"

        # Different data for each format to test which one is loaded
        plain_data = [{"format": "plain"}]
        gz_data = [{"format": "gzip"}]
        zip_data = [{"format": "zip"}]

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(plain_data, f)

        with gzip.open(gz_file, "wt", encoding="utf-8") as f:
            json.dump(gz_data, f)

        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("priority.json", json.dumps(zip_data))

        # Should load plain JSON first
        result = open_fixture_sync(temp_fixtures_dir, "priority")
        assert result == plain_data

        # Remove plain JSON, should load gzip
        json_file.unlink()
        result = open_fixture_sync(temp_fixtures_dir, "priority")
        assert result == gz_data

        # Remove gzip, should load zip
        gz_file.unlink()
        result = open_fixture_sync(temp_fixtures_dir, "priority")
        assert result == zip_data

    def test_fixture_not_found(self, temp_fixtures_dir: Path) -> None:
        """Test FileNotFoundError when fixture doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc_info:
            open_fixture_sync(temp_fixtures_dir, "nonexistent")

        assert "Could not find the nonexistent fixture" in str(exc_info.value)
        assert (
            "(tried .json, .jsonl, .csv with optional .gz/.zip compression, numbered shards, and case variations)"
            in str(exc_info.value)
        )

    def test_empty_zip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for empty zip file."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture_sync(temp_fixtures_dir, "empty")

        assert "No JSON files found in zip archive" in str(exc_info.value)

    def test_zip_with_no_json_files(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for zip file with no JSON files."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture_sync(temp_fixtures_dir, "no_json")

        assert "No JSON files found in zip archive" in str(exc_info.value)

    def test_corrupted_gzip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for corrupted gzip file."""
        # Create corrupted gzip file
        corrupted_file = temp_fixtures_dir / "corrupted.json.gz"
        with open(corrupted_file, "wb") as f:
            f.write(b"not a gzip file")

        with pytest.raises(OSError) as exc_info:
            open_fixture_sync(temp_fixtures_dir, "corrupted")

        assert "Error reading fixture file" in str(exc_info.value)

    def test_corrupted_zip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for corrupted zip file."""
        # Create corrupted zip file
        corrupted_file = temp_fixtures_dir / "corrupted_zip.json.zip"
        with open(corrupted_file, "wb") as f:
            f.write(b"not a zip file")

        with pytest.raises(OSError) as exc_info:
            open_fixture_sync(temp_fixtures_dir, "corrupted_zip")

        assert "Error reading fixture file" in str(exc_info.value)

    def test_invalid_json_content(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for invalid JSON content."""
        invalid_file = temp_fixtures_dir / "invalid.json"
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json content")

        with pytest.raises(Exception):  # decode_json will raise an appropriate exception
            open_fixture_sync(temp_fixtures_dir, "invalid")

    @pytest.mark.parametrize("fixture_name", ["users", "users_csv"])
    def test_open_fixture_alias_emits_deprecation_warning(self, temp_fixtures_dir: Path, fixture_name: str) -> None:
        """Test deprecated open_fixture alias emits DeprecationWarning and delegates to open_fixture_sync."""
        with pytest.warns(DeprecationWarning, match="Use 'open_fixture_sync' instead") as record:
            result = open_fixture(temp_fixtures_dir, fixture_name)
        assert result == open_fixture_sync(temp_fixtures_dir, fixture_name)
        message = str(record[0].message)
        assert "Call to deprecated function 'open_fixture'" in message
        assert "Deprecated in advanced-alchemy 1.13.0" in message
        assert "removed in 2.0" in message


class TestOpenFixtureCSV:
    """Test cases for CSV fixture loading."""

    def test_open_plain_csv_fixture(self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]") -> None:
        """Test loading plain CSV fixture."""
        result = open_fixture_sync(temp_fixtures_dir, "users_csv")
        assert result == sample_csv_data
        # Verify it's a list of dicts
        assert isinstance(result, list)
        assert all(isinstance(row, dict) for row in result)

    def test_open_gzipped_csv_fixture(self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]") -> None:
        """Test loading gzipped CSV fixture."""
        result = open_fixture_sync(temp_fixtures_dir, "users_csv_gz")
        assert result == sample_csv_data

    def test_open_zipped_csv_fixture(self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]") -> None:
        """Test loading zipped CSV fixture."""
        result = open_fixture_sync(temp_fixtures_dir, "users_csv_zip")
        assert result == sample_csv_data

    def test_open_zipped_csv_fixture_multiple_files(
        self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test loading zipped CSV fixture with multiple files, should prefer matching name."""
        result = open_fixture_sync(temp_fixtures_dir, "users_csv_multi")
        assert result == sample_csv_data

    def test_csv_values_are_strings(self, temp_fixtures_dir: Path) -> None:
        """Test that CSV values are strings (important difference from JSON)."""
        result = open_fixture_sync(temp_fixtures_dir, "users_csv")
        # CSV returns strings, not integers
        assert result[0]["id"] == "1"
        assert isinstance(result[0]["id"], str)

    def test_json_priority_over_csv(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]", sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test that JSON fixtures are loaded before CSV when both exist."""
        # Create both JSON and CSV fixtures with same name
        json_file = temp_fixtures_dir / "priority_format.json"
        csv_file = temp_fixtures_dir / "priority_format.csv"

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sample_csv_data[0].keys())
            writer.writeheader()
            writer.writerows(sample_csv_data)

        # Should load JSON first
        result = open_fixture_sync(temp_fixtures_dir, "priority_format")
        assert result == sample_data  # JSON data, not CSV data

        # Remove JSON, should load CSV
        json_file.unlink()
        result = open_fixture_sync(temp_fixtures_dir, "priority_format")
        assert result == sample_csv_data

    def test_empty_csv_zip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for empty CSV zip file."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture_sync(temp_fixtures_dir, "empty_csv")
        assert "No CSV files found in zip archive" in str(exc_info.value)

    def test_csv_zip_with_no_csv_files(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for zip file with no CSV files."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture_sync(temp_fixtures_dir, "no_csv")
        assert "No CSV files found in zip archive" in str(exc_info.value)

    def test_csv_with_special_characters(self, temp_fixtures_dir: Path) -> None:
        """Test CSV with special characters, quotes, and commas."""
        special_data = [
            {"name": "O'Brien", "description": "Has apostrophe"},
            {"name": "Smith, Jr.", "description": "Has comma"},
            {"name": 'Quote"Test', "description": "Has quote"},
        ]

        csv_file = temp_fixtures_dir / "special.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=special_data[0].keys())
            writer.writeheader()
            writer.writerows(special_data)

        result = open_fixture_sync(temp_fixtures_dir, "special")
        assert result == special_data

    def test_csv_with_unicode(self, temp_fixtures_dir: Path) -> None:
        """Test CSV with Unicode characters."""
        unicode_data = [
            {"name": "François", "city": "Zürich"},
            {"name": "日本", "city": "東京"},
            {"name": "Москва", "city": "Россия"},
        ]

        csv_file = temp_fixtures_dir / "unicode.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=unicode_data[0].keys())
            writer.writeheader()
            writer.writerows(unicode_data)

        result = open_fixture_sync(temp_fixtures_dir, "unicode")
        assert result == unicode_data

    def test_csv_with_embedded_newlines(self, temp_fixtures_dir: Path) -> None:
        """Test CSV with embedded newlines in quoted fields (RFC 4180 compliance)."""
        # This is a critical test - embedded newlines must be preserved
        csv_content = """name,description
Alice,"Line 1
Line 2"
Bob,"Simple description"
Charlie,"Multiple
embedded
newlines"
"""
        csv_file = temp_fixtures_dir / "embedded_newlines.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = open_fixture_sync(temp_fixtures_dir, "embedded_newlines")
        assert len(result) == 3
        assert result[0]["name"] == "Alice"
        assert result[0]["description"] == "Line 1\nLine 2"  # Newline must be preserved
        assert result[1]["description"] == "Simple description"
        assert result[2]["description"] == "Multiple\nembedded\nnewlines"

    def test_csv_with_embedded_newlines_gzip(self, temp_fixtures_dir: Path) -> None:
        """Test gzipped CSV with embedded newlines in quoted fields."""
        csv_content = """name,description
Alice,"Line 1
Line 2"
"""
        gz_file = temp_fixtures_dir / "embedded_newlines_gz.csv.gz"
        with gzip.open(gz_file, "wt", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = open_fixture_sync(temp_fixtures_dir, "embedded_newlines_gz")
        assert len(result) == 1
        assert result[0]["description"] == "Line 1\nLine 2"  # Newline must be preserved

    def test_csv_with_embedded_newlines_zip(self, temp_fixtures_dir: Path) -> None:
        """Test zipped CSV with embedded newlines in quoted fields."""
        csv_content = """name,description
Alice,"Line 1
Line 2"
"""
        zip_file = temp_fixtures_dir / "embedded_newlines_zip.csv.zip"
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("embedded_newlines_zip.csv", csv_content)

        result = open_fixture_sync(temp_fixtures_dir, "embedded_newlines_zip")
        assert len(result) == 1
        assert result[0]["description"] == "Line 1\nLine 2"  # Newline must be preserved

    def test_csv_with_utf8_bom(self, temp_fixtures_dir: Path) -> None:
        """Test CSV with UTF-8 BOM (common in Excel exports)."""
        # UTF-8 BOM is \ufeff at the start of the file
        csv_content = "\ufeffname,value\nAlice,1\nBob,2\n"
        csv_file = temp_fixtures_dir / "bom.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = open_fixture_sync(temp_fixtures_dir, "bom")
        assert len(result) == 2
        # BOM should be stripped, so first key should be "name" not "\ufeffname"
        assert "name" in result[0]
        assert "\ufeffname" not in result[0]
        assert result[0]["name"] == "Alice"

    def test_csv_with_utf8_bom_gzip(self, temp_fixtures_dir: Path) -> None:
        """Test gzipped CSV with UTF-8 BOM."""
        csv_content = "\ufeffname,value\nAlice,1\n"
        # Write as bytes to preserve BOM
        gz_file = temp_fixtures_dir / "bom_gz.csv.gz"
        with gzip.open(gz_file, "wb") as f:
            f.write(csv_content.encode("utf-8"))

        result = open_fixture_sync(temp_fixtures_dir, "bom_gz")
        assert len(result) == 1
        assert "name" in result[0]
        assert "\ufeffname" not in result[0]

    def test_csv_with_utf8_bom_zip(self, temp_fixtures_dir: Path) -> None:
        """Test zipped CSV with UTF-8 BOM."""
        csv_content = "\ufeffname,value\nAlice,1\n"
        zip_file = temp_fixtures_dir / "bom_zip.csv.zip"
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write as bytes to preserve BOM
            zf.writestr("bom_zip.csv", csv_content.encode("utf-8"))

        result = open_fixture_sync(temp_fixtures_dir, "bom_zip")
        assert len(result) == 1
        assert "name" in result[0]
        assert "\ufeffname" not in result[0]

    def test_csv_empty_data_rows(self, temp_fixtures_dir: Path) -> None:
        """Test CSV with headers only (no data rows)."""
        csv_content = "name,email,age\n"
        csv_file = temp_fixtures_dir / "headers_only.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = open_fixture_sync(temp_fixtures_dir, "headers_only")
        assert result == []  # Empty list, no rows

    def test_uppercase_plain_csv(self, temp_fixtures_dir: Path) -> None:
        """Test loading uppercase plain CSV file."""
        csv_content = "name,value\nUPPER,1\n"
        csv_file = temp_fixtures_dir / "UPPERTEST.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        # Should find UPPERTEST.csv when searching for "uppertest"
        result = open_fixture_sync(temp_fixtures_dir, "uppertest")
        assert len(result) == 1
        assert result[0]["name"] == "UPPER"


class TestOpenFixtureAsync:
    """Test cases for asynchronous open_fixture_async function."""

    @pytest.mark.asyncio
    async def test_open_plain_json_fixture_async(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading plain JSON fixture asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users")
        assert result == sample_data

    @pytest.mark.asyncio
    async def test_open_gzipped_fixture_async(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading gzipped JSON fixture asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users_gz")
        assert result == sample_data

    @pytest.mark.asyncio
    async def test_open_zipped_fixture_async(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading zipped JSON fixture asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users_zip")
        assert result == sample_data

    @pytest.mark.asyncio
    async def test_open_zipped_fixture_multiple_files_async(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading zipped JSON fixture with multiple files asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users_multi")
        assert result == sample_data

    @pytest.mark.asyncio
    async def test_case_insensitive_support_async(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test case-insensitive fixture loading asynchronously."""
        # Create uppercase gzipped file
        uppercase_gz_file = temp_fixtures_dir / "ASYNCCASE.json.gz"
        with gzip.open(uppercase_gz_file, "wt", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # Test that uppercase is found
        result = await open_fixture_async(temp_fixtures_dir, "asynccase")
        assert result == sample_data

    @pytest.mark.asyncio
    async def test_file_format_priority_async(self, temp_fixtures_dir: Path) -> None:
        """Test that plain JSON is preferred over compressed formats in async version."""
        # Create all three formats for the same fixture name
        json_file = temp_fixtures_dir / "priority_async.json"
        gz_file = temp_fixtures_dir / "priority_async.json.gz"
        zip_file = temp_fixtures_dir / "priority_async.json.zip"

        # Different data for each format to test which one is loaded
        plain_data = [{"format": "plain"}]
        gz_data = [{"format": "gzip"}]
        zip_data = [{"format": "zip"}]

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(plain_data, f)

        with gzip.open(gz_file, "wt", encoding="utf-8") as f:
            json.dump(gz_data, f)

        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("priority_async.json", json.dumps(zip_data))

        # Should load plain JSON first
        result = await open_fixture_async(temp_fixtures_dir, "priority_async")
        assert result == plain_data

    @pytest.mark.asyncio
    async def test_fixture_not_found_async(self, temp_fixtures_dir: Path) -> None:
        """Test FileNotFoundError when fixture doesn't exist in async version."""
        with pytest.raises(FileNotFoundError) as exc_info:
            await open_fixture_async(temp_fixtures_dir, "nonexistent")

        assert "Could not find the nonexistent fixture" in str(exc_info.value)
        assert (
            "(tried .json, .jsonl, .csv with optional .gz/.zip compression, numbered shards, and case variations)"
            in str(exc_info.value)
        )

    @pytest.mark.asyncio
    async def test_empty_zip_file_async(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for empty zip file in async version."""
        with pytest.raises(ValueError) as exc_info:
            await open_fixture_async(temp_fixtures_dir, "empty")

        assert "No JSON files found in zip archive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_corrupted_gzip_file_async(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for corrupted gzip file in async version."""
        # Create corrupted gzip file
        corrupted_file = temp_fixtures_dir / "corrupted_async.json.gz"
        with open(corrupted_file, "wb") as f:
            f.write(b"not a gzip file")

        with pytest.raises(OSError) as exc_info:
            await open_fixture_async(temp_fixtures_dir, "corrupted_async")

        assert "Error reading fixture file" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_anyio_dependency(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]", monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test async fixture loaders succeed without importing anyio."""
        monkeypatch.setitem(sys.modules, "anyio", None)
        assert await open_fixture_async(temp_fixtures_dir, "users") == sample_data
        batches = [batch async for batch in iter_fixture_async(temp_fixtures_dir, "users", batch_size=2)]
        assert batches == [sample_data[:2], sample_data[2:]]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path_kind", ["pathlib", "anyio"])
    async def test_open_jsonl_async(self, tmp_path: Path, path_kind: str) -> None:
        """Test open_fixture_async loads JSONL fixtures from both pathlib.Path and anyio.Path."""
        _write_fixture(tmp_path / "users.jsonl.gz", '{"id": 1}\n{"id": 2}\n')
        path = pytest.importorskip("anyio").Path(tmp_path) if path_kind == "anyio" else tmp_path
        assert await open_fixture_async(path, "users") == [{"id": 1}, {"id": 2}]

    # Async CSV Tests
    @pytest.mark.asyncio
    async def test_open_plain_csv_fixture_async(
        self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test loading plain CSV fixture asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users_csv")
        assert result == sample_csv_data

    @pytest.mark.asyncio
    async def test_open_gzipped_csv_fixture_async(
        self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test loading gzipped CSV fixture asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users_csv_gz")
        assert result == sample_csv_data

    @pytest.mark.asyncio
    async def test_open_zipped_csv_fixture_async(
        self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test loading zipped CSV fixture asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users_csv_zip")
        assert result == sample_csv_data

    @pytest.mark.asyncio
    async def test_open_zipped_csv_fixture_multiple_files_async(
        self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test loading zipped CSV fixture with multiple files asynchronously."""
        result = await open_fixture_async(temp_fixtures_dir, "users_csv_multi")
        assert result == sample_csv_data

    @pytest.mark.asyncio
    async def test_json_priority_over_csv_async(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]", sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test that JSON fixtures are loaded before CSV when both exist in async version."""
        json_file = temp_fixtures_dir / "priority_async.json"
        csv_file = temp_fixtures_dir / "priority_async.csv"

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sample_csv_data[0].keys())
            writer.writeheader()
            writer.writerows(sample_csv_data)

        result = await open_fixture_async(temp_fixtures_dir, "priority_async")
        assert result == sample_data

    @pytest.mark.asyncio
    async def test_empty_csv_zip_file_async(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for empty CSV zip file in async version."""
        with pytest.raises(ValueError) as exc_info:
            await open_fixture_async(temp_fixtures_dir, "empty_csv")
        assert "No CSV files found in zip archive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_csv_with_embedded_newlines_async(self, temp_fixtures_dir: Path) -> None:
        """Test async CSV loading with embedded newlines in quoted fields."""
        csv_content = """name,description
Alice,"Line 1
Line 2"
"""
        csv_file = temp_fixtures_dir / "embedded_async.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = await open_fixture_async(temp_fixtures_dir, "embedded_async")
        assert len(result) == 1
        assert result[0]["description"] == "Line 1\nLine 2"

    @pytest.mark.asyncio
    async def test_csv_with_embedded_newlines_gzip_async(self, temp_fixtures_dir: Path) -> None:
        """Test async gzipped CSV loading with embedded newlines."""
        csv_content = """name,description
Alice,"Line 1
Line 2"
"""
        gz_file = temp_fixtures_dir / "embedded_gz_async.csv.gz"
        with gzip.open(gz_file, "wt", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = await open_fixture_async(temp_fixtures_dir, "embedded_gz_async")
        assert len(result) == 1
        assert result[0]["description"] == "Line 1\nLine 2"

    @pytest.mark.asyncio
    async def test_csv_with_embedded_newlines_zip_async(self, temp_fixtures_dir: Path) -> None:
        """Test async zipped CSV loading with embedded newlines."""
        csv_content = """name,description
Alice,"Line 1
Line 2"
"""
        zip_file = temp_fixtures_dir / "embedded_zip_async.csv.zip"
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("embedded_zip_async.csv", csv_content)

        result = await open_fixture_async(temp_fixtures_dir, "embedded_zip_async")
        assert len(result) == 1
        assert result[0]["description"] == "Line 1\nLine 2"

    @pytest.mark.asyncio
    async def test_csv_with_utf8_bom_async(self, temp_fixtures_dir: Path) -> None:
        """Test async CSV loading with UTF-8 BOM."""
        csv_content = "\ufeffname,value\nAlice,1\n"
        csv_file = temp_fixtures_dir / "bom_async.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = await open_fixture_async(temp_fixtures_dir, "bom_async")
        assert len(result) == 1
        assert "name" in result[0]
        assert "\ufeffname" not in result[0]

    @pytest.mark.asyncio
    async def test_concurrent_csv_reads(self, temp_fixtures_dir: Path) -> None:
        """Test concurrent async reads of the same CSV fixture."""
        import asyncio

        csv_content = "name,value\nAlice,1\nBob,2\n"
        csv_file = temp_fixtures_dir / "concurrent.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        # Perform 5 concurrent reads
        results = await asyncio.gather(*(open_fixture_async(temp_fixtures_dir, "concurrent") for _ in range(5)))

        # All results should be identical
        assert len(results) == 5
        for result in results:
            assert len(result) == 2
            assert result[0]["name"] == "Alice"
            assert result[1]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_uppercase_plain_csv_async(self, temp_fixtures_dir: Path) -> None:
        """Test async loading of uppercase plain CSV file."""
        csv_content = "name,value\nUPPER,1\n"
        csv_file = temp_fixtures_dir / "UPPERASYNC.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = await open_fixture_async(temp_fixtures_dir, "upperasync")
        assert len(result) == 1
        assert result[0]["name"] == "UPPER"


class TestIntegration:
    """Integration tests to ensure compatibility with existing usage patterns."""

    def test_backward_compatibility_sync(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test that existing sync code still works as expected."""
        # This mirrors the usage pattern in test_sqlquery_service.py
        fixture_data = open_fixture_sync(temp_fixtures_dir, "users")
        assert fixture_data == sample_data
        assert len(fixture_data) == 3
        assert fixture_data[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_backward_compatibility_async(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test that existing async code still works as expected."""
        # This mirrors the usage pattern in test_sqlquery_service.py
        fixture_data = await open_fixture_async(temp_fixtures_dir, "users")
        assert fixture_data == sample_data
        assert len(fixture_data) == 3
        assert fixture_data[0]["name"] == "Alice"

    def test_compression_efficiency(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test that compressed fixtures are actually smaller than plain JSON."""
        # Create a larger dataset for meaningful compression
        large_data = sample_data * 100  # Repeat the data 100 times

        # Create plain JSON
        json_file = temp_fixtures_dir / "large.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(large_data, f, indent=2)

        # Create gzipped version
        gz_file = temp_fixtures_dir / "large.json.gz"
        with gzip.open(gz_file, "wt", encoding="utf-8") as f:
            json.dump(large_data, f, indent=2)

        # Create zipped version
        zip_file = temp_fixtures_dir / "large.json.zip"
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("large.json", json.dumps(large_data, indent=2))

        # Check file sizes
        json_size = json_file.stat().st_size
        gz_size = gz_file.stat().st_size
        zip_size = zip_file.stat().st_size

        # Compressed versions should be smaller
        assert gz_size < json_size
        assert zip_size < json_size

        # Verify all formats load the same data
        json_data = open_fixture_sync(temp_fixtures_dir, "large")

        # Remove plain JSON to force loading compressed versions
        json_file.unlink()
        gz_data = open_fixture_sync(temp_fixtures_dir, "large")

        gz_file.unlink()
        zip_data = open_fixture_sync(temp_fixtures_dir, "large")

        assert json_data == gz_data == zip_data == large_data

    def test_csv_fixture_integration_sync(self, temp_fixtures_dir: Path) -> None:
        """Test CSV fixture loading in a realistic scenario."""
        # Create a CSV fixture similar to real-world usage
        states_data = [
            {"abbreviation": "AL", "name": "Alabama"},
            {"abbreviation": "AK", "name": "Alaska"},
            {"abbreviation": "AZ", "name": "Arizona"},
        ]

        csv_file = temp_fixtures_dir / "us_state_lookup.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["abbreviation", "name"])
            writer.writeheader()
            writer.writerows(states_data)

        # Load fixture
        fixture_data = open_fixture_sync(temp_fixtures_dir, "us_state_lookup")
        assert fixture_data == states_data
        assert len(fixture_data) == 3
        assert fixture_data[0]["name"] == "Alabama"
        assert fixture_data[0]["abbreviation"] == "AL"

    @pytest.mark.asyncio
    async def test_csv_fixture_integration_async(self, temp_fixtures_dir: Path) -> None:
        """Test CSV fixture loading in a realistic async scenario."""
        states_data = [
            {"abbreviation": "CA", "name": "California"},
            {"abbreviation": "TX", "name": "Texas"},
        ]

        csv_file = temp_fixtures_dir / "states_async.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["abbreviation", "name"])
            writer.writeheader()
            writer.writerows(states_data)

        fixture_data = await open_fixture_async(temp_fixtures_dir, "states_async")
        assert fixture_data == states_data
        assert len(fixture_data) == 2

    def test_mixed_format_directory(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]", sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test loading from directory with mixed JSON and CSV fixtures."""
        # Create JSON fixture
        json_file = temp_fixtures_dir / "data_json.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # Create CSV fixture
        csv_file = temp_fixtures_dir / "data_csv.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sample_csv_data[0].keys())
            writer.writeheader()
            writer.writerows(sample_csv_data)

        # Both should load correctly
        json_result = open_fixture_sync(temp_fixtures_dir, "data_json")
        csv_result = open_fixture_sync(temp_fixtures_dir, "data_csv")

        assert json_result == sample_data
        assert csv_result == sample_csv_data

    def test_public_exports(self) -> None:
        """Test public exports and type aliases exposed by advanced_alchemy.utils.fixtures."""
        assert fixtures_module.__all__ == (
            "FixtureCompression",
            "FixtureFormat",
            "iter_fixture_async",
            "iter_fixture_sync",
            "open_fixture",
            "open_fixture_async",
            "open_fixture_sync",
            "write_fixture_sync",
        )
        assert get_args(FixtureFormat) == ("json", "jsonl", "csv")
        assert get_args(FixtureCompression) == ("gzip", "zip")


class TestOpenFixtureJSONL:
    """Test cases for JSONL fixture loading and streaming reads via open_fixture_sync."""

    @pytest.mark.parametrize(
        "file_name",
        [
            "users.jsonl",
            "users.jsonl.gz",
            "users.jsonl.zip",
            "USERS.jsonl.gz",
            "USERS.jsonl.zip",
        ],
    )
    def test_open_jsonl_variants(self, tmp_path: Path, file_name: str) -> None:
        """Test loading plain, gzipped, and zipped JSONL fixtures including case variants."""
        _write_fixture(tmp_path / file_name, '{"id": 1}\n{"id": 2}\n')
        assert open_fixture_sync(tmp_path, "users") == [{"id": 1}, {"id": 2}]

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("{}\n\n{}\n  \n", [{}, {}]),
            ('{"a": 1}\r\n{"a": 2}\r\n', [{"a": 1}, {"a": 2}]),
            ('\ufeff{"id": 1}\n', [{"id": 1}]),
            ('1\n"two"\nnull\n', [1, "two", None]),
            ("", []),
            ('{"id": 1}', [{"id": 1}]),
        ],
    )
    def test_open_jsonl_line_handling(self, tmp_path: Path, content: str, expected: "list[Any]") -> None:
        """Test blank lines, CRLF endings, UTF-8 BOM, scalar JSON values, empty files, and missing trailing newline."""
        _write_fixture(tmp_path / "users.jsonl", content)
        assert open_fixture_sync(tmp_path, "users") == expected

    @pytest.mark.parametrize("file_name", ["users.json", "users.json.gz"])
    def test_open_json_with_bom(self, tmp_path: Path, file_name: str) -> None:
        """Test loading JSON fixtures with a UTF-8 BOM."""
        _write_fixture(tmp_path / file_name, "\ufeff[1, 2]")
        assert open_fixture_sync(tmp_path, "users") == [1, 2]

    def test_open_unsharded_json_returns_non_array_value(self, tmp_path: Path) -> None:
        """Test unsharded JSON files return non-array top-level values unchanged."""
        _write_fixture(tmp_path / "config.json", '{"a": 1}')
        assert open_fixture_sync(tmp_path, "config") == {"a": 1}

    def test_jsonl_malformed_line_raises_value_error(self, tmp_path: Path) -> None:
        """Test malformed JSONL line raises ValueError with path and 1-based line number."""
        fixture_path = tmp_path / "users.jsonl"
        _write_fixture(fixture_path, '{"id": 1}\n{bad\n')
        with pytest.raises(ValueError) as exc_info:
            open_fixture_sync(tmp_path, "users")
        assert "at line 2" in str(exc_info.value)
        assert str(fixture_path) in str(exc_info.value)

    @pytest.mark.parametrize(
        ("files", "expected"),
        [
            (
                {"users.json": '[{"src": "json"}]', "users.jsonl": '{"src": "jsonl"}\n', "users.csv": "src\ncsv\n"},
                [{"src": "json"}],
            ),
            (
                {"users.jsonl.gz": '{"src": "jsonl"}\n', "users.csv": "src\ncsv\n"},
                [{"src": "jsonl"}],
            ),
            (
                {"users.csv": "src\ncsv\n"},
                [{"src": "csv"}],
            ),
        ],
    )
    def test_jsonl_format_priority(
        self, tmp_path: Path, files: "dict[str, str]", expected: "list[dict[str, str]]"
    ) -> None:
        """Test format resolution priority is json > jsonl > csv."""
        for name, content in files.items():
            _write_fixture(tmp_path / name, content)
        assert open_fixture_sync(tmp_path, "users") == expected

    def test_jsonl_zip_prefers_matching_member(self, tmp_path: Path) -> None:
        """Test zipped JSONL prefers the member matching the fixture name."""
        zip_path = tmp_path / "users.jsonl.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("other.jsonl", '{"src": "other"}\n')
            archive.writestr("users.jsonl", '{"src": "users"}\n')
        assert open_fixture_sync(tmp_path, "users") == [{"src": "users"}]

    @pytest.mark.parametrize("member", ["readme.txt", "users.json"])
    def test_jsonl_zip_without_jsonl_member_raises(self, tmp_path: Path, member: str) -> None:
        """Test zipped JSONL without any .jsonl member raises ValueError."""
        zip_path = tmp_path / "users.jsonl.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member, "content")
        with pytest.raises(ValueError, match="No JSONL files found in zip archive"):
            open_fixture_sync(tmp_path, "users")

    @pytest.mark.parametrize("corruption", ["truncated", "deflate-body"])
    def test_corrupt_jsonl_gzip_raises_os_error(self, tmp_path: Path, corruption: str) -> None:
        """Test truncated and deflate-corrupted gzipped JSONL files raise OSError."""
        data = bytearray(gzip.compress(b'{"id": 1}\n' * 1000))
        if corruption == "truncated":
            corrupt_bytes = bytes(data[: len(data) // 2])
        else:
            data[10] |= 0x06
            corrupt_bytes = bytes(data)
        (tmp_path / "users.jsonl.gz").write_bytes(corrupt_bytes)
        with pytest.raises(OSError, match="Error reading fixture file") as exc_info:
            open_fixture_sync(tmp_path, "users")
        if corruption == "deflate-body":
            assert isinstance(exc_info.value.__cause__, zlib.error)

    @pytest.mark.parametrize("file_name", ["users.json.gz", "users.jsonl.gz", "users.jsonl.zip"])
    def test_reader_streams_without_whole_file_decompression(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, file_name: str
    ) -> None:
        """Test fixture loading streams without calling gzip.decompress or Path.read_bytes."""
        content = '[{"id": 1}]' if file_name == "users.json.gz" else '{"id": 1}\n'
        _write_fixture(tmp_path / file_name, content)

        def _raise(*args: Any, **kwargs: Any) -> Any:
            msg = "whole-file read"
            raise AssertionError(msg)

        monkeypatch.setattr(gzip, "decompress", _raise)
        monkeypatch.setattr(Path, "read_bytes", _raise)
        assert open_fixture_sync(tmp_path, "users") == [{"id": 1}]


class TestFixtureShards:
    """Test cases for numbered shard discovery, validation, and concatenation."""

    def test_open_sharded_jsonl_gzip(self, tmp_path: Path) -> None:
        """Test loading numbered gzipped JSONL shards returns concatenated records."""
        _write_fixture(tmp_path / "users.001.jsonl.gz", '{"id": 1}\n{"id": 2}\n{"id": 3}\n')
        _write_fixture(tmp_path / "users.002.jsonl.gz", '{"id": 4}\n{"id": 5}\n')
        assert open_fixture_sync(tmp_path, "users") == [
            {"id": 1},
            {"id": 2},
            {"id": 3},
            {"id": 4},
            {"id": 5},
        ]

    @pytest.mark.parametrize(
        ("files", "expected"),
        [
            (
                {"users.001.jsonl.gz": '{"id": 1}\n', "users.002.jsonl": '{"id": 2}\n'},
                [{"id": 1}, {"id": 2}],
            ),
            (
                {"USERS.001.jsonl.zip": '{"id": 1}\n', "users.002.jsonl.gz": '{"id": 2}\n'},
                [{"id": 1}, {"id": 2}],
            ),
            (
                {"users.1.jsonl": '{"id": 1}\n', "users.02.jsonl": '{"id": 2}\n', "users.003.jsonl": '{"id": 3}\n'},
                [{"id": 1}, {"id": 2}, {"id": 3}],
            ),
            (
                {"users.001.json": '[{"id": 1}]', "users.002.json.gz": '[{"id": 2}, {"id": 3}]'},
                [{"id": 1}, {"id": 2}, {"id": 3}],
            ),
            (
                {"users.001.csv": "id\n1\n", "users.002.csv.zip": "id\n2\n"},
                [{"id": "1"}, {"id": "2"}],
            ),
        ],
    )
    def test_open_shard_layouts(
        self, tmp_path: Path, files: "dict[str, str]", expected: "list[dict[str, Any]]"
    ) -> None:
        """Test mixed compression, case variants, variable digit widths, and formats across shards."""
        for name, content in files.items():
            _write_fixture(tmp_path / name, content)
        assert open_fixture_sync(tmp_path, "users") == expected

    def test_open_shards_in_numeric_order(self, tmp_path: Path) -> None:
        """Test shards are ordered numerically so shard 10 follows shard 9."""
        files = {f"users.{i}.jsonl": f'{{"id": {i}}}\n' for i in range(1, 11)}
        for name, content in files.items():
            _write_fixture(tmp_path / name, content)
        assert open_fixture_sync(tmp_path, "users") == [{"id": i} for i in range(1, 11)]

    @pytest.mark.parametrize(
        ("files", "message", "named"),
        [
            (
                {"users.json": "[]", "users.001.json": "[]"},
                "has both an unsharded file and numbered shards",
                ("users.json", "users.001.json"),
            ),
            (
                {"users.001.jsonl": "{}\n", "users.003.jsonl": "{}\n"},
                "is missing shard index(es) 2",
                ("users.001.jsonl", "users.003.jsonl"),
            ),
            (
                {"users.000.jsonl": "{}\n", "users.001.jsonl": "{}\n"},
                "shard indexes start at 1, found index 0",
                ("users.000.jsonl",),
            ),
            (
                {"users.1.json": "[]", "users.001.json.gz": "[]"},
                "has multiple shards with index 1",
                ("users.1.json", "users.001.json.gz"),
            ),
            (
                {"users.001.json": '{"a": 1}'},
                "must contain a JSON array, got dict",
                ("users.001.json",),
            ),
        ],
    )
    def test_shard_validation_errors(
        self, tmp_path: Path, files: "dict[str, str]", message: str, named: "tuple[str, ...]"
    ) -> None:
        """Test invalid shard layouts raise ValueError naming the fixture and offending paths."""
        for name, content in files.items():
            _write_fixture(tmp_path / name, content)
        with pytest.raises(ValueError) as exc_info:
            open_fixture_sync(tmp_path, "users")
        exc_text = str(exc_info.value)
        assert "Fixture 'users'" in exc_text
        assert message in exc_text
        assert all(name in exc_text for name in named)

    @pytest.mark.parametrize(
        ("files", "expected"),
        [
            (
                {"users.json": '[{"src": "json"}]', "users.001.csv": "src\ncsv\n"},
                [{"src": "json"}],
            ),
            (
                {"users.jsonl": '{"src": "jsonl"}\n', "users.001.csv": "src\na\n", "users.003.csv": "src\nb\n"},
                [{"src": "jsonl"}],
            ),
        ],
    )
    def test_lower_priority_shards_are_ignored(
        self, tmp_path: Path, files: "dict[str, str]", expected: "list[dict[str, str]]"
    ) -> None:
        """Test shards of a lower-priority format are ignored even when invalid."""
        for name, content in files.items():
            _write_fixture(tmp_path / name, content)
        assert open_fixture_sync(tmp_path, "users") == expected

    def test_shard_name_is_matched_literally(self, tmp_path: Path) -> None:
        """Test regex metacharacters in fixture_name are matched literally."""
        _write_fixture(tmp_path / "a.b+c.001.jsonl", '{"id": 1}\n')
        _write_fixture(tmp_path / "aXbbc.002.jsonl", '{"id": 2}\n')
        _write_fixture(tmp_path / "a.bbc.002.jsonl", '{"id": 3}\n')
        assert open_fixture_sync(tmp_path, "a.b+c") == [{"id": 1}]

    def test_non_shard_entries_are_ignored(self, tmp_path: Path) -> None:
        """Test directories and files with extra suffixes do not count as shards."""
        (tmp_path / "users.001.jsonl").mkdir()
        _write_fixture(tmp_path / "users.001.jsonl.bak", '{"id": 9}\n')
        _write_fixture(tmp_path / "users.jsonl", '{"id": 1}\n')
        assert open_fixture_sync(tmp_path, "users") == [{"id": 1}]

    def test_hard_linked_shard_names_load_once(self, tmp_path: Path) -> None:
        """Test hard-linked case-variant shard names are deduplicated by inode."""
        _write_fixture(tmp_path / "users.001.jsonl", '{"id": 1}\n')
        os.link(tmp_path / "users.001.jsonl", tmp_path / "USERS.001.jsonl")
        _write_fixture(tmp_path / "users.002.jsonl", '{"id": 2}\n')
        assert open_fixture_sync(tmp_path, "users") == [{"id": 1}, {"id": 2}]

    def test_hard_linked_unsharded_name_reported_once(self, tmp_path: Path) -> None:
        """Test hard-linked unsharded case variants are reported once in conflict errors."""
        _write_fixture(tmp_path / "users.json.gz", "[]")
        os.link(tmp_path / "users.json.gz", tmp_path / "USERS.json.gz")
        _write_fixture(tmp_path / "users.001.json", "[]")
        with pytest.raises(ValueError) as exc_info:
            open_fixture_sync(tmp_path, "users")
        assert str(exc_info.value).count(".json.gz") == 1

    def test_missing_fixtures_directory(self, tmp_path: Path) -> None:
        """Test missing fixtures directory raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Could not find the users fixture"):
            open_fixture_sync(tmp_path / "missing", "users")

    @pytest.mark.asyncio
    async def test_open_sharded_async(self, tmp_path: Path) -> None:
        """Test open_fixture_async loads numbered shards in order."""
        _write_fixture(tmp_path / "users.001.jsonl.gz", '{"id": 1}\n{"id": 2}\n{"id": 3}\n')
        _write_fixture(tmp_path / "users.002.jsonl.gz", '{"id": 4}\n{"id": 5}\n')
        assert await open_fixture_async(tmp_path, "users") == [
            {"id": 1},
            {"id": 2},
            {"id": 3},
            {"id": 4},
            {"id": 5},
        ]


class TestIterFixture:
    """Test cases for iter_fixture_sync and iter_fixture_async batch streaming."""

    @pytest.fixture
    def sharded_users(self, tmp_path: Path) -> Path:
        """Create two numbered shards spanning gzipped and plain JSONL."""
        _write_fixture(tmp_path / "users.001.jsonl.gz", '{"id": 1}\n{"id": 2}\n{"id": 3}\n')
        _write_fixture(tmp_path / "users.002.jsonl", '{"id": 4}\n{"id": 5}\n')
        return tmp_path

    @pytest.mark.parametrize(
        ("batch_size", "expected_sizes"),
        [
            (4, [4, 1]),
            (5, [5]),
            (2, [2, 2, 1]),
            (1, [1, 1, 1, 1, 1]),
            (1000, [5]),
        ],
    )
    def test_iter_fixture_sync_batches(self, sharded_users: Path, batch_size: int, expected_sizes: "list[int]") -> None:
        """Test iter_fixture_sync yields non-empty batches of at most batch_size across shards."""
        assert [
            len(batch) for batch in iter_fixture_sync(sharded_users, "users", batch_size=batch_size)
        ] == expected_sizes

    def test_iter_fixture_sync_preserves_order(self, sharded_users: Path) -> None:
        """Test iter_fixture_sync preserves record order across shard boundaries."""
        assert list(iter_fixture_sync(sharded_users, "users", batch_size=4)) == [
            [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
            [{"id": 5}],
        ]

    @pytest.mark.asyncio
    async def test_iter_fixture_async_batches(self, sharded_users: Path) -> None:
        """Test iter_fixture_async yields ordered batches across shards."""
        batches = [batch async for batch in iter_fixture_async(sharded_users, "users", batch_size=4)]
        assert batches == [
            [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
            [{"id": 5}],
        ]

    @pytest.mark.parametrize(
        ("file_name", "content", "batch_size", "expected"),
        [
            (
                "users.json",
                '[{"id": 1}, {"id": 2}, {"id": 3}]',
                2,
                [[{"id": 1}, {"id": 2}], [{"id": 3}]],
            ),
            (
                "users.csv.zip",
                "id\n1\n2\n3\n",
                2,
                [[{"id": "1"}, {"id": "2"}], [{"id": "3"}]],
            ),
        ],
    )
    def test_iter_fixture_sync_formats(
        self, tmp_path: Path, file_name: str, content: str, batch_size: int, expected: "list[list[dict[str, Any]]]"
    ) -> None:
        """Test iter_fixture_sync streams JSON array and compressed CSV fixtures."""
        _write_fixture(tmp_path / file_name, content)
        assert list(iter_fixture_sync(tmp_path, "users", batch_size=batch_size)) == expected

    @pytest.mark.parametrize(
        ("file_name", "content"),
        [
            ("users.jsonl", ""),
            ("users.json", "[]"),
            ("users.csv", "id\n"),
        ],
    )
    def test_iter_fixture_empty_yields_nothing(self, tmp_path: Path, file_name: str, content: str) -> None:
        """Test iter_fixture_sync yields no batches for empty fixtures."""
        _write_fixture(tmp_path / file_name, content)
        assert list(iter_fixture_sync(tmp_path, "users")) == []

    @pytest.mark.parametrize("batch_size", [0, -1])
    def test_iter_fixture_sync_rejects_batch_size(self, tmp_path: Path, batch_size: int) -> None:
        """Test iter_fixture_sync validates batch_size eagerly at call time."""
        _write_fixture(tmp_path / "users.jsonl", '{"id": 1}\n')
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            iter_fixture_sync(tmp_path, "users", batch_size=batch_size)

    @pytest.mark.asyncio
    async def test_iter_fixture_async_rejects_batch_size(self, tmp_path: Path) -> None:
        """Test iter_fixture_async rejects non-positive batch_size on first iteration."""
        _write_fixture(tmp_path / "users.jsonl", '{"id": 1}\n')
        agen = iter_fixture_async(tmp_path, "users", batch_size=0)
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            await agen.__anext__()

    def test_iter_fixture_sync_missing_fixture_raises_on_call(self, tmp_path: Path) -> None:
        """Test iter_fixture_sync raises FileNotFoundError eagerly at call time."""
        with pytest.raises(FileNotFoundError, match="Could not find the users fixture"):
            iter_fixture_sync(tmp_path, "users")

    def test_iter_fixture_non_array_json_raises(self, tmp_path: Path) -> None:
        """Test iter_fixture_sync rejects non-array top-level JSON values."""
        _write_fixture(tmp_path / "config.json", '{"a": 1}')
        with pytest.raises(ValueError, match="must contain a JSON array, got dict"):
            list(iter_fixture_sync(tmp_path, "config"))

    def test_iter_fixture_sync_close_releases_handles(
        self, sharded_users: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test closing iter_fixture_sync early closes the opened file handle."""
        opened: list[Any] = []
        original = _FixtureFile._open_text

        def spy(self: _FixtureFile) -> Any:
            handle = original(self)
            opened.append(handle)
            return handle

        monkeypatch.setattr(_FixtureFile, "_open_text", spy)
        gen = iter_fixture_sync(sharded_users, "users", batch_size=1)
        assert isinstance(gen, Generator)
        next(gen)
        gen.close()
        assert len(opened) == 1
        assert all(handle.closed for handle in opened)

    @pytest.mark.asyncio
    async def test_iter_fixture_async_aclose_releases_handles(
        self, sharded_users: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test closing iter_fixture_async early via aclose() closes the opened file handle."""
        opened: list[Any] = []
        original = _FixtureFile._open_text

        def spy(self: _FixtureFile) -> Any:
            handle = original(self)
            opened.append(handle)
            return handle

        monkeypatch.setattr(_FixtureFile, "_open_text", spy)
        agen = iter_fixture_async(sharded_users, "users", batch_size=1)
        assert isinstance(agen, AsyncGenerator)
        await agen.__anext__()
        await agen.aclose()
        assert len(opened) == 1
        assert all(handle.closed for handle in opened)

    def test_iter_fixture_sync_consumed_releases_handles(
        self, sharded_users: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test exhausting iter_fixture_sync closes every opened shard handle."""
        opened: list[Any] = []
        original = _FixtureFile._open_text

        def spy(self: _FixtureFile) -> Any:
            handle = original(self)
            opened.append(handle)
            return handle

        monkeypatch.setattr(_FixtureFile, "_open_text", spy)
        list(iter_fixture_sync(sharded_users, "users", batch_size=2))
        assert len(opened) == 2
        assert all(handle.closed for handle in opened)


class TestWriteFixtureSync:
    """Test cases for write_fixture_sync and _FixtureLocator.existing_paths."""

    @pytest.mark.parametrize(
        ("file_format", "records", "expected_name", "expected_bytes"),
        [
            pytest.param(
                "json",
                [{"id": 1}, {"id": 2}],
                "users.json",
                b'[\n{"id":1},\n{"id":2}\n]\n',
                id="json",
            ),
            pytest.param(
                "jsonl",
                [{"id": 1}, {"id": 2}],
                "users.jsonl",
                b'{"id":1}\n{"id":2}\n',
                id="jsonl",
            ),
            pytest.param(
                "csv",
                [{"id": 1, "name": "A"}, {"id": 2, "name": None}, {"id": 3}],
                "users.csv",
                b"id,name\r\n1,A\r\n2,\r\n3,\r\n",
                id="csv",
            ),
            pytest.param(
                "json",
                [],
                "users.json",
                b"[]\n",
                id="json-empty",
            ),
            pytest.param(
                "jsonl",
                [],
                "users.jsonl",
                b"",
                id="jsonl-empty",
            ),
            pytest.param(
                "csv",
                [],
                "users.csv",
                b"",
                id="csv-empty",
            ),
        ],
    )
    def test_write_exact_encoding(
        self,
        tmp_path: Path,
        file_format: FixtureFormat,
        records: "list[dict[str, Any]]",
        expected_name: str,
        expected_bytes: bytes,
    ) -> None:
        """Test exact byte encoding for JSON, JSONL, CSV, and empty fixtures."""
        paths = write_fixture_sync(tmp_path, "users", records, file_format=file_format)
        expected_path = tmp_path / expected_name
        assert paths == [expected_path]
        assert expected_path.read_bytes() == expected_bytes

    @pytest.mark.parametrize("file_format", ["json", "jsonl", "csv"])
    @pytest.mark.parametrize("compression", [None, "gzip", "zip"])
    def test_write_round_trip(
        self,
        tmp_path: Path,
        sample_data: "list[dict[str, Any]]",
        sample_csv_data: "list[dict[str, str]]",
        file_format: FixtureFormat,
        compression: "FixtureCompression | None",
    ) -> None:
        """Test writing and loading back across all formats and compressions."""
        out_dir = tmp_path / "out" / "nested"
        rows = sample_csv_data if file_format == "csv" else sample_data
        suffix = {"gzip": ".gz", "zip": ".zip"}.get(compression or "", "")
        expected_path = out_dir / f"users.{file_format}{suffix}"

        paths = write_fixture_sync(out_dir, "users", rows, file_format=file_format, compression=compression)

        assert out_dir.is_dir()
        assert paths == [expected_path]
        assert open_fixture_sync(out_dir, "users") == rows

    def test_write_gzip_is_deterministic(self, tmp_path: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test gzip fixture writes produce deterministic bytes with zeroed header metadata."""
        paths_a = write_fixture_sync(tmp_path / "a", "users", sample_data, file_format="jsonl", compression="gzip")
        paths_b = write_fixture_sync(tmp_path / "b", "users", sample_data, file_format="jsonl", compression="gzip")

        data_a = paths_a[0].read_bytes()
        data_b = paths_b[0].read_bytes()
        assert data_a == data_b
        assert data_a[3] == 0
        assert data_a[4:8] == b"\x00\x00\x00\x00"

    def test_write_zip_member_name_and_determinism(self, tmp_path: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test zip fixture writes produce deterministic archives with fixed member metadata."""
        paths_a = write_fixture_sync(tmp_path / "a", "users", sample_data, file_format="jsonl", compression="zip")
        paths_b = write_fixture_sync(tmp_path / "b", "users", sample_data, file_format="jsonl", compression="zip")

        assert paths_a[0].read_bytes() == paths_b[0].read_bytes()
        with zipfile.ZipFile(paths_a[0], "r") as archive:
            assert archive.namelist() == ["users.jsonl"]
            assert archive.infolist()[0].date_time == (1980, 1, 1, 0, 0, 0)

    def test_write_removes_stale_fixture_files(self, tmp_path: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test commit removes stale fixture files while preserving unrelated files."""
        (tmp_path / "users.json").write_bytes(b"old")
        (tmp_path / "USERS.csv").write_bytes(b"old")
        (tmp_path / "users.001.jsonl.gz").write_bytes(b"old")
        (tmp_path / "users_extra.json").write_bytes(b"old")
        (tmp_path / "users.json.bak").write_bytes(b"old")

        write_fixture_sync(tmp_path, "users", sample_data, file_format="jsonl")

        assert sorted(p.name for p in tmp_path.iterdir()) == ["users.json.bak", "users.jsonl", "users_extra.json"]

    def test_write_removes_gapped_old_layout(self, tmp_path: Path) -> None:
        """Test commit removes gapped old shard layouts that open_fixture_sync rejects."""
        _write_fixture(tmp_path / "users.001.jsonl", '{"id": 0}\n')
        _write_fixture(tmp_path / "users.003.jsonl", '{"id": 0}\n')
        with pytest.raises(ValueError, match="is missing shard index\\(es\\) 2"):
            open_fixture_sync(tmp_path, "users")

        write_fixture_sync(tmp_path, "users", [{"id": 1}], file_format="json")

        assert sorted(p.name for p in tmp_path.iterdir()) == ["users.json"]
        assert open_fixture_sync(tmp_path, "users") == [{"id": 1}]

    def test_existing_paths_lists_every_layout(self, tmp_path: Path) -> None:
        """Test _FixtureLocator.existing_paths returns sorted deduplicated paths across layouts."""
        for name in (
            "users.json",
            "USERS.csv",
            "users.001.jsonl.gz",
            "users.1.json",
            "users.001.json.gz",
            "users_extra.json",
        ):
            (tmp_path / name).write_bytes(b"x")

        assert _FixtureLocator(tmp_path, "users").existing_paths() == [
            tmp_path / name
            for name in ("USERS.csv", "users.001.json.gz", "users.001.jsonl.gz", "users.1.json", "users.json")
        ]
        assert _FixtureLocator(tmp_path / "missing", "users").existing_paths() == []

    def test_write_aborts_on_iterator_error(self, tmp_path: Path) -> None:
        """Test iterator errors abort without leaving temp files or modifying existing fixtures."""
        existing = tmp_path / "users.json"
        existing.write_bytes(b"old")

        def failing_records() -> "Generator[dict[str, int], None, None]":
            for i in range(1, 11):
                yield {"id": i}
            msg = "boom"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="boom"):
            write_fixture_sync(tmp_path, "users", failing_records(), file_format="jsonl", compression="gzip")

        assert existing.read_bytes() == b"old"
        assert [p.name for p in tmp_path.iterdir()] == ["users.json"]

    def test_write_csv_rejects_non_mapping(self, tmp_path: Path) -> None:
        """Test CSV writer rejects non-mapping records without leaving files behind."""
        with pytest.raises(TypeError, match="CSV fixture records must be mappings, got int"):
            write_fixture_sync(tmp_path, "users", [1], file_format="csv")
        assert list(tmp_path.iterdir()) == []

    def test_write_csv_rejects_schema_drift(self, tmp_path: Path) -> None:
        """Test CSV writer rejects records containing keys absent from the first record."""
        with pytest.raises(
            ValueError, match=r"CSV record 2 of fixture 'users' has keys not in the header: \['extra'\]"
        ):
            write_fixture_sync(tmp_path, "users", [{"id": 1}, {"id": 2, "extra": "x"}], file_format="csv")
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"max_bytes": 0}, "max_bytes must be at least 1, got 0"),
            ({"max_records": 0}, "max_records must be at least 1, got 0"),
            ({"file_format": "xml"}, "Unsupported fixture format 'xml'"),
            ({"compression": "bz2"}, "Unsupported fixture compression 'bz2'"),
        ],
    )
    def test_write_validates_arguments_before_touching_disk(
        self, tmp_path: Path, kwargs: "dict[str, Any]", match: str
    ) -> None:
        """Test invalid writer options raise ValueError before creating the output directory."""
        target = tmp_path / "missing"
        with pytest.raises(ValueError, match=match):
            write_fixture_sync(target, "users", [], **kwargs)
        assert target.exists() is False

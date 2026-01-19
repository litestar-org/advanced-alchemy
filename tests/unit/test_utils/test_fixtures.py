"""Tests for advanced_alchemy.utils.fixtures module."""

import csv
import gzip
import io
import json
import tempfile
import zipfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from advanced_alchemy.utils.fixtures import open_fixture, open_fixture_async


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


class TestOpenFixture:
    """Test cases for synchronous open_fixture function."""

    def test_open_plain_json_fixture(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test loading plain JSON fixture."""
        result = open_fixture(temp_fixtures_dir, "users")
        assert result == sample_data

    def test_open_gzipped_fixture(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test loading gzipped JSON fixture."""
        result = open_fixture(temp_fixtures_dir, "users_gz")
        assert result == sample_data

    def test_open_zipped_fixture(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test loading zipped JSON fixture."""
        result = open_fixture(temp_fixtures_dir, "users_zip")
        assert result == sample_data

    def test_open_zipped_fixture_multiple_files(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading zipped JSON fixture with multiple files, should prefer matching name."""
        result = open_fixture(temp_fixtures_dir, "users_multi")
        assert result == sample_data

    def test_open_zipped_fixture_preferred_name(
        self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]"
    ) -> None:
        """Test loading zipped JSON fixture prefers file with matching name."""
        result = open_fixture(temp_fixtures_dir, "users_preferred")
        assert result == sample_data

    def test_case_insensitive_support(self, temp_fixtures_dir: Path, sample_data: "list[dict[str, Any]]") -> None:
        """Test case-insensitive fixture loading (uppercase takes priority for compressed files)."""
        # Create uppercase gzipped file
        uppercase_gz_file = temp_fixtures_dir / "TESTCASE.json.gz"
        with gzip.open(uppercase_gz_file, "wt", encoding="utf-8") as f:
            json.dump(sample_data, f)

        # Test that uppercase is found
        result = open_fixture(temp_fixtures_dir, "testcase")
        assert result == sample_data

        # Create lowercase version and test priority (uppercase should still win)
        lowercase_gz_file = temp_fixtures_dir / "testcase.json.gz"
        lowercase_data = [{"different": "data"}]
        with gzip.open(lowercase_gz_file, "wt", encoding="utf-8") as f:
            json.dump(lowercase_data, f)

        # Should still load uppercase version first
        result = open_fixture(temp_fixtures_dir, "testcase")
        assert result == sample_data  # Original data, not lowercase_data

        # Remove uppercase, should fallback to lowercase
        uppercase_gz_file.unlink()
        result = open_fixture(temp_fixtures_dir, "testcase")
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
        result = open_fixture(temp_fixtures_dir, "priority")
        assert result == plain_data

        # Remove plain JSON, should load gzip
        json_file.unlink()
        result = open_fixture(temp_fixtures_dir, "priority")
        assert result == gz_data

        # Remove gzip, should load zip
        gz_file.unlink()
        result = open_fixture(temp_fixtures_dir, "priority")
        assert result == zip_data

    def test_fixture_not_found(self, temp_fixtures_dir: Path) -> None:
        """Test FileNotFoundError when fixture doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc_info:
            open_fixture(temp_fixtures_dir, "nonexistent")

        assert "Could not find the nonexistent fixture" in str(exc_info.value)
        assert "(tried .json, .json.gz, .json.zip, .csv, .csv.gz, .csv.zip with case variations)" in str(exc_info.value)

    def test_empty_zip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for empty zip file."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture(temp_fixtures_dir, "empty")

        assert "No JSON files found in zip archive" in str(exc_info.value)

    def test_zip_with_no_json_files(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for zip file with no JSON files."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture(temp_fixtures_dir, "no_json")

        assert "No JSON files found in zip archive" in str(exc_info.value)

    def test_corrupted_gzip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for corrupted gzip file."""
        # Create corrupted gzip file
        corrupted_file = temp_fixtures_dir / "corrupted.json.gz"
        with open(corrupted_file, "wb") as f:
            f.write(b"not a gzip file")

        with pytest.raises(OSError) as exc_info:
            open_fixture(temp_fixtures_dir, "corrupted")

        assert "Error reading fixture file" in str(exc_info.value)

    def test_corrupted_zip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for corrupted zip file."""
        # Create corrupted zip file
        corrupted_file = temp_fixtures_dir / "corrupted_zip.json.zip"
        with open(corrupted_file, "wb") as f:
            f.write(b"not a zip file")

        with pytest.raises(OSError) as exc_info:
            open_fixture(temp_fixtures_dir, "corrupted_zip")

        assert "Error reading fixture file" in str(exc_info.value)

    def test_invalid_json_content(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for invalid JSON content."""
        invalid_file = temp_fixtures_dir / "invalid.json"
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json content")

        with pytest.raises(Exception):  # decode_json will raise an appropriate exception
            open_fixture(temp_fixtures_dir, "invalid")


class TestOpenFixtureCSV:
    """Test cases for CSV fixture loading."""

    def test_open_plain_csv_fixture(self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]") -> None:
        """Test loading plain CSV fixture."""
        result = open_fixture(temp_fixtures_dir, "users_csv")
        assert result == sample_csv_data
        # Verify it's a list of dicts
        assert isinstance(result, list)
        assert all(isinstance(row, dict) for row in result)

    def test_open_gzipped_csv_fixture(self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]") -> None:
        """Test loading gzipped CSV fixture."""
        result = open_fixture(temp_fixtures_dir, "users_csv_gz")
        assert result == sample_csv_data

    def test_open_zipped_csv_fixture(self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]") -> None:
        """Test loading zipped CSV fixture."""
        result = open_fixture(temp_fixtures_dir, "users_csv_zip")
        assert result == sample_csv_data

    def test_open_zipped_csv_fixture_multiple_files(
        self, temp_fixtures_dir: Path, sample_csv_data: "list[dict[str, str]]"
    ) -> None:
        """Test loading zipped CSV fixture with multiple files, should prefer matching name."""
        result = open_fixture(temp_fixtures_dir, "users_csv_multi")
        assert result == sample_csv_data

    def test_csv_values_are_strings(self, temp_fixtures_dir: Path) -> None:
        """Test that CSV values are strings (important difference from JSON)."""
        result = open_fixture(temp_fixtures_dir, "users_csv")
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
        result = open_fixture(temp_fixtures_dir, "priority_format")
        assert result == sample_data  # JSON data, not CSV data

        # Remove JSON, should load CSV
        json_file.unlink()
        result = open_fixture(temp_fixtures_dir, "priority_format")
        assert result == sample_csv_data

    def test_empty_csv_zip_file(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for empty CSV zip file."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture(temp_fixtures_dir, "empty_csv")
        assert "No CSV files found in zip archive" in str(exc_info.value)

    def test_csv_zip_with_no_csv_files(self, temp_fixtures_dir: Path) -> None:
        """Test error handling for zip file with no CSV files."""
        with pytest.raises(ValueError) as exc_info:
            open_fixture(temp_fixtures_dir, "no_csv")
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

        result = open_fixture(temp_fixtures_dir, "special")
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

        result = open_fixture(temp_fixtures_dir, "unicode")
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

        result = open_fixture(temp_fixtures_dir, "embedded_newlines")
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

        result = open_fixture(temp_fixtures_dir, "embedded_newlines_gz")
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

        result = open_fixture(temp_fixtures_dir, "embedded_newlines_zip")
        assert len(result) == 1
        assert result[0]["description"] == "Line 1\nLine 2"  # Newline must be preserved

    def test_csv_with_utf8_bom(self, temp_fixtures_dir: Path) -> None:
        """Test CSV with UTF-8 BOM (common in Excel exports)."""
        # UTF-8 BOM is \ufeff at the start of the file
        csv_content = "\ufeffname,value\nAlice,1\nBob,2\n"
        csv_file = temp_fixtures_dir / "bom.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = open_fixture(temp_fixtures_dir, "bom")
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

        result = open_fixture(temp_fixtures_dir, "bom_gz")
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

        result = open_fixture(temp_fixtures_dir, "bom_zip")
        assert len(result) == 1
        assert "name" in result[0]
        assert "\ufeffname" not in result[0]

    def test_csv_empty_data_rows(self, temp_fixtures_dir: Path) -> None:
        """Test CSV with headers only (no data rows)."""
        csv_content = "name,email,age\n"
        csv_file = temp_fixtures_dir / "headers_only.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        result = open_fixture(temp_fixtures_dir, "headers_only")
        assert result == []  # Empty list, no rows

    def test_uppercase_plain_csv(self, temp_fixtures_dir: Path) -> None:
        """Test loading uppercase plain CSV file."""
        csv_content = "name,value\nUPPER,1\n"
        csv_file = temp_fixtures_dir / "UPPERTEST.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            f.write(csv_content)

        # Should find UPPERTEST.csv when searching for "uppertest"
        result = open_fixture(temp_fixtures_dir, "uppertest")
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
        assert "(tried .json, .json.gz, .json.zip, .csv, .csv.gz, .csv.zip with case variations)" in str(exc_info.value)

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

    @pytest.mark.skip(reason="Import mocking is complex and anyio is required by the project")
    @pytest.mark.asyncio
    async def test_missing_anyio_dependency(self, temp_fixtures_dir: Path) -> None:
        """Test MissingDependencyError when anyio is not available."""
        # Note: This test documents the expected behavior when anyio is not available.
        # In practice, anyio is a required dependency for this project.
        pass

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
        fixture_data = open_fixture(temp_fixtures_dir, "users")
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
        json_data = open_fixture(temp_fixtures_dir, "large")

        # Remove plain JSON to force loading compressed versions
        json_file.unlink()
        gz_data = open_fixture(temp_fixtures_dir, "large")

        gz_file.unlink()
        zip_data = open_fixture(temp_fixtures_dir, "large")

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
        fixture_data = open_fixture(temp_fixtures_dir, "us_state_lookup")
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
        json_result = open_fixture(temp_fixtures_dir, "data_json")
        csv_result = open_fixture(temp_fixtures_dir, "data_csv")

        assert json_result == sample_data
        assert csv_result == sample_csv_data

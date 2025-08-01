"""Tests for advanced_alchemy.utils.fixtures module."""

import gzip
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
def temp_fixtures_dir(sample_data: "list[dict[str, Any]]") -> "Generator[Path, None, None]":
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
        assert "(tried .json, .json.gz, .json.zip with case variations)" in str(exc_info.value)

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
        assert "(tried .json, .json.gz, .json.zip with case variations)" in str(exc_info.value)

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

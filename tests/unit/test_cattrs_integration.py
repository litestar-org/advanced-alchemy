"""Tests for cattrs integration with attrs support in Advanced Alchemy services."""

from __future__ import annotations

import unittest.mock as mock
from typing import Optional

import pytest

from advanced_alchemy.service.typing import (
    ATTRS_INSTALLED,
    CATTRS_INSTALLED,
    schema_dump,
)

# pyright: reportAttributeAccessIssue=false

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed"),
]

if ATTRS_INSTALLED:
    from attrs import define

    @define
    class SimpleAttrsModel:
        """Simple attrs model for testing."""

        name: str
        age: int
        email: Optional[str] = None  # noqa: UP045


class TestCattrsIntegration:
    """Test cattrs integration scenarios."""

    @pytest.mark.skipif(not CATTRS_INSTALLED, reason="cattrs not installed")
    def test_schema_dump_with_cattrs_enabled(self) -> None:
        """Test schema_dump uses cattrs when available."""
        instance = SimpleAttrsModel(name="John", age=30, email="john@example.com")

        result = schema_dump(instance)

        assert isinstance(result, dict)
        assert result["name"] == "John"
        assert result["age"] == 30
        assert result["email"] == "john@example.com"

    def test_schema_dump_with_cattrs_disabled(self) -> None:
        """Test schema_dump falls back to attrs.asdict when cattrs is disabled."""
        from advanced_alchemy.service import typing as service_typing

        instance = SimpleAttrsModel(name="Jane", age=25)

        # Mock CATTRS_INSTALLED to be False
        with mock.patch.object(service_typing, "CATTRS_INSTALLED", False):
            result = schema_dump(instance)

        assert isinstance(result, dict)
        assert result["name"] == "Jane"
        assert result["age"] == 25
        assert result["email"] is None

    @pytest.mark.skipif(not CATTRS_INSTALLED, reason="cattrs not installed")
    def test_to_schema_with_cattrs_priority(self) -> None:
        """Test that to_schema uses cattrs over attrs when both are available."""
        from advanced_alchemy.service._util import ResultConverter

        converter = ResultConverter()
        data = {"name": "Alice", "age": 28, "email": "alice@example.com"}

        result = converter.to_schema(data, schema_type=SimpleAttrsModel)

        assert isinstance(result, SimpleAttrsModel)
        assert result.name == "Alice"
        assert result.age == 28
        assert result.email == "alice@example.com"

    def test_to_schema_attrs_fallback_when_cattrs_disabled(self) -> None:
        """Test that to_schema falls back to attrs when cattrs is disabled."""
        from advanced_alchemy.service import _util
        from advanced_alchemy.service import typing as service_typing
        from advanced_alchemy.service._util import ResultConverter

        converter = ResultConverter()
        data = {"name": "Bob", "age": 35, "email": "bob@example.com"}

        # Mock CATTRS_INSTALLED to be False in both modules
        with (
            mock.patch.object(service_typing, "CATTRS_INSTALLED", False),
            mock.patch.object(_util, "CATTRS_INSTALLED", False),
        ):
            result = converter.to_schema(data, schema_type=SimpleAttrsModel)

        assert isinstance(result, SimpleAttrsModel)
        assert result.name == "Bob"
        assert result.age == 35
        assert result.email == "bob@example.com"

    def test_to_schema_sequence_with_cattrs_disabled(self) -> None:
        """Test that to_schema handles sequences correctly when cattrs is disabled."""
        from advanced_alchemy.service import _util
        from advanced_alchemy.service import typing as service_typing
        from advanced_alchemy.service._util import ResultConverter
        from advanced_alchemy.service.pagination import OffsetPagination

        converter = ResultConverter()
        data = [
            {"name": "Charlie", "age": 40},
            {"name": "Diana", "age": 45},
        ]

        # Mock CATTRS_INSTALLED to be False in both modules
        with (
            mock.patch.object(service_typing, "CATTRS_INSTALLED", False),
            mock.patch.object(_util, "CATTRS_INSTALLED", False),
        ):
            result = converter.to_schema(data, schema_type=SimpleAttrsModel)

        assert isinstance(result, OffsetPagination)
        assert len(result.items) == 2
        assert all(isinstance(item, SimpleAttrsModel) for item in result.items)
        assert result.items[0].name == "Charlie"
        assert result.items[1].name == "Diana"

    @pytest.mark.skipif(not CATTRS_INSTALLED, reason="cattrs not installed")
    def test_cattrs_structure_direct_usage(self) -> None:
        """Test direct usage of cattrs structure function."""
        from advanced_alchemy.service.typing import structure

        data = {"name": "Eve", "age": 33, "email": "eve@example.com"}
        result = structure(data, SimpleAttrsModel)

        assert isinstance(result, SimpleAttrsModel)
        assert result.name == "Eve"
        assert result.age == 33
        assert result.email == "eve@example.com"

    @pytest.mark.skipif(not CATTRS_INSTALLED, reason="cattrs not installed")
    def test_cattrs_unstructure_direct_usage(self) -> None:
        """Test direct usage of cattrs unstructure function."""
        from advanced_alchemy.service.typing import unstructure

        instance = SimpleAttrsModel(name="Frank", age=28)
        result = unstructure(instance)

        assert isinstance(result, dict)
        assert result["name"] == "Frank"
        assert result["age"] == 28
        assert result["email"] is None

    def test_performance_with_cached_field_names(self) -> None:
        """Test that field name caching improves performance."""
        from advanced_alchemy.service import _util
        from advanced_alchemy.service import typing as service_typing
        from advanced_alchemy.service._util import ResultConverter, _get_attrs_field_names

        converter = ResultConverter()

        # Clear cache to ensure we're testing caching behavior
        _get_attrs_field_names.cache_clear()

        # Mock CATTRS_INSTALLED in both modules to be False to use attrs path
        with (
            mock.patch.object(service_typing, "CATTRS_INSTALLED", False),
            mock.patch.object(_util, "CATTRS_INSTALLED", False),
        ):
            # First call should populate the cache
            data1 = {"name": "Grace", "age": 30}
            result1 = converter.to_schema(data1, schema_type=SimpleAttrsModel)

            # Check cache info - should have 1 miss after first call
            cache_info_after_first = _get_attrs_field_names.cache_info()

            # Second call should use cached field names
            data2 = {"name": "Henry", "age": 35}
            result2 = converter.to_schema(data2, schema_type=SimpleAttrsModel)

            # Check cache info - should have 1 hit now
            cache_info_after_second = _get_attrs_field_names.cache_info()

        assert isinstance(result1, SimpleAttrsModel)
        assert isinstance(result2, SimpleAttrsModel)
        assert result1.name == "Grace"
        assert result2.name == "Henry"

        # Verify caching is working - should have 1 miss and 1 hit
        assert cache_info_after_first.misses == 1
        assert cache_info_after_second.hits >= 1
        assert cache_info_after_second.currsize >= 1

    def test_integration_with_both_libraries_available(self) -> None:
        """Test behavior when both cattrs and attrs are available."""
        if not CATTRS_INSTALLED:
            pytest.skip("cattrs not available for this test")

        from advanced_alchemy.service._util import ResultConverter

        converter = ResultConverter()
        data = {"name": "Ivy", "age": 29, "email": "ivy@example.com"}

        # Should prefer cattrs path when both are available
        result = converter.to_schema(data, schema_type=SimpleAttrsModel)

        assert isinstance(result, SimpleAttrsModel)
        assert result.name == "Ivy"
        assert result.age == 29
        assert result.email == "ivy@example.com"

    def test_edge_case_missing_fields(self) -> None:
        """Test handling of missing fields in data."""
        from advanced_alchemy.service import _util
        from advanced_alchemy.service import typing as service_typing
        from advanced_alchemy.service._util import ResultConverter

        converter = ResultConverter()
        # Data missing the 'age' field
        data = {"name": "Jack"}

        # Mock CATTRS_INSTALLED to be False in both modules to test attrs path
        with (
            mock.patch.object(service_typing, "CATTRS_INSTALLED", False),
            mock.patch.object(_util, "CATTRS_INSTALLED", False),
        ):
            # This should handle missing fields gracefully
            with pytest.raises(TypeError):  # attrs will complain about missing required field
                converter.to_schema(data, schema_type=SimpleAttrsModel)

    def test_extra_fields_filtered_out(self) -> None:
        """Test that extra fields not in attrs schema are filtered out."""
        from advanced_alchemy.service import _util
        from advanced_alchemy.service import typing as service_typing
        from advanced_alchemy.service._util import ResultConverter

        converter = ResultConverter()
        # Data with extra field 'phone' not in SimpleAttrsModel
        data = {"name": "Kate", "age": 32, "email": "kate@example.com", "phone": "123-456-7890"}

        # Mock CATTRS_INSTALLED to be False in both modules to test attrs filtering path
        with (
            mock.patch.object(service_typing, "CATTRS_INSTALLED", False),
            mock.patch.object(_util, "CATTRS_INSTALLED", False),
        ):
            result = converter.to_schema(data, schema_type=SimpleAttrsModel)

        assert isinstance(result, SimpleAttrsModel)
        assert result.name == "Kate"
        assert result.age == 32
        assert result.email == "kate@example.com"
        # Extra field should not cause issues
        assert not hasattr(result, "phone")

"""Tests for attrs integration in Advanced Alchemy services."""

from __future__ import annotations

from typing import Any, Optional

import pytest
from attrs import define, field

from advanced_alchemy.service.typing import (
    ATTRS_INSTALLED,
    AttrsInstance,
    is_attrs_instance,
    is_attrs_instance_with_field,
    is_attrs_instance_without_field,
    is_attrs_schema,
    is_schema,
    is_schema_with_field,
    is_schema_without_field,
    schema_dump,
)

pytestmark = [
    pytest.mark.unit,
]

# attrs test classes and fixtures


@define
class SimpleAttrsInstance:
    """Simple attrs class for testing."""

    name: str
    age: int


@define
class AttrsWithOptional:
    """attrs class with optional fields."""

    name: str
    email: Optional[str] = None  # noqa: UP045
    active: bool = True


@define
class AttrsWithDefaults:
    """attrs class with field defaults."""

    title: str
    count: int = field(default=0)
    tags: list[str] = field(factory=list)


@define
class NestedAttrsInstance:
    """attrs class with nested attrs."""

    user: SimpleAttrsInstance
    metadata: dict[str, Any] = field(factory=dict)


class TestAttrsDetection:
    """Test attrs class detection functions."""

    def test_attrs_installed_flag(self) -> None:
        """Test that ATTRS_INSTALLED flag is a boolean."""
        assert isinstance(ATTRS_INSTALLED, bool)

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_attrs_instance_with_attrs_instance(self) -> None:
        """Test is_attrs_instance with actual attrs class instance."""
        instance = SimpleAttrsInstance(name="test", age=30)
        assert is_attrs_instance(instance)

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_attrs_instance_with_complex_attrs(self) -> None:
        """Test is_attrs_instance with complex attrs instances."""
        simple_instance = SimpleAttrsInstance(name="John", age=25)
        nested_instance = NestedAttrsInstance(user=simple_instance, metadata={"role": "admin"})

        assert is_attrs_instance(simple_instance)
        assert is_attrs_instance(nested_instance)

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_attrs_schema_with_attrs_classes(self) -> None:
        """Test is_attrs_schema with attrs class types."""
        assert is_attrs_schema(SimpleAttrsInstance)
        assert is_attrs_schema(AttrsWithOptional)
        assert is_attrs_schema(AttrsWithDefaults)
        assert is_attrs_schema(NestedAttrsInstance)

    def test_is_attrs_schema_with_non_attrs_classes(self) -> None:
        """Test is_attrs_schema with non-attrs class types."""
        assert not is_attrs_schema(dict)
        assert not is_attrs_schema(list)
        assert not is_attrs_schema(str)
        assert not is_attrs_schema(int)

        class RegularClass:
            pass

        assert not is_attrs_schema(RegularClass)

    def test_is_attrs_class_with_non_attrs_instance(self) -> None:
        """Test is_attrs_class with non-attrs objects."""
        assert not is_attrs_instance({})
        assert not is_attrs_instance([])
        assert not is_attrs_instance("string")
        assert not is_attrs_instance(42)

    def test_is_attrs_class_with_regular_class(self) -> None:
        """Test is_attrs_class with regular Python class."""

        class RegularClass:
            def __init__(self, name: str) -> None:
                self.name = name

        instance = RegularClass("test")
        assert not is_attrs_instance(instance)

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_attrs_instance_with_field(self) -> None:
        """Test is_attrs_class_with_field function."""
        instance = SimpleAttrsInstance(name="test", age=30)

        assert is_attrs_instance_with_field(instance, "name")
        assert is_attrs_instance_with_field(instance, "age")
        assert not is_attrs_instance_with_field(instance, "nonexistent")

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_attrs_instance_without_field(self) -> None:
        """Test is_attrs_class_without_field function."""
        instance = SimpleAttrsInstance(name="test", age=30)

        assert not is_attrs_instance_without_field(instance, "name")
        assert not is_attrs_instance_without_field(instance, "age")
        assert is_attrs_instance_without_field(instance, "nonexistent")

    def test_is_attrs_class_field_checks_with_non_attrs(self) -> None:
        """Test field checking functions with non-attrs objects."""
        regular_obj = {"name": "test", "age": 30}

        assert not is_attrs_instance_with_field(regular_obj, "name")
        assert not is_attrs_instance_without_field(regular_obj, "name")


class TestSchemaIntegration:
    """Test attrs integration with schema functions."""

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_schema_with_attrs_class(self) -> None:
        """Test is_schema function includes attrs classes."""
        instance = SimpleAttrsInstance(name="test", age=30)
        assert is_schema(instance)

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_schema_with_field_attrs(self) -> None:
        """Test is_schema_with_field with attrs classes."""
        instance = SimpleAttrsInstance(name="test", age=30)

        assert is_schema_with_field(instance, "name")
        assert is_schema_with_field(instance, "age")
        assert not is_schema_with_field(instance, "nonexistent")

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_is_schema_without_field_attrs(self) -> None:
        """Test is_schema_without_field with attrs classes."""
        instance = SimpleAttrsInstance(name="test", age=30)

        assert not is_schema_without_field(instance, "name")
        assert not is_schema_without_field(instance, "age")
        assert is_schema_without_field(instance, "nonexistent")


class TestSchemaDump:
    """Test schema_dump function with attrs classes."""

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_schema_dump_simple_attrs(self) -> None:
        """Test schema_dump with simple attrs class."""
        instance = SimpleAttrsInstance(name="John", age=30)
        result = schema_dump(instance)

        expected = {"name": "John", "age": 30}
        assert result == expected
        assert isinstance(result, dict)

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_schema_dump_attrs_with_optional(self) -> None:
        """Test schema_dump with attrs class having optional fields."""
        instance = AttrsWithOptional(name="Jane", email="jane@example.com", active=True)
        result = schema_dump(instance)

        expected = {"name": "Jane", "email": "jane@example.com", "active": True}
        assert result == expected

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_schema_dump_attrs_with_defaults(self) -> None:
        """Test schema_dump with attrs class having field defaults."""
        instance = AttrsWithDefaults(title="Test", count=5, tags=["tag1", "tag2"])
        result = schema_dump(instance)

        expected = {"title": "Test", "count": 5, "tags": ["tag1", "tag2"]}
        assert result == expected

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_schema_dump_nested_attrs(self) -> None:
        """Test schema_dump with nested attrs classes."""
        user = SimpleAttrsInstance(name="John", age=25)
        instance = NestedAttrsInstance(user=user, metadata={"role": "admin"})
        result = schema_dump(instance)

        expected = {"user": {"name": "John", "age": 25}, "metadata": {"role": "admin"}}
        assert result == expected

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_schema_dump_attrs_collection_types(self) -> None:
        """Test schema_dump retains collection types."""
        instance = AttrsWithDefaults(title="Test", tags=["a", "b", "c"])
        result = schema_dump(instance)

        assert isinstance(result["tags"], list)
        assert result["tags"] == ["a", "b", "c"]

    def test_schema_dump_non_attrs_unchanged(self) -> None:
        """Test schema_dump with non-attrs objects remains unchanged."""
        # Dict should pass through unchanged
        dict_data = {"name": "test", "age": 30}
        assert schema_dump(dict_data) == dict_data

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_schema_dump_exclude_unset_parameter(self) -> None:
        """Test schema_dump exclude_unset parameter (attrs always includes all fields)."""
        instance = SimpleAttrsInstance(name="test", age=30)

        # attrs.asdict doesn't have exclude_unset concept, should return all fields
        result_with_unset = schema_dump(instance, exclude_unset=True)
        result_without_unset = schema_dump(instance, exclude_unset=False)

        expected = {"name": "test", "age": 30}
        assert result_with_unset == expected
        assert result_without_unset == expected


class TestAttrsInstanceProtocol:
    """Test AttrsInstance protocol."""

    def test_attrs_class_protocol_exists(self) -> None:
        """Test that AttrsInstance protocol is available."""
        assert AttrsInstance is not None

    @pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
    def test_attrs_class_protocol_with_real_attrs(self) -> None:
        """Test AttrsInstance protocol with real attrs class."""
        instance = SimpleAttrsInstance(name="test", age=30)

        # Should have __attrs_attrs__ attribute when attrs is installed
        assert hasattr(instance.__class__, "__attrs_attrs__")

    def test_attrs_class_protocol_type_annotation(self) -> None:
        """Test AttrsInstance can be used in type annotations."""

        # This test ensures the protocol is properly defined for type checking
        def process_attrs(obj: AttrsInstance) -> dict[str, Any]:
            return {"processed": True}

        # Should not raise type errors
        assert callable(process_attrs)


class TestErrorHandling:
    """Test error handling in attrs integration."""

    @pytest.mark.skipif(ATTRS_INSTALLED, reason="attrs is installed")
    def test_attrs_functions_when_not_installed(self) -> None:
        """Test attrs functions behave correctly when attrs not installed."""
        # When attrs not installed, detection should return False
        dummy_obj = SimpleAttrsInstance(name="test", age=30)

        assert not is_attrs_instance(dummy_obj)
        assert not is_attrs_instance_with_field(dummy_obj, "name")
        assert not is_attrs_instance_without_field(dummy_obj, "name")

    @pytest.mark.skipif(ATTRS_INSTALLED, reason="attrs is installed")
    def test_schema_dump_fallback_when_attrs_not_installed(self) -> None:
        """Test schema_dump falls back to __dict__ when attrs not installed."""
        dummy_obj = SimpleAttrsInstance(name="test", age=30)
        result = schema_dump(dummy_obj)

        # Should fall back to __dict__ access
        expected = {"name": "test", "age": 30}
        assert result == expected

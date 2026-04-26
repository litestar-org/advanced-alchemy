"""Unit tests for shared dependency-injection utilities."""

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from advanced_alchemy.utils.dependencies import DependencyCache, FieldNameType, FilterConfig, make_hashable
from advanced_alchemy.utils.singleton import SingletonMeta

pytestmark = pytest.mark.unit


def test_field_name_type_is_named_tuple_with_default_type_hint() -> None:
    field = FieldNameType(name="id")

    assert field.name == "id"
    assert field.type_hint is str
    assert tuple(field) == ("id", str)


def test_filter_config_allows_empty_config() -> None:
    config: FilterConfig = {}

    assert config == {}


def test_make_hashable_dict_order_invariant() -> None:
    left: dict[str, Any] = {"x": 1, "y": 2}
    right: dict[str, Any] = {"y": 2, "x": 1}

    assert make_hashable(left) == make_hashable(right)


def test_make_hashable_nested_values() -> None:
    config: FilterConfig = cast(
        "FilterConfig",
        {"sort_field": ("a", "b"), "search_ignore_case": True, "in_fields": [FieldNameType("tag")]},
    )

    assert make_hashable(config) == make_hashable(dict(config))


def test_make_hashable_set_order_invariant() -> None:
    assert make_hashable({1, 2, 3}) == make_hashable({3, 2, 1})


def test_dependency_cache_singleton() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(SingletonMeta, "_instances", {})
        first = DependencyCache()
        second = DependencyCache()

    assert first is second


def test_dependency_cache_add_get_dependencies() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(SingletonMeta, "_instances", {})
        cache = DependencyCache()
        dependencies = {"filters": MagicMock()}

        cache.add_dependencies("key", dependencies)

        assert cache.get_dependencies("key") == dependencies
        assert cache.get_dependencies("missing") is None


def test_dependency_cache_get_set_by_config() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(SingletonMeta, "_instances", {})
        cache = DependencyCache()
        config: FilterConfig = {"id_field": "uuid"}
        dependencies = {"filters": MagicMock()}

        cache.set(config, dependencies)

        assert cache.get(config) == dependencies

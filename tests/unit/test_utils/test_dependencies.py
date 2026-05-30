"""Unit tests for shared dependency-injection utilities."""

from enum import Enum
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from advanced_alchemy.utils.dependencies import (
    ChoiceField,
    DependencyCache,
    FieldNameType,
    FilterConfig,
    make_hashable,
    normalize_choice_field_types,
    normalize_sort_field,
)
from advanced_alchemy.utils.singleton import SingletonMeta

pytestmark = pytest.mark.unit


class StatusChoice(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"


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
        {
            "sort_field": ("a", "b"),
            "search_ignore_case": True,
            "in_fields": [FieldNameType("tag")],
            "choice_fields": [ChoiceField("status", ["active", "pending"])],
        },
    )

    assert make_hashable(config) == make_hashable(dict(config))


def test_make_hashable_set_order_invariant() -> None:
    assert make_hashable({1, 2, 3}) == make_hashable({3, 2, 1})


def test_make_hashable_preserves_list_order() -> None:
    assert make_hashable(["name", "id"]) != make_hashable(["id", "name"])


def test_normalize_sort_field_preserves_list_order() -> None:
    assert normalize_sort_field(["name", "id"]) == "name"


def test_normalize_sort_field_sorts_set_values() -> None:
    assert normalize_sort_field({"name", "id"}) == "id"


def test_normalize_choice_field_types_supports_explicit_values() -> None:
    normalized = normalize_choice_field_types([ChoiceField("status", ["active", "pending"])])
    field = next(iter(normalized))

    assert field.name == "status"
    assert "active" in str(field.type_hint)
    assert "pending" in str(field.type_hint)


def test_normalize_choice_field_types_supports_explicit_value_tuples() -> None:
    normalized = normalize_choice_field_types(("status", ("active", "pending")))
    field = next(iter(normalized))

    assert field.name == "status"
    assert "active" in str(field.type_hint)
    assert "pending" in str(field.type_hint)


def test_normalize_choice_field_types_supports_type_hint_tuples() -> None:
    normalized = normalize_choice_field_types(("status", StatusChoice))
    field = next(iter(normalized))

    assert field.name == "status"
    assert field.type_hint is StatusChoice


def test_normalize_choice_field_types_preserves_list_order() -> None:
    normalized = normalize_choice_field_types([("visibility", ["public", "private"]), FieldNameType("status", str)])

    assert [field.name for field in normalized] == ["visibility", "status"]


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

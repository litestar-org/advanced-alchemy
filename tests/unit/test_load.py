from __future__ import annotations

import pytest

from advanced_alchemy.repository.load import Load, LoadConfig


@pytest.mark.parametrize(
    ("load_1", "load_2", "expected"),
    [
        (Load(a=True), Load(a=True), True),
        (Load(a=True, b=True), Load(b=True, a=True), True),
        (Load(a=False, a__b=True), Load(a=False), True),
        (Load(a=False, a__b=False), Load(a=False, a__b=False), True),
        (Load(a=False, a__b=False, a__b__c=True), Load(a=False, a__b=False), True),
        (Load(a=True), Load(a=False), False),
        (Load(LoadConfig(default_strategy="*"), a=True), Load(a=True), False),
    ],
)
def test_load_eq(load_1: Load[str], load_2: Load[str], expected: Load[str]) -> None:
    """Test load equality."""
    assert (load_1 == load_2) == expected


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (Load(a=True), True),
        (Load(a=False), True),
        (Load(a=...), True),
        (Load(LoadConfig(default_strategy="*")), True),
        (Load(), False),
        (Load(LoadConfig(default_strategy=None)), False),
    ],
)
def test_load_bool(load: Load[str], expected: bool) -> None:
    """Test load truthiness"""
    assert bool(load) == expected


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (Load(a=...), True),
        (Load(a__b=..., a__b__c=False), True),
        (Load(LoadConfig(default_strategy="*")), True),
        (Load(), False),
        (Load(a__b=True), False),
    ],
)
def test_has_wildcards(load: Load[str], expected: bool) -> None:
    """Test wildcard detection."""
    assert load.has_wildcards() == expected

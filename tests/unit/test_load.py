from __future__ import annotations

import pytest

from advanced_alchemy.repository._load import SQLAlchemyLoad, SQLAlchemyLoadConfig


@pytest.mark.parametrize(
    ("load_1", "load_2", "expected"),
    [
        (SQLAlchemyLoad(a=True), SQLAlchemyLoad(a=True), True),
        (SQLAlchemyLoad(a=True, b=True), SQLAlchemyLoad(b=True, a=True), True),
        (SQLAlchemyLoad(a=False, a__b=True), SQLAlchemyLoad(a__b=True), True),
        (SQLAlchemyLoad(a=False, a__b=False), SQLAlchemyLoad(a=False, a__b=False), True),
        (SQLAlchemyLoad(a=True, a__b=False), SQLAlchemyLoad(a=True, a__b=False), True),
        (SQLAlchemyLoad(a=False, a__b=False, a__b__c=True), SQLAlchemyLoad(a__b__c=True), True),
        (SQLAlchemyLoad(a=True), SQLAlchemyLoad(a=False), False),
        (SQLAlchemyLoad(SQLAlchemyLoadConfig(default_strategy=...), a=True), SQLAlchemyLoad(a=True), False),
    ],
)
def test_load_eq(load_1: SQLAlchemyLoad, load_2: SQLAlchemyLoad, expected: SQLAlchemyLoad) -> None:
    """Test load equality."""
    assert (load_1 == load_2) == expected


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (SQLAlchemyLoad(a=True), True),
        (SQLAlchemyLoad(a=False), True),
        (SQLAlchemyLoad(a=...), True),
        (SQLAlchemyLoad(SQLAlchemyLoadConfig(default_strategy=...)), True),
        (SQLAlchemyLoad(), False),
        (SQLAlchemyLoad(SQLAlchemyLoadConfig(default_strategy=None)), False),
    ],
)
def test_load_bool(load: SQLAlchemyLoad, expected: bool) -> None:
    """Test load truthiness"""
    assert bool(load) == expected


@pytest.mark.parametrize(
    ("load", "expected"),
    [
        (SQLAlchemyLoad(a=...), True),
        (SQLAlchemyLoad(a__b=..., a__b__c=False), True),
        (SQLAlchemyLoad(SQLAlchemyLoadConfig(default_strategy=...)), True),
        (SQLAlchemyLoad(), False),
        (SQLAlchemyLoad(a__b=True), False),
    ],
)
def test_has_wildcards(load: SQLAlchemyLoad, expected: bool) -> None:
    """Test wildcard detection."""
    assert load.has_wildcards() == expected

"""Re-export parity test for the ``advanced_alchemy.filters`` public surface.

This test guards against regressions while ``filters.py`` is split into a
package. Every name advertised in ``__all__`` must:

* be importable via ``from advanced_alchemy.filters import <name>``,
* resolve to a non-``None`` object,
* be the same object as imported via ``advanced_alchemy.filters.<name>``.

After the package split, every name must additionally be importable via its
new submodule path and resolve to the same object as the public re-export.
The submodule expectations live in ``EXPECTED_SUBMODULE_LOCATIONS`` below; if
a public name is missing from that map, the test only checks the public path.
"""

import importlib

import pytest

import advanced_alchemy.filters as filters_pkg

PUBLIC_NAMES = tuple(filters_pkg.__all__)


EXPECTED_SUBMODULE_LOCATIONS: "dict[str, str]" = {
    "StatementFilter": "advanced_alchemy.filters._base",
    "InAnyFilter": "advanced_alchemy.filters._base",
    "PaginationFilter": "advanced_alchemy.filters._base",
    "FilterMap": "advanced_alchemy.filters._base",
    "LogicalOperatorMap": "advanced_alchemy.filters._base",
    "StatementFilterT": "advanced_alchemy.filters._base",
    "StatementTypeT": "advanced_alchemy.filters._base",
    "BeforeAfter": "advanced_alchemy.filters._columns",
    "OnBeforeAfter": "advanced_alchemy.filters._columns",
    "CollectionFilter": "advanced_alchemy.filters._columns",
    "NotInCollectionFilter": "advanced_alchemy.filters._columns",
    "NullFilter": "advanced_alchemy.filters._columns",
    "NotNullFilter": "advanced_alchemy.filters._columns",
    "ComparisonFilter": "advanced_alchemy.filters._columns",
    "LimitOffset": "advanced_alchemy.filters._pagination",
    "OrderBy": "advanced_alchemy.filters._pagination",
    "SearchFilter": "advanced_alchemy.filters._search",
    "NotInSearchFilter": "advanced_alchemy.filters._search",
    "RelationshipFilter": "advanced_alchemy.filters._relationship",
    "ExistsFilter": "advanced_alchemy.filters._logical",
    "NotExistsFilter": "advanced_alchemy.filters._logical",
    "FilterGroup": "advanced_alchemy.filters._logical",
    "MultiFilter": "advanced_alchemy.filters._logical",
    "UNSET": "advanced_alchemy.filters._filterset",
    "BaseFieldFilter": "advanced_alchemy.filters._filterset",
    "FieldSpec": "advanced_alchemy.filters._filterset",
    "BooleanFilter": "advanced_alchemy.filters._fields",
    "DateFilter": "advanced_alchemy.filters._fields",
    "DatePartFilter": "advanced_alchemy.filters._fields",
    "DateTimeFilter": "advanced_alchemy.filters._fields",
    "EnumFilter": "advanced_alchemy.filters._fields",
    "NumberFilter": "advanced_alchemy.filters._fields",
    "OrderingApply": "advanced_alchemy.filters._fields",
    "OrderingFilter": "advanced_alchemy.filters._fields",
    "StringFilter": "advanced_alchemy.filters._fields",
    "UUIDFilter": "advanced_alchemy.filters._fields",
    "FilterTypes": "advanced_alchemy.filters",
}


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_public_name_importable_from_package(name: str) -> None:
    obj = getattr(filters_pkg, name)
    assert obj is not None, f"advanced_alchemy.filters.{name} is None"


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_public_name_in_module_dict(name: str) -> None:
    assert name in dir(filters_pkg), f"{name} not exported by advanced_alchemy.filters"


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_public_name_resolves_to_same_object_via_submodule(name: str) -> None:
    expected_module = EXPECTED_SUBMODULE_LOCATIONS.get(name)
    if expected_module is None:
        pytest.skip(f"No expected submodule location declared for {name}")
    if expected_module == "advanced_alchemy.filters":
        return
    submodule = importlib.import_module(expected_module)
    public_obj = getattr(filters_pkg, name)
    submodule_obj = getattr(submodule, name, None)
    assert submodule_obj is not None, f"{name} not found in {expected_module}"
    assert submodule_obj is public_obj, (
        f"{name} in {expected_module} is not the same object as advanced_alchemy.filters.{name}"
    )


def test_all_tuple_has_no_duplicates() -> None:
    assert len(PUBLIC_NAMES) == len(set(PUBLIC_NAMES)), "advanced_alchemy.filters.__all__ has duplicate entries"


def test_filter_map_typed_dict_keys_match_filter_classes() -> None:
    expected_keys = {
        "before_after",
        "on_before_after",
        "collection",
        "not_in_collection",
        "limit_offset",
        "null",
        "not_null",
        "order_by",
        "search",
        "not_in_search",
        "comparison",
        "exists",
        "not_exists",
        "filter_group",
        "relationship",
    }
    actual_keys = set(filters_pkg.MultiFilter._filter_map.keys())
    assert actual_keys == expected_keys, f"FilterMap keys drifted: {actual_keys ^ expected_keys}"

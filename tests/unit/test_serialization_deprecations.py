"""Tests for the v1.x deprecation shims at ``advanced_alchemy._serialization``
and ``advanced_alchemy.service.typing``.

The shims must:
1. Continue to expose every name that v1.9.x exported.
2. Emit a ``DeprecationWarning`` on attribute access that names the new home.
3. Return the same object as the new canonical location.
"""

import importlib
from typing import Any

import pytest


def _import_attr(module_name: str, attr_name: str) -> Any:
    """Import ``attr_name`` from ``module_name`` fresh, bypassing the import cache.

    The shim's ``__getattr__`` only fires on attribute access that misses the
    module's regular namespace, so the warning is emitted once per *attribute*
    rather than once per *import statement*.  Returning the resolved object lets
    tests assert it matches the canonical location.
    """
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


# ---------------------------------------------------------------------------
# advanced_alchemy._serialization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "new_module"),
    [
        ("BaseModel", "advanced_alchemy.typing"),
        ("PYDANTIC_INSTALLED", "advanced_alchemy.typing"),
        ("encode_json", "advanced_alchemy.utils.serialization"),
        ("decode_json", "advanced_alchemy.utils.serialization"),
        ("encode_complex_type", "advanced_alchemy.utils.serialization"),
        ("decode_complex_type", "advanced_alchemy.utils.serialization"),
        ("convert_datetime_to_gmt_iso", "advanced_alchemy.utils.serialization"),
        ("convert_date_to_iso", "advanced_alchemy.utils.serialization"),
    ],
)
def test_legacy_serialization_shim_emits_deprecation_warning(name: str, new_module: str) -> None:
    """Each name re-exported from ``advanced_alchemy._serialization`` warns and
    points at the canonical location."""
    with pytest.warns(DeprecationWarning, match=rf"Use '{new_module}\.{name}' instead"):
        value = _import_attr("advanced_alchemy._serialization", name)

    canonical = getattr(importlib.import_module(new_module), name)
    assert value is canonical


def test_legacy_serialization_shim_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match="not_a_real_name"):
        _import_attr("advanced_alchemy._serialization", "not_a_real_name")


def test_legacy_serialization_shim_lists_renames_in_all() -> None:
    import advanced_alchemy._serialization as shim

    expected = {
        "BaseModel",
        "PYDANTIC_INSTALLED",
        "encode_json",
        "decode_json",
        "encode_complex_type",
        "decode_complex_type",
        "convert_datetime_to_gmt_iso",
        "convert_date_to_iso",
    }
    assert expected.issubset(set(shim.__all__))


# ---------------------------------------------------------------------------
# advanced_alchemy.service.typing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "new_module"),
    [
        # Foundational typing surface
        ("ATTRS_INSTALLED", "advanced_alchemy.typing"),
        ("CATTRS_INSTALLED", "advanced_alchemy.typing"),
        ("LITESTAR_INSTALLED", "advanced_alchemy.typing"),
        ("MSGSPEC_INSTALLED", "advanced_alchemy.typing"),
        ("PYDANTIC_INSTALLED", "advanced_alchemy.typing"),
        ("UNSET", "advanced_alchemy.typing"),
        ("BaseModel", "advanced_alchemy.typing"),
        ("Struct", "advanced_alchemy.typing"),
        ("TypeAdapter", "advanced_alchemy.typing"),
        ("UnsetType", "advanced_alchemy.typing"),
        ("FailFast", "advanced_alchemy.typing"),
        ("DTOData", "advanced_alchemy.typing"),
        ("T", "advanced_alchemy.typing"),
        # Schema/dict/attrs guards and helpers
        ("schema_dump", "advanced_alchemy.utils.serializers"),
        ("ModelDictT", "advanced_alchemy.utils.serializers"),
        ("ModelDictListT", "advanced_alchemy.utils.serializers"),
        ("ModelDTOT", "advanced_alchemy.utils.serializers"),
        ("FilterTypeT", "advanced_alchemy.utils.serializers"),
        ("SupportedSchemaModel", "advanced_alchemy.utils.serializers"),
        ("is_attrs_instance", "advanced_alchemy.utils.serializers"),
        ("is_dto_data", "advanced_alchemy.utils.serializers"),
        ("is_msgspec_struct", "advanced_alchemy.utils.serializers"),
        ("is_pydantic_model", "advanced_alchemy.utils.serializers"),
        ("is_schema", "advanced_alchemy.utils.serializers"),
        ("is_dict", "advanced_alchemy.utils.serializers"),
        ("get_type_adapter", "advanced_alchemy.utils.serializers"),
        ("structure", "advanced_alchemy.utils.serializers"),
        ("unstructure", "advanced_alchemy.utils.serializers"),
        ("fields", "advanced_alchemy.utils.serializers"),
        ("asdict", "advanced_alchemy.utils.serializers"),
        ("has", "advanced_alchemy.utils.serializers"),
    ],
)
def test_legacy_service_typing_shim_emits_deprecation_warning(name: str, new_module: str) -> None:
    with pytest.warns(DeprecationWarning, match=rf"Use '{new_module}\.{name}' instead"):
        value = _import_attr("advanced_alchemy.service.typing", name)

    canonical = getattr(importlib.import_module(new_module), name)
    assert value is canonical


def test_legacy_service_typing_shim_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match="not_a_real_name"):
        _import_attr("advanced_alchemy.service.typing", "not_a_real_name")


def test_legacy_service_typing_shim_keeps_pydantic_use_failfast() -> None:
    """``PYDANTIC_USE_FAILFAST`` was a module-level constant, not a moved
    name.  It must remain accessible without a deprecation warning."""
    import warnings

    import advanced_alchemy.service.typing as shim

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        # No warning expected — direct attribute access on the constant.
        assert shim.PYDANTIC_USE_FAILFAST is False

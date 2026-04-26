# pyright: reportUnsupportedDunderAll=false
"""Deprecated shim for ``advanced_alchemy.service.typing``.

This module re-exports the public surface that lived here in v1.x from
its new locations under :mod:`advanced_alchemy.typing` (foundational
optional-dependency stubs and feature-detection flags) and
:mod:`advanced_alchemy.utils.serializers` (schema/dict/attrs type guards
and ``schema_dump``).  Importing any name from this module emits a
:class:`DeprecationWarning`.

This module will be removed in a future major release.
"""

from typing import Any

from advanced_alchemy.utils.deprecation import warn_deprecation

# Names that moved to advanced_alchemy.typing
_TYPING_NAMES = (
    "ATTRS_INSTALLED",
    "CATTRS_INSTALLED",
    "LITESTAR_INSTALLED",
    "MSGSPEC_INSTALLED",
    "PYDANTIC_INSTALLED",
    "UNSET",
    "AttrsInstance",
    "AttrsLike",
    "BaseModel",
    "BaseModelLike",
    "DTOData",
    "DTODataLike",
    "DictProtocol",
    "FailFast",
    "Struct",
    "StructLike",
    "T",
    "TypeAdapter",
    "UnsetType",
    "attrs_nothing",
    "convert",
)

# Names that moved to advanced_alchemy.utils.serializers
_SERIALIZERS_NAMES = (
    "AttrsInstance",
    "BulkModelDictT",
    "FilterTypeT",
    "ModelDTOT",
    "ModelDictListT",
    "ModelDictT",
    "PydanticOrMsgspecT",
    "SupportedSchemaModel",
    "asdict",
    "fields",
    "get_attrs_fields",
    "get_type_adapter",
    "has_dict_attribute",
    "is_attrs_instance",
    "is_attrs_instance_with_field",
    "is_attrs_instance_without_field",
    "is_attrs_schema",
    "is_dataclass",
    "is_dataclass_with_field",
    "is_dataclass_without_field",
    "is_dict",
    "is_dict_with_field",
    "is_dict_without_field",
    "is_dto_data",
    "is_msgspec_struct",
    "is_msgspec_struct_with_field",
    "is_msgspec_struct_without_field",
    "is_pydantic_model",
    "is_pydantic_model_with_field",
    "is_pydantic_model_without_field",
    "is_row_mapping",
    "is_schema",
    "is_schema_or_dict",
    "is_schema_or_dict_with_field",
    "is_schema_or_dict_without_field",
    "is_schema_with_field",
    "is_schema_without_field",
    "is_sqlmodel_table_model",
    "schema_dump",
    "structure",
    "unstructure",
    "has",
)

# Source module for each renamed symbol. ``utils.serializers`` wins for any
# name present in both lists.
_RENAMES: "dict[str, str]" = {
    **dict.fromkeys(_TYPING_NAMES, "advanced_alchemy.typing"),
    **dict.fromkeys(_SERIALIZERS_NAMES, "advanced_alchemy.utils.serializers"),
}

# Constants that never moved — kept here for backwards compatibility.
PYDANTIC_USE_FAILFAST = False

# Names below are resolved lazily via ``__getattr__`` for the deprecation
# warning. ruff's F822 / pyright's reportUnsupportedDunderAll don't see them
# at module level — that's the point.
__all__ = (  # noqa: F822
    "ATTRS_INSTALLED",
    "CATTRS_INSTALLED",
    "LITESTAR_INSTALLED",
    "MSGSPEC_INSTALLED",
    "PYDANTIC_INSTALLED",
    "PYDANTIC_USE_FAILFAST",
    "UNSET",
    "AttrsInstance",
    "AttrsLike",
    "BaseModel",
    "BaseModelLike",
    "BulkModelDictT",
    "DTOData",
    "DTODataLike",
    "DictProtocol",
    "FailFast",
    "FilterTypeT",
    "ModelDTOT",
    "ModelDictListT",
    "ModelDictT",
    "PydanticOrMsgspecT",
    "Struct",
    "StructLike",
    "SupportedSchemaModel",
    "T",
    "TypeAdapter",
    "UnsetType",
    "asdict",
    "attrs_nothing",
    "convert",
    "fields",
    "get_attrs_fields",
    "get_type_adapter",
    "has",
    "has_dict_attribute",
    "is_attrs_instance",
    "is_attrs_instance_with_field",
    "is_attrs_instance_without_field",
    "is_attrs_schema",
    "is_dataclass",
    "is_dataclass_with_field",
    "is_dataclass_without_field",
    "is_dict",
    "is_dict_with_field",
    "is_dict_without_field",
    "is_dto_data",
    "is_msgspec_struct",
    "is_msgspec_struct_with_field",
    "is_msgspec_struct_without_field",
    "is_pydantic_model",
    "is_pydantic_model_with_field",
    "is_pydantic_model_without_field",
    "is_row_mapping",
    "is_schema",
    "is_schema_or_dict",
    "is_schema_or_dict_with_field",
    "is_schema_or_dict_without_field",
    "is_schema_with_field",
    "is_schema_without_field",
    "is_sqlmodel_table_model",
    "schema_dump",
    "structure",
    "unstructure",
)


def __getattr__(name: str) -> Any:
    if name not in _RENAMES:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    new_module = _RENAMES[name]
    warn_deprecation(
        version="1.10.0",
        removal_in="2.0.0",
        deprecated_name=f"{__name__}.{name}",
        kind="import",
        alternative=f"{new_module}.{name}",
    )
    import importlib

    return getattr(importlib.import_module(new_module), name)

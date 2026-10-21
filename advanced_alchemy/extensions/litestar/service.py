"""Litestar extension lazy re-exports for ``advanced_alchemy.service``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.service import (
        ATTRS_INSTALLED,
        DEFAULT_ERROR_MESSAGE_TEMPLATES,
        AttrsInstance,
        Empty,
        EmptyType,
        ErrorMessages,
        FilterTypeT,
        LoadSpec,
        ModelDictListT,
        ModelDictT,
        ModelDTOT,
        ModelOrRowMappingT,
        ModelT,
        OffsetPagination,
        OrderingPair,
        ResultConverter,
        SchemaDumpConfig,
        SQLAlchemyAsyncQueryService,
        SQLAlchemyAsyncRepositoryReadService,
        SQLAlchemyAsyncRepositoryService,
        SQLAlchemySyncQueryService,
        SQLAlchemySyncRepositoryReadService,
        SQLAlchemySyncRepositoryService,
        SupportedSchemaModel,
        fields,
        find_filter,
        is_attrs_instance,
        is_attrs_instance_with_field,
        is_attrs_instance_without_field,
        is_attrs_schema,
        is_dict,
        is_dict_with_field,
        is_dict_without_field,
        is_dto_data,
        is_msgspec_struct,
        is_msgspec_struct_with_field,
        is_msgspec_struct_without_field,
        is_pydantic_model,
        is_pydantic_model_with_field,
        is_pydantic_model_without_field,
        is_schema,
        is_schema_or_dict,
        is_schema_or_dict_with_field,
        is_schema_or_dict_without_field,
        is_schema_with_field,
        is_schema_without_field,
        is_sqlmodel_table_model,
        model_from_dict,
        schema_dump,
    )

__all__ = (
    "ATTRS_INSTALLED",
    "DEFAULT_ERROR_MESSAGE_TEMPLATES",
    "AttrsInstance",
    "Empty",
    "EmptyType",
    "ErrorMessages",
    "FilterTypeT",
    "LoadSpec",
    "ModelDTOT",
    "ModelDictListT",
    "ModelDictT",
    "ModelOrRowMappingT",
    "ModelT",
    "OffsetPagination",
    "OrderingPair",
    "ResultConverter",
    "SQLAlchemyAsyncQueryService",
    "SQLAlchemyAsyncRepositoryReadService",
    "SQLAlchemyAsyncRepositoryService",
    "SQLAlchemySyncQueryService",
    "SQLAlchemySyncRepositoryReadService",
    "SQLAlchemySyncRepositoryService",
    "SchemaDumpConfig",
    "SupportedSchemaModel",
    "fields",
    "find_filter",
    "is_attrs_instance",
    "is_attrs_instance_with_field",
    "is_attrs_instance_without_field",
    "is_attrs_schema",
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
    "is_schema",
    "is_schema_or_dict",
    "is_schema_or_dict_with_field",
    "is_schema_or_dict_without_field",
    "is_schema_with_field",
    "is_schema_without_field",
    "is_sqlmodel_table_model",
    "model_from_dict",
    "schema_dump",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.service``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.service")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))

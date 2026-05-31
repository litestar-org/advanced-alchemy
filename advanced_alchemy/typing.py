# pyright: reportUnsupportedDunderAll=false
"""Public type shims for optional dependencies.

Re-exports foundational stub types so that internal and external code
can ``from advanced_alchemy.typing import SQLModelBase`` (or any other
shim) without reaching into private modules.
"""

from typing import Any

from advanced_alchemy._typing import (
    ATTRS_INSTALLED,
    CATTRS_INSTALLED,
    LITESTAR_INSTALLED,
    MSGSPEC_INSTALLED,
    NUMPY_INSTALLED,
    ORJSON_INSTALLED,
    PYDANTIC_INSTALLED,
    SQLMODEL_INSTALLED,
    UNSET,
    AttrsInstance,
    AttrsLike,
    BaseModel,
    BaseModelLike,
    DataclassProtocol,
    DTOData,
    DTODataLike,
    FailFast,
    SQLModelBase,
    SQLModelBaseLike,
    Struct,
    StructLike,
    T,
    T_co,
    TypeAdapter,
    UnsetType,
    attrs_asdict,
    attrs_fields,
    attrs_has,
    attrs_nothing,
    cattrs_structure,
    cattrs_unstructure,
    convert,
)

__all__ = (  # noqa: F822
    "ATTRS_INSTALLED",
    "CATTRS_INSTALLED",
    "LITESTAR_INSTALLED",
    "MSGSPEC_INSTALLED",
    "NUMPY_INSTALLED",
    "ORJSON_INSTALLED",
    "PYDANTIC_INSTALLED",
    "SQLMODEL_INSTALLED",
    "UNSET",
    "AttrsInstance",
    "AttrsLike",
    "BaseModel",
    "BaseModelLike",
    "DTOData",
    "DTODataLike",
    "DataclassProtocol",
    "DictProtocol",
    "FailFast",
    "SQLModelBase",
    "SQLModelBaseLike",
    "Struct",
    "StructLike",
    "T",
    "T_co",
    "TypeAdapter",
    "UnsetType",
    "attrs_asdict",
    "attrs_fields",
    "attrs_has",
    "attrs_nothing",
    "cattrs_structure",
    "cattrs_unstructure",
    "convert",
)


def __getattr__(name: str) -> Any:
    if name != "DictProtocol":
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    from advanced_alchemy._typing import DictProtocol
    from advanced_alchemy.utils.deprecation import warn_deprecation

    warn_deprecation(
        version="1.11.0",
        removal_in="2.0.0",
        deprecated_name=f"{__name__}.DictProtocol",
        kind="import",
        alternative="advanced_alchemy.utils.serialization.has_dict_attribute",
    )
    return DictProtocol

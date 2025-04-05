"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    TypeVar,
    Union,
    cast,
    overload,
)

from typing_extensions import TypeAlias, TypeGuard

from advanced_alchemy.repository.typing import ModelT
from advanced_alchemy.service._typing import (
    LITESTAR_INSTALLED,
    MSGSPEC_INSTALLED,
    PYDANTIC_INSTALLED,
    UNSET,
    BaseModel,
    DTOData,
    FailFast,
    Struct,
    TypeAdapter,
    convert,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from advanced_alchemy.filters import StatementFilter

PYDANTIC_USE_FAILFAST = False  # leave permanently disabled for now


T = TypeVar("T")


FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
"""Type variable for filter types.

:class:`~advanced_alchemy.filters.StatementFilter`
"""


SupportedSchemaModel: TypeAlias = Union[Struct, BaseModel]
"""Type alias for objects that support to_dict or model_dump methods."""

ModelDTOT = TypeVar("ModelDTOT", bound="SupportedSchemaModel")
"""Type variable for model DTOs.

:class:`msgspec.Struct`|:class:`pydantic.BaseModel`
"""
PydanticOrMsgspecT = SupportedSchemaModel
"""Type alias for pydantic or msgspec models.

:class:`msgspec.Struct` or :class:`pydantic.BaseModel`
"""
ModelDictT: TypeAlias = "Union[dict[str, Any], ModelT, SupportedSchemaModel, DTOData[ModelT]]"
"""Type alias for model dictionaries.

Represents:
- :type:`dict[str, Any]` | :class:`~advanced_alchemy.base.ModelProtocol` | :class:`msgspec.Struct` |  :class:`pydantic.BaseModel` | :class:`litestar.dto.data_structures.DTOData` | :class:`~advanced_alchemy.base.ModelProtocol`
"""
ModelDictListT: TypeAlias = "Sequence[Union[dict[str, Any], ModelT, SupportedSchemaModel]]"
"""Type alias for model dictionary lists.

A list or sequence of any of the following:
- :type:`Sequence`[:type:`dict[str, Any]` | :class:`~advanced_alchemy.base.ModelProtocol` | :class:`msgspec.Struct` | :class:`pydantic.BaseModel`]

"""
BulkModelDictT: TypeAlias = (
    "Union[Sequence[Union[dict[str, Any], ModelT, SupportedSchemaModel]], DTOData[list[ModelT]]]"
)
"""Type alias for bulk model dictionaries.

:type:`Sequence`[ :type:`dict[str, Any]` | :class:`~advanced_alchemy.base.ModelProtocol` | :class:`msgspec.Struct` :class:`pydantic.BaseModel`] | :class:`litestar.dto.data_structures.DTOData`
"""


@lru_cache(typed=True)
def get_type_adapter(f: type[T]) -> TypeAdapter[T]:
    """Caches and returns a pydantic type adapter.

    Args:
        f: Type to create a type adapter for.

    Returns:
        :class:`pydantic.TypeAdapter`[:class:`typing.TypeVar`[T]]
    """
    if PYDANTIC_USE_FAILFAST:
        return TypeAdapter(
            Annotated[f, FailFast()],
        )
    return TypeAdapter(f)


def is_dto_data(v: Any) -> TypeGuard[DTOData[Any]]:
    """Check if a value is a Litestar DTOData object.

    Args:
        v: Value to check.

    Returns:
        bool
    """
    return LITESTAR_INSTALLED and isinstance(v, DTOData)


def is_pydantic_model(v: Any) -> TypeGuard[BaseModel]:
    """Check if a value is a pydantic model.

    Args:
        v: Value to check.

    Returns:
        bool
    """
    return PYDANTIC_INSTALLED and isinstance(v, BaseModel)


def is_msgspec_struct(v: Any) -> TypeGuard[Struct]:
    """Check if a value is a msgspec struct.

    Args:
        v: Value to check.

    Returns:
        bool
    """
    return MSGSPEC_INSTALLED and isinstance(v, Struct)


def is_dataclass(obj: Any) -> TypeGuard[Any]:
    """Check if an object is a dataclass."""
    return hasattr(obj, "__dataclass_fields__")


def is_dataclass_with_field(obj: Any, field_name: str) -> TypeGuard[object]:  # Can't specify dataclass type directly
    """Check if an object is a dataclass and has a specific field."""
    return is_dataclass(obj) and hasattr(obj, field_name)


def is_dataclass_without_field(obj: Any, field_name: str) -> TypeGuard[object]:
    """Check if an object is a dataclass and does not have a specific field."""
    return is_dataclass(obj) and not hasattr(obj, field_name)


def is_dict(v: Any) -> TypeGuard[dict[str, Any]]:
    """Check if a value is a dictionary.

    Args:
        v: Value to check.

    Returns:
        bool
    """
    return isinstance(v, dict)


def is_dict_with_field(v: Any, field_name: str) -> TypeGuard[dict[str, Any]]:
    """Check if a dictionary has a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_dict(v) and field_name in v


def is_dict_without_field(v: Any, field_name: str) -> TypeGuard[dict[str, Any]]:
    """Check if a dictionary does not have a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_dict(v) and field_name not in v


def is_pydantic_model_with_field(v: Any, field_name: str) -> TypeGuard[BaseModel]:
    """Check if a pydantic model has a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_pydantic_model(v) and hasattr(v, field_name)


def is_pydantic_model_without_field(v: Any, field_name: str) -> TypeGuard[BaseModel]:
    """Check if a pydantic model does not have a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_pydantic_model(v) and not hasattr(v, field_name)


def is_msgspec_struct_with_field(v: Any, field_name: str) -> TypeGuard[Struct]:
    """Check if a msgspec struct has a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_msgspec_struct(v) and hasattr(v, field_name)


def is_msgspec_struct_without_field(v: Any, field_name: str) -> "TypeGuard[Struct]":
    """Check if a msgspec struct does not have a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_msgspec_struct(v) and not hasattr(v, field_name)


def is_schema(v: Any) -> "TypeGuard[SupportedSchemaModel]":
    """Check if a value is a msgspec Struct or Pydantic model.

    Args:
        v: Value to check.

    Returns:
        bool
    """
    return is_msgspec_struct(v) or is_pydantic_model(v)


def is_schema_or_dict(v: Any) -> "TypeGuard[Union[SupportedSchemaModel, dict[str, Any]]]":
    """Check if a value is a msgspec Struct, Pydantic model, or dict.

    Args:
        v: Value to check.

    Returns:
        bool
    """
    return is_schema(v) or is_dict(v)


def is_schema_with_field(v: Any, field_name: str) -> "TypeGuard[SupportedSchemaModel]":
    """Check if a value is a msgspec Struct or Pydantic model with a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_msgspec_struct_with_field(v, field_name) or is_pydantic_model_with_field(v, field_name)


def is_schema_without_field(v: Any, field_name: str) -> "TypeGuard[SupportedSchemaModel]":
    """Check if a value is a msgspec Struct or Pydantic model without a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return not is_schema_with_field(v, field_name)


def is_schema_or_dict_with_field(v: Any, field_name: str) -> "TypeGuard[Union[SupportedSchemaModel, dict[str, Any]]]":
    """Check if a value is a msgspec Struct, Pydantic model, or dict with a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return is_schema_with_field(v, field_name) or is_dict_with_field(v, field_name)


def is_schema_or_dict_without_field(
    v: Any, field_name: str
) -> "TypeGuard[Union[SupportedSchemaModel, dict[str, Any]]]":
    """Check if a value is a msgspec Struct, Pydantic model, or dict without a specific field.

    Args:
        v: Value to check.
        field_name: Field name to check for.

    Returns:
        bool
    """
    return not is_schema_or_dict_with_field(v, field_name)


@overload
def schema_dump(
    data: "Union[dict[str, Any], SupportedSchemaModel, DTOData[ModelT]]", exclude_unset: bool = True
) -> "Union[dict[str, Any], ModelT]": ...


@overload
def schema_dump(data: ModelT, exclude_unset: bool = True) -> ModelT: ...


def schema_dump(  # noqa: PLR0911
    data: "Union[dict[str, Any], ModelT, SupportedSchemaModel, DTOData[ModelT]]", exclude_unset: bool = True
) -> "Union[dict[str, Any], ModelT]":
    """Dump a data object to a dictionary.

    Args:
        data:  :type:`dict[str, Any]` | :class:`advanced_alchemy.base.ModelProtocol` | :class:`msgspec.Struct` | :class:`pydantic.BaseModel` | :class:`litestar.dto.data_structures.DTOData[ModelT]`
        exclude_unset: :type:`bool` Whether to exclude unset values.

    Returns:
        Union[:type: dict[str, Any], :class:`~advanced_alchemy.base.ModelProtocol`]
    """
    if is_dict(data):
        return data
    if is_pydantic_model(data):
        return data.model_dump(exclude_unset=exclude_unset)
    if is_msgspec_struct(data):
        if exclude_unset:
            return {f: val for f in data.__struct_fields__ if (val := getattr(data, f, None)) != UNSET}
        return {f: getattr(data, f, None) for f in data.__struct_fields__}
    if is_dto_data(data):
        return cast("dict[str, Any]", data.as_builtins())
    if hasattr(data, "__dict__"):
        return data.__dict__
    return cast("ModelT", data)  # type: ignore[no-return-any]


__all__ = (
    "LITESTAR_INSTALLED",
    "MSGSPEC_INSTALLED",
    "PYDANTIC_INSTALLED",
    "PYDANTIC_USE_FAILFAST",
    "UNSET",
    "BaseModel",
    "BulkModelDictT",
    "DTOData",
    "FailFast",
    "FilterTypeT",
    "ModelDTOT",
    "ModelDictListT",
    "ModelDictT",
    "PydanticOrMsgspecT",
    "Struct",
    "SupportedSchemaModel",
    "TypeAdapter",
    "UnsetType",
    "convert",
    "get_type_adapter",
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
    "is_schema",
    "is_schema_or_dict",
    "is_schema_or_dict_with_field",
    "is_schema_or_dict_without_field",
    "is_schema_with_field",
    "is_schema_without_field",
    "schema_dump",
)

if TYPE_CHECKING:
    if not PYDANTIC_INSTALLED:
        from advanced_alchemy.service._typing import BaseModel, FailFast, TypeAdapter
    else:
        from pydantic import BaseModel, FailFast, TypeAdapter  # type: ignore[assignment] # noqa: TC004

    if not MSGSPEC_INSTALLED:
        from advanced_alchemy.service._typing import UNSET, Struct, UnsetType, convert
    else:
        from msgspec import UNSET, Struct, UnsetType, convert  # type: ignore[assignment]  # noqa: TC004

    if not LITESTAR_INSTALLED:
        from advanced_alchemy.service._typing import DTOData
    else:
        from litestar.dto import DTOData  # type: ignore[assignment] # noqa: TC004

"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Sequence,
    TypeVar,
    Union,
    cast,
)

from typing_extensions import Annotated, TypeAlias, TypeGuard

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
    from advanced_alchemy.filters import StatementFilter

PYDANTIC_USE_FAILFAST = False  # leave permanently disabled for now


T = TypeVar("T")


FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")
PydanticOrMsgspecT = Union[Struct, BaseModel]
ModelDictT: TypeAlias = Union[Dict[str, Any], ModelT, Struct, BaseModel, DTOData[ModelT]]
ModelDictListT: TypeAlias = Sequence[Union[Dict[str, Any], ModelT, Struct, BaseModel]]
BulkModelDictT: TypeAlias = Union[Sequence[Union[Dict[str, Any], ModelT, Struct, BaseModel]], DTOData[List[ModelT]]]


@lru_cache(typed=True)
def get_type_adapter(f: type[T]) -> TypeAdapter[T]:
    """Caches and returns a pydantic type adapter"""
    if PYDANTIC_USE_FAILFAST:
        return TypeAdapter(
            Annotated[f, FailFast()],
        )
    return TypeAdapter(f)


def is_dto_data(v: Any) -> TypeGuard[DTOData[Any]]:
    return LITESTAR_INSTALLED and isinstance(v, DTOData)


def is_pydantic_model(v: Any) -> TypeGuard[BaseModel]:
    return PYDANTIC_INSTALLED and isinstance(v, BaseModel)


def is_msgspec_model(v: Any) -> TypeGuard[Struct]:
    return MSGSPEC_INSTALLED and isinstance(v, Struct)


def is_dict(v: Any) -> TypeGuard[dict[str, Any]]:
    return isinstance(v, dict)


def is_dict_with_field(v: Any, field_name: str) -> TypeGuard[dict[str, Any]]:
    return is_dict(v) and field_name in v


def is_dict_without_field(v: Any, field_name: str) -> TypeGuard[dict[str, Any]]:
    return is_dict(v) and field_name not in v


def is_pydantic_model_with_field(v: Any, field_name: str) -> TypeGuard[BaseModel]:
    return is_pydantic_model(v) and field_name in v.model_fields


def is_pydantic_model_without_field(v: Any, field_name: str) -> TypeGuard[BaseModel]:
    return not is_pydantic_model_with_field(v, field_name)


def is_msgspec_model_with_field(v: Any, field_name: str) -> TypeGuard[Struct]:
    return is_msgspec_model(v) and field_name in v.__struct_fields__


def is_msgspec_model_without_field(v: Any, field_name: str) -> TypeGuard[Struct]:
    return not is_msgspec_model_with_field(v, field_name)


def schema_dump(
    data: dict[str, Any] | ModelT | Struct | BaseModel | DTOData[ModelT],
    exclude_unset: bool = True,
) -> dict[str, Any] | ModelT:
    if is_dict(data):
        return data
    if is_pydantic_model(data):
        return data.model_dump(exclude_unset=exclude_unset)
    if is_msgspec_model(data) and exclude_unset:
        return {f: val for f in data.__struct_fields__ if (val := getattr(data, f, None)) != UNSET}
    if is_msgspec_model(data) and not exclude_unset:
        return {f: getattr(data, f, None) for f in data.__struct_fields__}
    if is_dto_data(data):
        return cast("ModelT", data.as_builtins())  # pyright: ignore[reportUnknownVariableType]
    return cast("ModelT", data)


__all__ = (
    "ModelDictT",
    "ModelDictListT",
    "FilterTypeT",
    "ModelDTOT",
    "BulkModelDictT",
    "PydanticOrMsgspecT",
    "PYDANTIC_INSTALLED",
    "MSGSPEC_INSTALLED",
    "LITESTAR_INSTALLED",
    "PYDANTIC_USE_FAILFAST",
    "DTOData",
    "BaseModel",
    "TypeAdapter",
    "get_type_adapter",
    "FailFast",
    "Struct",
    "convert",
    "UNSET",
    "UnsetType",
    "is_dto_data",
    "is_dict",
    "is_dict_with_field",
    "is_dict_without_field",
    "is_msgspec_model",
    "is_pydantic_model_with_field",
    "is_msgspec_model_without_field",
    "is_pydantic_model",
    "is_msgspec_model_with_field",
    "is_pydantic_model_without_field",
    "schema_dump",
)

if TYPE_CHECKING:
    if not PYDANTIC_INSTALLED:
        from advanced_alchemy.service._typing import BaseModel, FailFast, TypeAdapter
    else:
        from pydantic import BaseModel, FailFast, TypeAdapter  # type: ignore[assignment] # noqa: TCH004

    if not MSGSPEC_INSTALLED:
        from advanced_alchemy.service._typing import UNSET, Struct, UnsetType, convert
    else:
        from msgspec import UNSET, Struct, UnsetType, convert  # type: ignore[assignment]  # noqa: TCH004

    if not LITESTAR_INSTALLED:
        from advanced_alchemy.service._typing import DTOData
    else:
        from litestar.dto import DTOData  # type: ignore[assignment] # noqa: TCH004

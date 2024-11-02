"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Final,
    List,
    Union,
    cast,
)

from typing_extensions import Annotated, TypeAlias, TypeGuard, TypeVar

from advanced_alchemy.filters import StatementFilter  # noqa: TCH001
from advanced_alchemy.repository.typing import ModelT

T = TypeVar("T")  # pragma: nocover

if TYPE_CHECKING:
    from pydantic import BaseModel  # pyright: ignore[reportAssignmentType]
    from pydantic.type_adapter import TypeAdapter  # pyright: ignore[reportUnusedImport, reportAssignmentType]
try:
    from pydantic import BaseModel  # pyright: ignore[reportAssignmentType]
    from pydantic.type_adapter import TypeAdapter  # pyright: ignore[reportUnusedImport, reportAssignmentType]

    PYDANTIC_INSTALLED: Final[bool] = True
except ImportError:  # pragma: nocover
    PYDANTIC_INSTALLED: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003

if TYPE_CHECKING:
    from pydantic import FailFast  # pyright: ignore[reportAssignmentType]
try:
    # this is from pydantic 2.8.  We should check for it before using it.
    from pydantic import FailFast  # pyright: ignore[reportAssignmentType]

    PYDANTIC_USE_FAILFAST: Final[bool] = False
except ImportError:
    PYDANTIC_USE_FAILFAST: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003


@lru_cache(typed=True)
def get_type_adapter(f: type[T]) -> TypeAdapter[T]:
    """Caches and returns a pydantic type adapter"""
    if PYDANTIC_USE_FAILFAST:
        return TypeAdapter(
            Annotated[f, FailFast()],  # type: ignore[operator]
        )
    return TypeAdapter(f)


if TYPE_CHECKING:
    from msgspec import UNSET, Struct, convert  # pyright: ignore[reportAssignmentType,reportUnusedImport]
try:
    from msgspec import (  # pyright: ignore[reportAssignmentType,reportUnusedImport]
        UNSET,
        Struct,
        convert,
    )

    MSGSPEC_INSTALLED: Final[bool] = True
except ImportError:  # pragma: nocover
    MSGSPEC_INSTALLED: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003


if TYPE_CHECKING:
    from litestar.dto.data_structures import DTOData  # pyright: ignore[reportAssignmentType,reportUnusedImport]
try:
    from litestar.dto.data_structures import DTOData  # pyright: ignore[reportAssignmentType,reportUnusedImport]

    LITESTAR_INSTALLED: Final[bool] = True
except ImportError:
    LITESTAR_INSTALLED: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003

FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")
PydanticOrMsgspecT = Union[Struct, BaseModel]
ModelDictT: TypeAlias = Union[Dict[str, Any], ModelT, Struct, BaseModel, DTOData[ModelT]]
ModelDictListT: TypeAlias = Sequence[Union[Dict[str, Any], ModelT, Struct, BaseModel]]
BulkModelDictT: TypeAlias = Union[Sequence[Union[Dict[str, Any], ModelT, Struct, BaseModel]], DTOData[List[ModelT]]]  # pyright: ignore[reportInvalidTypeArguments]


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

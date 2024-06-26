"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import (
    Any,
    ClassVar,
    Dict,
    Final,
    Generic,
    Protocol,
    Sequence,
    TypeVar,
    Union,
    cast,
    runtime_checkable,
)

from typing_extensions import TypeAlias, TypeGuard

from advanced_alchemy.exceptions import AdvancedAlchemyError
from advanced_alchemy.filters import StatementFilter  # noqa: TCH001
from advanced_alchemy.repository.typing import ModelT

try:
    from pydantic import BaseModel  # pyright: ignore[reportAssignmentType]
    from pydantic.type_adapter import TypeAdapter  # pyright: ignore[reportUnusedImport, reportAssignmentType]

    PYDANTIC_INSTALLED: Final[bool] = True
except ImportError:  # pragma: nocover

    @runtime_checkable
    class BaseModel(Protocol):  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

        def model_dump(*args: Any, **kwargs: Any) -> dict[str, Any]:
            """Placeholder"""
            return {}

    T = TypeVar("T")  # pragma: nocover

    class TypeAdapter(Generic[T]):  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: nocover
            """Init"""

        def validate_python(self, data: Any, *args: Any, **kwargs: Any) -> T:  # pragma: nocover
            """Stub"""
            return cast("T", data)

    PYDANTIC_INSTALLED: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003


try:
    from msgspec import UNSET, Struct, UnsetType, convert  # pyright: ignore[reportAssignmentType,reportUnusedImport]

    MSGSPEC_INSTALLED: Final[bool] = True
except ImportError:  # pragma: nocover
    import enum

    @runtime_checkable
    class Struct(Protocol):  # type: ignore[no-redef]
        """Placeholder Implementation"""

        __struct_fields__: ClassVar[tuple[str, ...]]

    def convert(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001
        """Placeholder implementation"""
        return {}

    class UnsetType(enum.Enum):  # type: ignore[no-redef] # pragma: nocover
        UNSET = "UNSET"

    UNSET = UnsetType.UNSET  # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]
    MSGSPEC_INSTALLED: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003


FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")
PydanticOrMsgspecT = Union[Struct, BaseModel]
ModelDictT: TypeAlias = Union[Dict[str, Any], ModelT, Struct, BaseModel]
ModelDictListT: TypeAlias = Sequence[Union[Dict[str, Any], ModelT, Struct, BaseModel]]


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
    return PYDANTIC_INSTALLED and isinstance(v, BaseModel) and field_name in v.model_fields  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]


def is_msgspec_model_with_field(v: Any, field_name: str) -> TypeGuard[Struct]:
    return MSGSPEC_INSTALLED and isinstance(v, Struct) and field_name in v.__struct_fields__


def schema_to_dict(v: Any, exclude_unset: bool = True) -> dict[str, Any]:
    if is_dict(v):
        return v
    if is_pydantic_model(v):
        return v.model_dump(exclude_unset=exclude_unset)

    if is_msgspec_model(v) and exclude_unset:
        return {f: val for f in v.__struct_fields__ if (val := getattr(v, f, None)) != UNSET}

    if is_msgspec_model(v) and not exclude_unset:
        return {f: getattr(v, f, None) for f in v.__struct_fields__}
    msg = f"Unable to convert model to dictionary for '{type(v)}' types"
    raise AdvancedAlchemyError(msg)


__all__ = (
    "ModelDictT",
    "ModelDictListT",
    "FilterTypeT",
    "ModelDTOT",
    "PydanticOrMsgspecT",
    "PYDANTIC_INSTALLED",
    "MSGSPEC_INSTALLED",
    "BaseModel",
    "TypeAdapter",
    "Struct",
    "convert",
    "UNSET",
    "is_dict",
    "is_dict_with_field",
    "is_msgspec_model",
    "is_pydantic_model_with_field",
    "is_pydantic_model",
    "is_msgspec_model_with_field",
    "schema_to_dict",
)

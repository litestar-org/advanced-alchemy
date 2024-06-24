"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import (
    Any,
    Final,
    Generic,
    TypeVar,
    cast,
)

from typing_extensions import TypeAlias

from advanced_alchemy.filters import StatementFilter  # noqa: TCH001
from advanced_alchemy.repository.typing import ModelT  # noqa: TCH001

try:
    from pydantic import BaseModel  # pyright: ignore[reportAssignmentType]
    from pydantic.type_adapter import TypeAdapter  # pyright: ignore[reportUnusedImport, reportAssignmentType]

    PYDANTIC_INSTALLED: Final[bool] = True
except ImportError:  # pragma: nocover

    class BaseModel:  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            """Model dump placeholder"""
            return {}

    T = TypeVar("T")  # pragma: nocover

    class TypeAdapter(Generic[T]):  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: nocover
            super().__init__()

        def validate_python(self, data: Any, *args: Any, **kwargs: Any) -> T:  # pragma: nocover
            """Stub"""
            return cast("T", data)

    PYDANTIC_INSTALLED: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003


try:
    from msgspec import UNSET, Struct, UnsetType, convert  # pyright: ignore[reportAssignmentType,reportUnusedImport]

    MSGSPEC_INSTALLED: Final[bool] = True
except ImportError:  # pragma: nocover
    import enum

    class Struct:  # type: ignore[no-redef]
        """Placeholder Implementation"""

        __struct_fields__: tuple[str, ...]

    def convert(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001
        """Placeholder implementation"""
        return {}

    class UnsetType(enum.Enum):  # type: ignore[no-redef] # pragma: nocover
        UNSET = "UNSET"

    UNSET = UnsetType.UNSET  # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]
    MSGSPEC_INSTALLED: Final[bool] = False  # type: ignore # pyright: ignore[reportConstantRedefinition,reportGeneralTypeIssues]  # noqa: PGH003


ModelDictT: TypeAlias = "dict[str, Any] | ModelT"
ModelDictListT: TypeAlias = "list[ModelT | dict[str, Any]] | list[dict[str, Any]]"
FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
if PYDANTIC_INSTALLED and MSGSPEC_INSTALLED:
    ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")
    PydanticOrMsgspecT: TypeAlias = "Struct | BaseModel"  # pyright: ignore[reportRedeclaration]
if PYDANTIC_INSTALLED and not MSGSPEC_INSTALLED:
    ModelDTOT = TypeVar("ModelDTOT", bound="BaseModel")  # type: ignore  # noqa: PGH003
    PydanticOrMsgspecT: TypeAlias = "BaseModel"  # type: ignore  # noqa: PGH003 # pyright: ignore[reportRedeclaration]
elif MSGSPEC_INSTALLED and not PYDANTIC_INSTALLED:
    ModelDTOT = TypeVar("ModelDTOT", bound="Struct")  # type: ignore  # noqa: PGH003
    PydanticOrMsgspecT: TypeAlias = "Struct"  # type: ignore # pyright: ignore[reportRedeclaration]  # noqa: PGH003
else:
    ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")  # type: ignore  # noqa: PGH003
    PydanticOrMsgspecT: TypeAlias = Any  # type: ignore  # pyright: ignore[reportRedeclaration]  # noqa: PGH003

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
)

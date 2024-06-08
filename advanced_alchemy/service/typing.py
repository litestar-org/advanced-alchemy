"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import (
    Any,
    Generic,
    Protocol,
    TypeVar,
    cast,
)

from typing_extensions import TypeAlias

from advanced_alchemy.filters import StatementFilter  # noqa: TCH001
from advanced_alchemy.repository.typing import ModelT  # noqa: TCH001

try:
    from msgspec import Struct, convert  # pyright: ignore[reportAssignmentType,reportUnusedImport]
except ImportError:  # pragma: nocover

    class Struct(Protocol):  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

    def convert(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001 # pragma: nocover
        """Placeholder implementation"""
        return {}


try:
    from pydantic import BaseModel  # pyright: ignore[reportAssignmentType]
    from pydantic.type_adapter import TypeAdapter  # pyright: ignore[reportUnusedImport, reportAssignmentType]
except ImportError:  # pragma: nocover

    class BaseModel(Protocol):  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

    T = TypeVar("T")  # pragma: nocover

    class TypeAdapter(Generic[T]):  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: nocover
            super().__init__()

        def validate_python(self, data: Any, *args: Any, **kwargs: Any) -> T:  # pragma: nocover
            """Stub"""
            return cast("T", data)


ModelDictT: TypeAlias = "dict[str, Any] | ModelT"
ModelDictListT: TypeAlias = "list[ModelT | dict[str, Any]] | list[dict[str, Any]]"
FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")
PydanticModelDTOT = TypeVar("PydanticModelDTOT", bound="BaseModel")
StructModelDTOT = TypeVar("StructModelDTOT", bound="Struct")

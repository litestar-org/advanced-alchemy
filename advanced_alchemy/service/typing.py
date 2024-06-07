"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import Any, TypeVar

from typing_extensions import TypeAlias

from advanced_alchemy.filters import StatementFilter  # noqa: TCH001
from advanced_alchemy.repository.typing import ModelT  # noqa: TCH001

try:
    from msgspec import Struct  # pyright: ignore[reportAssignmentType,reportUnknownVariableType,reportMissingImports]
except ImportError:  # pragma: nocover

    class Struct:  # type: ignore[no-redef]
        """Placeholder Implementation"""


try:
    from pydantic import (  # pyright: ignore[reportAssignmentType,reportUnknownVariableType,reportMissingImports]
        BaseModel,  # pyright: ignore[reportAssignmentType,reportUnknownVariableType,reportMissingImports]
    )
except ImportError:  # pragma: nocover

    class BaseModel:  # type: ignore[no-redef]
        """Placeholder Implementation"""


ModelDictT: TypeAlias = "dict[str, Any] | ModelT"
ModelDictListT: TypeAlias = "list[ModelT | dict[str, Any]] | list[dict[str, Any]]"
FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")
PydanticModelDTOT = TypeVar("PydanticModelDTOT", bound="BaseModel")
StructModelDTOT = TypeVar("StructModelDTOT", bound="Struct")

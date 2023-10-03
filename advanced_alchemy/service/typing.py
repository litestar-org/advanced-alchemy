"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import Any, TypeAlias, TypeVar

from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.repository.typing import ModelT

ModelDictT: TypeAlias = dict[str, Any] | ModelT
ModelDictListT: TypeAlias = list[ModelT | dict[str, Any]] | list[dict[str, Any]]
FilterTypeT = TypeVar("FilterTypeT", bound=FilterTypes)

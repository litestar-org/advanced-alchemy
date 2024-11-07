"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.util import find_spec
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Dict,
    Generic,
    List,
    Protocol,
    Sequence,
    Union,
    cast,
    runtime_checkable,
)

from typing_extensions import Annotated, TypeAlias, TypeVar, dataclass_transform

from advanced_alchemy.filters import StatementFilter  # noqa: TCH001
from advanced_alchemy.repository.typing import ModelT

PYDANTIC_INSTALLED = bool(find_spec("pydantic"))
PYDANTIC_USE_FAILFAST = False  # leave permanently disabled for now
MSGSPEC_INSTALLED = bool(find_spec("msgspec"))
LITESTAR_INSTALLED = bool(find_spec("litestar"))

T = TypeVar("T")

if not PYDANTIC_INSTALLED and not TYPE_CHECKING:

    @runtime_checkable
    class BaseModel(Protocol):
        """Placeholder Implementation"""

        model_fields: ClassVar[dict[str, Any]]

        def model_dump(*args: Any, **kwargs: Any) -> dict[str, Any]:
            """Placeholder"""
            return {}

    class TypeAdapter(Generic[T]):
        """Placeholder Implementation"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Init"""

        def validate_python(self, data: Any, *args: Any, **kwargs: Any) -> T:
            """Stub"""
            return cast("T", data)

    class FailFast:
        """Placeholder Implementation for FailFast"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Init"""

        def __call__(self, *args: Any, **kwargs: Any) -> None:
            """Placeholder"""


else:
    from pydantic import BaseModel  # pyright: ignore[reportAssignmentType]
    from pydantic.type_adapter import (
        TypeAdapter,  # type: ignore[assignment] # pyright: ignore[reportUnusedImport, reportAssignmentType]
    )

    try:
        # this is from pydantic 2.8.  We should check for it before using it.
        from pydantic import FailFast  # pyright: ignore[reportAssignmentType]
    except ImportError:

        class FailFast:  # type: ignore[no-redef]
            """Placeholder Implementation for FailFast"""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                """Init"""

            def __call__(self, *args: Any, **kwargs: Any) -> None:
                """Placeholder"""


@lru_cache(typed=True)
def get_type_adapter(f: type[T]) -> TypeAdapter[T]:
    """Caches and returns a pydantic type adapter"""
    if PYDANTIC_USE_FAILFAST:
        return TypeAdapter(
            Annotated[f, FailFast()],  # type: ignore[operator]
        )
    return TypeAdapter(f)


if not MSGSPEC_INSTALLED and not TYPE_CHECKING:
    import enum

    @dataclass_transform()
    @runtime_checkable
    class Struct(Protocol):
        """Placeholder Implementation"""

        __struct_fields__: ClassVar[tuple[str, ...]]

    def convert(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        """Placeholder implementation"""
        return {}

    class UnsetType(enum.Enum):
        UNSET = "UNSET"

    UNSET = UnsetType.UNSET
else:
    from msgspec import (
        UNSET,
        Struct,
        UnsetType,
        convert,
    )

if not LITESTAR_INSTALLED and not TYPE_CHECKING:

    class DTOData(Generic[T]):
        """Placeholder implementation"""

        def create_instance(*args: Any, **kwargs: Any) -> T:
            """Placeholder implementation"""
            return cast("T", kwargs)

        def update_instance(self, instance: T, **kwargs: Any) -> T:
            """Placeholder implementation"""
            return cast("T", kwargs)

        def as_builtins(self) -> Any:
            """Placeholder implementation"""
            return {}
else:
    from litestar.dto.data_structures import DTOData

FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
ModelDTOT = TypeVar("ModelDTOT", bound="Struct | BaseModel")
PydanticOrMsgspecT = Union[Struct, BaseModel]
ModelDictT: TypeAlias = Union[Dict[str, Any], ModelT, Struct, BaseModel, DTOData[ModelT]]
ModelDictListT: TypeAlias = Sequence[Union[Dict[str, Any], ModelT, Struct, BaseModel]]
BulkModelDictT: TypeAlias = Union[Sequence[Union[Dict[str, Any], ModelT, Struct, BaseModel]], DTOData[List[ModelT]]]


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
)

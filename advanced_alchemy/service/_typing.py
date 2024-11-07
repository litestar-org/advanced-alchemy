"""This is a simple wrapper around a few important classes in each library.

This is used to ensure compatibility when one or more of the libraries are installed.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import (
    Any,
    ClassVar,
    Generic,
    Protocol,
    cast,
    runtime_checkable,
)

from typing_extensions import TypeVar, dataclass_transform

PYDANTIC_INSTALLED = bool(find_spec("pydantic"))
MSGSPEC_INSTALLED = bool(find_spec("msgspec"))
LITESTAR_INSTALLED = bool(find_spec("litestar"))

T = TypeVar("T")

if not PYDANTIC_INSTALLED:

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

    class FailFast:  # pyright: ignore[reportRedeclaration]
        """Placeholder Implementation for FailFast"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Init"""

        def __call__(self, *args: Any, **kwargs: Any) -> None:
            """Placeholder"""


else:
    from pydantic import BaseModel, FailFast, TypeAdapter  # type: ignore[assignment]


if not MSGSPEC_INSTALLED:
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

    UNSET = UnsetType.UNSET  # pyright: ignore[reportConstantRedefinition]
else:
    from msgspec import (  # type: ignore[assignment]
        UNSET,  # pyright: ignore[reportConstantRedefinition]
        Struct,
        UnsetType,  # pyright: ignore[reportAssignmentType]
        convert,
    )

if not LITESTAR_INSTALLED:

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
    from litestar.dto.data_structures import DTOData  # type: ignore[assignment]


__all__ = (
    "PYDANTIC_INSTALLED",
    "MSGSPEC_INSTALLED",
    "LITESTAR_INSTALLED",
    "DTOData",
    "BaseModel",
    "TypeAdapter",
    "FailFast",
    "Struct",
    "convert",
    "UNSET",
)

"""This is a simple wrapper around a few important classes in each library.

This is used to ensure compatibility when one or more of the libraries are installed.
"""

from typing import (
    Any,
    ClassVar,
    Optional,
    Protocol,
    cast,
    runtime_checkable,
)

from typing_extensions import TypeVar, dataclass_transform

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)

try:
    from pydantic import BaseModel, FailFast, TypeAdapter  # pyright: ignore

    PYDANTIC_INSTALLED = True
except ImportError:

    @runtime_checkable
    class BaseModel(Protocol):  # type: ignore[no-redef]
        """Placeholder Implementation"""

        model_fields: "ClassVar[dict[str, Any]]"

        def model_dump(self, *args: Any, **kwargs: Any) -> "dict[str, Any]":
            """Placeholder"""
            return {}

    @runtime_checkable
    class TypeAdapter(Protocol[T_co]):  # type: ignore[no-redef]
        """Placeholder Implementation"""

        def __init__(
            self,
            type: Any,  # noqa: A002
            *,
            config: "Optional[Any]" = None,
            _parent_depth: int = 2,
            module: "Optional[str]" = None,
        ) -> None:
            """Init"""

        def validate_python(
            self,
            object: Any,  # noqa: A002
            /,
            *,
            strict: "Optional[bool]" = None,
            from_attributes: "Optional[bool]" = None,
            context: "Optional[dict[str, Any]]" = None,
        ) -> T_co:
            """Stub"""
            return cast("T_co", object)

    @runtime_checkable
    class FailFast(Protocol):  # type: ignore[no-redef]
        """Placeholder Implementation for FailFast"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Init"""

    PYDANTIC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

try:
    from msgspec import (
        UNSET,
        Struct,
        UnsetType,  # pyright: ignore[reportAssignmentType,reportGeneralTypeIssues]
        convert,  # pyright: ignore[reportGeneralTypeIssues]
    )

    MSGSPEC_INSTALLED: bool = True
except ImportError:
    import enum

    @dataclass_transform()
    @runtime_checkable
    class Struct(Protocol):  # type: ignore[no-redef]
        """Placeholder Implementation"""

        __struct_fields__: "ClassVar[tuple[str, ...]]"

    def convert(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001
        """Placeholder implementation"""
        return {}

    class UnsetType(enum.Enum):  # type: ignore[no-redef]
        UNSET = "UNSET"

    UNSET = UnsetType.UNSET  # pyright: ignore[reportConstantRedefinition]
    MSGSPEC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

try:
    from litestar.dto.data_structures import DTOData

    LITESTAR_INSTALLED = True
except ImportError:

    @runtime_checkable
    class DTOData(Protocol[T]):  # type: ignore[no-redef]
        """Placeholder implementation"""

        __slots__ = ("_backend", "_data_as_builtins")

        def __init__(self, backend: Any, data_as_builtins: Any) -> None:
            """Placeholder init"""

        def create_instance(self, **kwargs: Any) -> T:
            """Placeholder implementation"""
            return cast("T", kwargs)

        def update_instance(self, instance: T, **kwargs: Any) -> T:
            """Placeholder implementation"""
            return cast("T", kwargs)

        def as_builtins(self) -> Any:
            """Placeholder implementation"""
            return {}

    LITESTAR_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

try:
    from attrs import AttrsInstance, asdict, define, field, fields, has  # pyright: ignore

    ATTRS_INSTALLED = True
except ImportError:

    @runtime_checkable
    class AttrsInstance(Protocol):  # type: ignore[no-redef]
        """Placeholder Implementation for attrs classes"""

    def asdict(*args: Any, **kwargs: Any) -> "dict[str, Any]":  # type: ignore[misc] # noqa: ARG001
        """Placeholder implementation"""
        return {}

    def define(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001
        """Placeholder implementation"""
        return lambda cls: cls  # pyright: ignore[reportUnknownVariableType,reportUnknownLambdaType]

    def field(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001
        """Placeholder implementation"""
        return None

    def fields(*args: Any, **kwargs: Any) -> "tuple[Any, ...]":  # type: ignore[misc] # noqa: ARG001
        """Placeholder implementation"""
        return ()

    def has(*args: Any, **kwargs: Any) -> bool:  # type: ignore[misc] # noqa: ARG001
        """Placeholder implementation"""
        return False

    ATTRS_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

try:
    from cattrs import structure, unstructure  # pyright: ignore # type: ignore[import-not-found]

    CATTRS_INSTALLED = True
except ImportError:

    def unstructure(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        """Placeholder implementation"""
        return {}

    def structure(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        """Placeholder implementation"""
        return {}

    CATTRS_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

__all__ = (
    "ATTRS_INSTALLED",
    "CATTRS_INSTALLED",
    "LITESTAR_INSTALLED",
    "MSGSPEC_INSTALLED",
    "PYDANTIC_INSTALLED",
    "UNSET",
    "AttrsInstance",
    "BaseModel",
    "DTOData",
    "FailFast",
    "Struct",
    "TypeAdapter",
    "UnsetType",
    "asdict",
    "convert",
    "define",
    "field",
    "fields",
    "has",
    "structure",
    "unstructure",
)

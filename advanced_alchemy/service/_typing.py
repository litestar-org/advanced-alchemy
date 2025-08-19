# ruff: noqa: RUF100, PLR0913, A002, DOC201, PLR6301, PLR0917, ARG004, ARG002, ARG001
"""This is a simple wrapper around a few important classes in each library.

This is used to ensure compatibility when one or more of the libraries are installed.
"""

import enum
from typing import (
    Any,
    ClassVar,
    Final,
    Optional,
    Protocol,
    Union,
    cast,
    runtime_checkable,
)

from typing_extensions import Literal, TypeVar, dataclass_transform

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)

# Always define stub types for type checking


class BaseModelStub:
    """Placeholder implementation."""

    model_fields: ClassVar[dict[str, Any]] = {}
    __slots__ = ("__dict__", "__pydantic_extra__", "__pydantic_fields_set__", "__pydantic_private__")

    def __init__(self, **data: Any) -> None:
        for key, value in data.items():
            setattr(self, key, value)

    def model_dump(  # noqa: PLR0913
        self,
        /,
        *,
        include: "Optional[Any]" = None,  # noqa: ARG002
        exclude: "Optional[Any]" = None,  # noqa: ARG002
        context: "Optional[Any]" = None,  # noqa: ARG002
        by_alias: bool = False,  # noqa: ARG002
        exclude_unset: bool = False,  # noqa: ARG002
        exclude_defaults: bool = False,  # noqa: ARG002
        exclude_none: bool = False,  # noqa: ARG002
        round_trip: bool = False,  # noqa: ARG002
        warnings: "Union[bool, Literal['none', 'warn', 'error']]" = True,  # noqa: ARG002
        serialize_as_any: bool = False,  # noqa: ARG002
    ) -> "dict[str, Any]":
        """Placeholder implementation."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def model_dump_json(  # noqa: PLR0913
        self,
        /,
        *,
        include: "Optional[Any]" = None,  # noqa: ARG002
        exclude: "Optional[Any]" = None,  # noqa: ARG002
        context: "Optional[Any]" = None,  # noqa: ARG002
        by_alias: bool = False,  # noqa: ARG002
        exclude_unset: bool = False,  # noqa: ARG002
        exclude_defaults: bool = False,  # noqa: ARG002
        exclude_none: bool = False,  # noqa: ARG002
        round_trip: bool = False,  # noqa: ARG002
        warnings: "Union[bool, Literal['none', 'warn', 'error']]" = True,  # noqa: ARG002
        serialize_as_any: bool = False,  # noqa: ARG002
    ) -> str:
        """Placeholder implementation."""
        return "{}"


class TypeAdapterStub:
    """Placeholder implementation."""

    def __init__(
        self,
        type: Any,  # noqa: A002
        *,
        config: "Optional[Any]" = None,  # noqa: ARG002
        _parent_depth: int = 2,  # noqa: ARG002
        module: "Optional[str]" = None,  # noqa: ARG002
    ) -> None:
        """Initialize."""
        self._type = type

    def validate_python(  # noqa: PLR0913
        self,
        object: Any,
        /,
        *,
        strict: "Optional[bool]" = None,  # noqa: ARG002
        from_attributes: "Optional[bool]" = None,  # noqa: ARG002
        context: "Optional[dict[str, Any]]" = None,  # noqa: ARG002
        experimental_allow_partial: "Union[bool, Literal['off', 'on', 'trailing-strings']]" = False,  # noqa: ARG002
    ) -> Any:
        """Validate Python object."""
        return object


class FailFastStub:
    """Placeholder implementation for FailFast."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Init."""


# Try to import real implementations at runtime
try:
    from pydantic import BaseModel, FailFast, TypeAdapter

    PYDANTIC_INSTALLED = True  # pyright: ignore[reportConstantRedefinition]
except ImportError:
    BaseModel = BaseModelStub  # type: ignore[assignment,misc]
    TypeAdapter = TypeAdapterStub  # type: ignore[assignment,misc]
    FailFast = FailFastStub  # type: ignore[assignment,misc]
    PYDANTIC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

# Always define stub types for msgspec


@dataclass_transform()
class StructStub:
    """Placeholder implementation."""

    __struct_fields__: ClassVar[tuple[str, ...]] = ()
    __slots__ = ()

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


def convert_stub(  # noqa: PLR0913
    obj: Any,  # noqa: ARG001
    type: Any,  # noqa: A002,ARG001
    *,
    strict: bool = True,  # noqa: ARG001
    from_attributes: bool = False,  # noqa: ARG001
    dec_hook: "Optional[Any]" = None,  # noqa: ARG001
    builtin_types: "Optional[Any]" = None,  # noqa: ARG001
    str_keys: bool = False,  # noqa: ARG001
) -> Any:
    """Placeholder implementation."""
    return {}


class UnsetTypeStub(enum.Enum):
    UNSET = "UNSET"


UNSET_STUB = UnsetTypeStub.UNSET

# Try to import real implementations at runtime
try:
    from msgspec import UNSET, Struct, UnsetType, convert

    MSGSPEC_INSTALLED = True  # pyright: ignore[reportConstantRedefinition]
except ImportError:
    Struct = StructStub  # type: ignore[assignment,misc]
    UnsetType = UnsetTypeStub  # type: ignore[assignment,misc]
    UNSET = UNSET_STUB  # type: ignore[assignment] # pyright: ignore[reportConstantRedefinition]
    convert = convert_stub
    MSGSPEC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]


# Always define stub type for DTOData
@runtime_checkable
class DTODataStub(Protocol[T]):
    """Placeholder implementation."""

    __slots__ = ("_backend", "_data_as_builtins")

    def __init__(self, backend: Any, data_as_builtins: Any) -> None:
        """Initialize."""

    def create_instance(self, **kwargs: Any) -> T:
        return cast("T", kwargs)

    def update_instance(self, instance: T, **kwargs: Any) -> T:
        """Update instance."""
        return cast("T", kwargs)

    def as_builtins(self) -> Any:
        """Convert to builtins."""
        return {}


# Try to import real implementation at runtime
try:
    from litestar.dto.data_structures import DTOData

    LITESTAR_INSTALLED = True  # pyright: ignore[reportConstantRedefinition]
except ImportError:
    DTOData = DTODataStub  # type: ignore[assignment,misc]
    LITESTAR_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]


# Always define stub types for attrs
@dataclass_transform()
class AttrsInstanceStub:
    """Placeholder Implementation for attrs classes"""

    __attrs_attrs__: ClassVar[tuple[Any, ...]] = ()
    __slots__ = ()

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


def asdict_stub(*args: Any, **kwargs: Any) -> "dict[str, Any]":  # noqa: ARG001
    """Placeholder implementation"""
    return {}


def define_stub(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
    """Placeholder implementation"""
    return lambda cls: cls  # pyright: ignore[reportUnknownVariableType,reportUnknownLambdaType]


def field_stub(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
    """Placeholder implementation"""
    return None


def fields_stub(*args: Any, **kwargs: Any) -> "tuple[Any, ...]":  # noqa: ARG001
    """Placeholder implementation"""
    return ()


def has_stub(*args: Any, **kwargs: Any) -> bool:  # noqa: ARG001
    """Placeholder implementation"""
    return False


# Try to import real implementations at runtime
try:
    from attrs import AttrsInstance, asdict, define, field, fields, has

    ATTRS_INSTALLED = True  # pyright: ignore[reportConstantRedefinition]
except ImportError:
    AttrsInstance = AttrsInstanceStub  # type: ignore[misc]
    asdict = asdict_stub
    define = define_stub
    field = field_stub
    fields = fields_stub
    has = has_stub  # type: ignore[assignment]
    ATTRS_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

try:
    from cattrs import structure, unstructure

    CATTRS_INSTALLED = True  # pyright: ignore[reportConstantRedefinition]
except ImportError:

    def unstructure(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        """Placeholder implementation"""
        return {}

    def structure(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        """Placeholder implementation"""
        return {}

    CATTRS_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]  # pyright: ignore[reportConstantRedefinition]


class EmptyEnum(enum.Enum):
    """A sentinel enum used as placeholder."""

    EMPTY = 0


EmptyType = Union[Literal[EmptyEnum.EMPTY], UnsetType]
Empty: Final = EmptyEnum.EMPTY

__all__ = (
    "ATTRS_INSTALLED",
    "CATTRS_INSTALLED",
    "LITESTAR_INSTALLED",
    "MSGSPEC_INSTALLED",
    "PYDANTIC_INSTALLED",
    "UNSET",
    "UNSET_STUB",
    "AttrsInstance",
    "AttrsInstanceStub",
    "BaseModel",
    "BaseModelStub",
    "DTOData",
    "DTODataStub",
    "Empty",
    "EmptyEnum",
    "EmptyType",
    "FailFast",
    "FailFastStub",
    "Struct",
    "StructStub",
    "TypeAdapter",
    "TypeAdapterStub",
    "UnsetType",
    "UnsetTypeStub",
    "asdict",
    "asdict_stub",
    "convert",
    "convert_stub",
    "define",
    "define_stub",
    "field",
    "field_stub",
    "fields",
    "fields_stub",
    "has",
    "has_stub",
    "structure",
    "unstructure",
)

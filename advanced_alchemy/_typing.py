# ruff: noqa: RUF100, PLR0913, A002, DOC201, PLR6301, PLR0917, ARG004, ARG002, ARG001
"""Foundational type shims for optional dependencies.

Provides feature-detection flags and stub types used across the package
when optional libraries (pydantic, msgspec, attrs, cattrs, litestar,
sqlmodel, numpy) are not installed.

This module is the single source of truth for ``*_INSTALLED`` flags and
optional-dependency placeholder types.  Public re-exports live in
:mod:`advanced_alchemy.typing`.
"""

import enum
from dataclasses import dataclass
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, ClassVar, Final, Optional, Protocol, Union, cast, runtime_checkable

from typing_extensions import Literal, TypeVar, dataclass_transform

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapper
    from sqlalchemy.sql import FromClause


# ---------------------------------------------------------------------------
# Feature-detection flags (use ``find_spec`` to avoid eagerly importing).
# ---------------------------------------------------------------------------
ATTRS_INSTALLED = find_spec("attrs") is not None
CATTRS_INSTALLED = find_spec("cattrs") is not None
LITESTAR_INSTALLED = find_spec("litestar") is not None
MSGSPEC_INSTALLED = find_spec("msgspec") is not None
NUMPY_INSTALLED = find_spec("numpy") is not None
ORJSON_INSTALLED = find_spec("orjson") is not None
PYDANTIC_INSTALLED = find_spec("pydantic") is not None
SQLMODEL_INSTALLED = find_spec("sqlmodel") is not None


# ---------------------------------------------------------------------------
# Generic protocols and TypeVars.
# ---------------------------------------------------------------------------
T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


@runtime_checkable
class DataclassProtocol(Protocol):
    """Protocol for instance checking dataclasses."""

    __dataclass_fields__: "ClassVar[dict[str, Any]]"


@runtime_checkable
class DictProtocol(Protocol):
    """Protocol for objects with a __dict__ attribute."""

    __dict__: dict[str, Any]


# ---------------------------------------------------------------------------
# SQLModel placeholder.
# ---------------------------------------------------------------------------
class SQLModelBaseLike:
    """Placeholder for sqlmodel.SQLModel when the package is not installed.

    Declares the same structural attributes as :class:`ModelProtocol`
    so that type checkers can see SQLModel ``table=True`` models as
    protocol-compatible without requiring the real SQLModel package.
    """

    if TYPE_CHECKING:
        __table__: "FromClause"
        __mapper__: "Mapper[Any]"
        __name__: str

    model_fields: ClassVar[dict[str, Any]] = {}


if SQLMODEL_INSTALLED:
    from sqlmodel import SQLModel as SQLModelBase
else:
    SQLModelBase = SQLModelBaseLike  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Pydantic shims.
# ---------------------------------------------------------------------------
class BaseModelLike:
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


@dataclass
class FailFastStub:
    """Placeholder implementation for FailFast."""

    fail_fast: bool = True


try:
    from pydantic import BaseModel as _RealBaseModel
    from pydantic import FailFast as _RealFailFast
    from pydantic import TypeAdapter as _RealTypeAdapter

    BaseModel = _RealBaseModel
    TypeAdapter = _RealTypeAdapter
    FailFast = _RealFailFast
except ImportError:
    BaseModel = BaseModelLike  # type: ignore[assignment,misc]
    TypeAdapter = TypeAdapterStub  # type: ignore[assignment,misc]
    FailFast = FailFastStub  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Msgspec shims.
# ---------------------------------------------------------------------------
@dataclass_transform()
class StructLike:
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


try:
    from msgspec import UNSET as _REAL_UNSET
    from msgspec import Struct as _RealStruct
    from msgspec import UnsetType as _RealUnsetType
    from msgspec import convert as _real_convert

    Struct = _RealStruct
    UnsetType = _RealUnsetType
    UNSET = _REAL_UNSET
    convert = _real_convert
except ImportError:
    Struct = StructLike  # type: ignore[assignment,misc]
    UnsetType = UnsetTypeStub  # type: ignore[assignment,misc]
    UNSET = UNSET_STUB  # type: ignore[assignment] # pyright: ignore[reportConstantRedefinition]
    convert = convert_stub


# ---------------------------------------------------------------------------
# Litestar DTO shims.
# ---------------------------------------------------------------------------
@runtime_checkable
class DTODataLike(Protocol[T]):
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


try:
    from litestar.dto.data_structures import DTOData as _RealDTOData  # pyright: ignore[reportUnknownVariableType]

    DTOData = _RealDTOData
except ImportError:
    DTOData = DTODataLike  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Attrs shims.
# ---------------------------------------------------------------------------
@dataclass_transform()
class AttrsLike:
    """Placeholder Implementation for attrs classes"""

    __attrs_attrs__: ClassVar[tuple[Any, ...]] = ()
    __slots__ = ()

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


def attrs_asdict_stub(*args: Any, **kwargs: Any) -> "dict[str, Any]":  # noqa: ARG001
    """Placeholder implementation"""
    return {}


def attrs_define_stub(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
    """Placeholder implementation"""
    return lambda cls: cls  # pyright: ignore[reportUnknownVariableType,reportUnknownLambdaType]


def attrs_field_stub(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
    """Placeholder implementation"""
    return None


def attrs_fields_stub(*args: Any, **kwargs: Any) -> "tuple[Any, ...]":  # noqa: ARG001
    """Placeholder implementation"""
    return ()


def attrs_has_stub(*args: Any, **kwargs: Any) -> bool:  # noqa: ARG001
    """Placeholder implementation"""
    return False


class AttrsNothingStub:
    """Placeholder for attrs.NOTHING sentinel value"""

    def __repr__(self) -> str:
        return "NOTHING"


ATTRS_NOTHING_STUB = AttrsNothingStub()


try:
    from attrs import NOTHING as _real_attrs_nothing  # noqa: N811
    from attrs import AttrsInstance as _RealAttrsInstance  # pyright: ignore
    from attrs import asdict as _real_attrs_asdict
    from attrs import define as _real_attrs_define
    from attrs import field as _real_attrs_field
    from attrs import fields as _real_attrs_fields
    from attrs import has as _real_attrs_has

    AttrsInstance = _RealAttrsInstance
    attrs_asdict = _real_attrs_asdict
    attrs_define = _real_attrs_define
    attrs_field = _real_attrs_field
    attrs_fields = _real_attrs_fields
    attrs_has = _real_attrs_has
    attrs_nothing = _real_attrs_nothing
except ImportError:
    AttrsInstance = AttrsLike  # type: ignore[misc]
    attrs_asdict = attrs_asdict_stub
    attrs_define = attrs_define_stub
    attrs_field = attrs_field_stub
    attrs_fields = attrs_fields_stub
    attrs_has = attrs_has_stub  # type: ignore[assignment]
    attrs_nothing = ATTRS_NOTHING_STUB  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Cattrs shims.
# ---------------------------------------------------------------------------
try:
    from cattrs import structure as cattrs_structure
    from cattrs import unstructure as cattrs_unstructure
except ImportError:

    def cattrs_unstructure(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        """Placeholder implementation"""
        return {}

    def cattrs_structure(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        """Placeholder implementation"""
        return {}


# ---------------------------------------------------------------------------
# Generic sentinel for "no value supplied".
# ---------------------------------------------------------------------------
class EmptyEnum(enum.Enum):
    """A sentinel enum used as placeholder."""

    EMPTY = 0


EmptyType = Union[Literal[EmptyEnum.EMPTY], UnsetType]
Empty: Final = EmptyEnum.EMPTY


__all__ = (
    "ATTRS_INSTALLED",
    "ATTRS_NOTHING_STUB",
    "CATTRS_INSTALLED",
    "LITESTAR_INSTALLED",
    "MSGSPEC_INSTALLED",
    "NUMPY_INSTALLED",
    "ORJSON_INSTALLED",
    "PYDANTIC_INSTALLED",
    "SQLMODEL_INSTALLED",
    "UNSET",
    "UNSET_STUB",
    "AttrsInstance",
    "AttrsLike",
    "AttrsNothingStub",
    "BaseModel",
    "BaseModelLike",
    "DTOData",
    "DTODataLike",
    "DataclassProtocol",
    "DictProtocol",
    "Empty",
    "EmptyEnum",
    "EmptyType",
    "FailFast",
    "FailFastStub",
    "SQLModelBase",
    "SQLModelBaseLike",
    "Struct",
    "StructLike",
    "T",
    "T_co",
    "TypeAdapter",
    "TypeAdapterStub",
    "UnsetType",
    "UnsetTypeStub",
    "attrs_asdict",
    "attrs_asdict_stub",
    "attrs_define",
    "attrs_define_stub",
    "attrs_field",
    "attrs_field_stub",
    "attrs_fields",
    "attrs_fields_stub",
    "attrs_has",
    "attrs_has_stub",
    "attrs_nothing",
    "cattrs_structure",
    "cattrs_unstructure",
    "convert",
    "convert_stub",
)

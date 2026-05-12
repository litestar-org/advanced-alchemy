"""Configurable JSON serialization with Protocol-based architecture.

This module provides a flexible serialization system that supports:
- Custom type encoders via the ``type_encoders`` parameter
- Multiple backend support (msgspec, orjson, standard library)
- Thread-safe caching of serializer instances
- Integration with Litestar's type_encoders pattern

Example:
    Basic usage with default encoders::

        >>> from advanced_alchemy.utils.serialization import encode_json, decode_json
        >>> import datetime
        >>> encode_json({"date": datetime.date.today()})
        '{"date":"2025-12-17"}'

    Custom type encoders::

        >>> from decimal import Decimal
        >>> class Money:
        ...     def __init__(self, amount: Decimal):
        ...         self.amount = amount
        >>> encode_json(
        ...     {"price": Money(Decimal("19.99"))},
        ...     type_encoders={Money: lambda m: str(m.amount)}
        ... )
        '{"price":"19.99"}'
"""

import datetime
import enum
import json
import threading
from abc import ABC, abstractmethod
from collections.abc import Mapping
from decimal import Decimal
from functools import lru_cache
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path, PurePath
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Final,
    Literal,
    Optional,
    Protocol,
    TypeVar,
    Union,
    cast,
    overload,
    runtime_checkable,
)
from uuid import UUID

from sqlalchemy import RowMapping
from typing_extensions import TypeAlias, TypeGuard

from advanced_alchemy.typing import (
    ATTRS_INSTALLED,
    CATTRS_INSTALLED,
    LITESTAR_INSTALLED,
    MSGSPEC_INSTALLED,
    NUMPY_INSTALLED,
    ORJSON_INSTALLED,
    PYDANTIC_INSTALLED,
    SQLMODEL_INSTALLED,
    UNSET,
    AttrsInstance,
    AttrsLike,
    BaseModel,
    BaseModelLike,
    DictProtocol,
    DTOData,
    DTODataLike,
    FailFast,
    Struct,
    StructLike,
    attrs_nothing,
    convert,
)
from advanced_alchemy.typing import attrs_asdict as asdict
from advanced_alchemy.typing import attrs_fields as fields
from advanced_alchemy.typing import attrs_has as has
from advanced_alchemy.typing import cattrs_structure as structure
from advanced_alchemy.typing import cattrs_unstructure as unstructure

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.engine.row import Row

    from advanced_alchemy.filters import StatementFilter
    from advanced_alchemy.repository.typing import ModelT

__all__ = (
    "ATTRS_INSTALLED",
    "CATTRS_INSTALLED",
    "DEFAULT_TYPE_ENCODERS",
    "MSGSPEC_INSTALLED",
    "PYDANTIC_INSTALLED",
    "PYDANTIC_USE_FAILFAST",
    "UNSET",
    "AttrsInstance",
    "BaseModel",
    "BulkModelDictT",
    "FilterTypeT",
    "JSONSerializer",
    "ModelDTOT",
    "ModelDictListT",
    "ModelDictT",
    "MsgspecSerializer",
    "OrjsonSerializer",
    "PydanticOrMsgspecT",
    "StandardLibSerializer",
    "Struct",
    "SupportedSchemaModel",
    "TypeEncodersMap",
    "asdict",
    "attrs_nothing",
    "convert",
    "convert_date_to_iso",
    "convert_datetime_to_gmt_iso",
    "decode_complex_type",
    "decode_json",
    "encode_complex_type",
    "encode_json",
    "fields",
    "get_attrs_fields",
    "get_serializer",
    "get_type_adapter",
    "has",
    "has_dict_attribute",
    "is_attrs_instance",
    "is_attrs_instance_with_field",
    "is_attrs_instance_without_field",
    "is_attrs_schema",
    "is_dataclass",
    "is_dataclass_with_field",
    "is_dataclass_without_field",
    "is_dict",
    "is_dict_with_field",
    "is_dict_without_field",
    "is_dto_data",
    "is_msgspec_struct",
    "is_msgspec_struct_with_field",
    "is_msgspec_struct_without_field",
    "is_pydantic_model",
    "is_pydantic_model_with_field",
    "is_pydantic_model_without_field",
    "is_row_mapping",
    "is_schema",
    "is_schema_or_dict",
    "is_schema_or_dict_with_field",
    "is_schema_or_dict_without_field",
    "is_schema_with_field",
    "is_schema_without_field",
    "is_sqlmodel_table_model",
    "schema_dump",
    "structure",
    "unstructure",
)

# Type aliases
TypeEncodersMap = Mapping[type, Callable[[Any], Any]]
"""Mapping of types to encoder functions for custom serialization."""

T = TypeVar("T")

PYDANTIC_USE_FAILFAST = False  # leave permanently disabled for now

FilterTypeT = TypeVar("FilterTypeT", bound="StatementFilter")
"""Type variable for filter types."""

SupportedSchemaModel: TypeAlias = Union[StructLike, BaseModelLike, AttrsLike]
"""Type alias for objects that support schema conversion methods (model_dump, asdict, etc.)."""

ModelDTOT = TypeVar("ModelDTOT", bound="Union[SupportedSchemaModel, Any]")
"""Type variable for model DTOs."""

PydanticOrMsgspecT = SupportedSchemaModel
"""Type alias for supported schema models."""

ModelDictT: TypeAlias = "Union[dict[str, Any], ModelT, SupportedSchemaModel, DTODataLike[ModelT], Any]"
"""Type alias for model dictionaries."""

ModelDictListT: TypeAlias = "Sequence[Union[dict[str, Any], ModelT, SupportedSchemaModel, Any]]"
"""Type alias for model dictionary lists."""

BulkModelDictT: TypeAlias = (
    "Union[Sequence[Union[dict[str, Any], ModelT, SupportedSchemaModel, Any]], DTODataLike[list[ModelT]]]"
)
"""Type alias for bulk model dictionaries."""


# ============================================================================
# Helper functions
# ============================================================================


def convert_datetime_to_gmt_iso(dt: datetime.datetime) -> str:
    """Convert datetime to ISO 8601 format with UTC timezone.

    If the datetime is naive (no timezone), UTC is assumed.
    The ``+00:00`` suffix is replaced with ``Z`` for consistency.

    Args:
        dt: The datetime to convert.

    Returns:
        ISO 8601 formatted datetime string with ``Z`` suffix for UTC.

    Example:
        >>> import datetime
        >>> dt = datetime.datetime(2025, 12, 17, 10, 30, 0)
        >>> convert_datetime_to_gmt_iso(dt)
        '2025-12-17T10:30:00Z'
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def convert_date_to_iso(dt: datetime.date) -> str:
    """Convert date to ISO 8601 format.

    Args:
        dt: The date to convert.

    Returns:
        ISO 8601 formatted date string (YYYY-MM-DD).

    Example:
        >>> import datetime
        >>> convert_date_to_iso(datetime.date(2025, 12, 17))
        '2025-12-17'
    """
    return dt.isoformat()


@lru_cache(typed=True)
def get_type_adapter(f: "type[T]") -> Any:
    """Caches and returns a pydantic type adapter."""
    from advanced_alchemy.typing import TypeAdapter

    if PYDANTIC_USE_FAILFAST:
        return TypeAdapter(Annotated[f, FailFast()])  # pyright: ignore
    return TypeAdapter(f)


@lru_cache(maxsize=128, typed=True)
def get_attrs_fields(cls: Any) -> "tuple[Any, ...]":
    """Caches and returns attrs fields for a given attrs class."""
    if ATTRS_INSTALLED:
        return fields(cls)  # type: ignore[no-any-return]
    return ()


def is_dto_data(v: Any) -> TypeGuard[DTODataLike[Any]]:
    """Check if a value is a Litestar DTOData object."""
    return LITESTAR_INSTALLED and isinstance(v, DTOData)


def is_pydantic_model(v: Any) -> TypeGuard[BaseModelLike]:
    """Check if a value is a pydantic model."""
    if not PYDANTIC_INSTALLED:
        return False
    if isinstance(v, type):
        try:
            return issubclass(v, BaseModel)
        except TypeError:
            return False
    return isinstance(v, BaseModel)


def is_sqlmodel_table_model(v: Any) -> bool:
    """Check if a value is a SQLModel table model instance or class."""
    if not SQLMODEL_INSTALLED:
        return False
    if isinstance(v, type):
        try:
            return issubclass(v, BaseModel) and hasattr(v, "__mapper__")
        except TypeError:
            return False
    return isinstance(v, BaseModel) and hasattr(v, "__mapper__")


def is_msgspec_struct(v: Any) -> TypeGuard[StructLike]:
    """Check if a value is a msgspec struct."""
    return MSGSPEC_INSTALLED and isinstance(v, Struct)


def is_attrs_instance(obj: Any) -> TypeGuard[AttrsLike]:
    """Check if a value is an attrs class instance."""
    return ATTRS_INSTALLED and has(obj.__class__)


def is_attrs_schema(cls: Any) -> TypeGuard["type[AttrsLike]"]:
    """Check if a class type is an attrs schema."""
    return ATTRS_INSTALLED and has(cls)


def is_dataclass(obj: Any) -> TypeGuard[Any]:
    """Check if an object is a dataclass."""
    return hasattr(obj, "__dataclass_fields__")


def is_dataclass_with_field(obj: Any, field_name: str) -> TypeGuard[object]:
    """Check if an object is a dataclass and has a specific field."""
    return is_dataclass(obj) and hasattr(obj, field_name)


def is_dataclass_without_field(obj: Any, field_name: str) -> TypeGuard[object]:
    """Check if an object is a dataclass and does not have a specific field."""
    return is_dataclass(obj) and not hasattr(obj, field_name)


def is_attrs_instance_with_field(v: Any, field_name: str) -> TypeGuard[AttrsLike]:
    """Check if an attrs instance has a specific field."""
    return is_attrs_instance(v) and hasattr(v, field_name)


def is_attrs_instance_without_field(v: Any, field_name: str) -> TypeGuard[AttrsLike]:
    """Check if an attrs instance does not have a specific field."""
    return is_attrs_instance(v) and not hasattr(v, field_name)


def is_dict(v: Any) -> TypeGuard[dict[str, Any]]:
    """Check if a value is a dictionary."""
    return isinstance(v, dict)


def has_dict_attribute(obj: Any) -> "TypeGuard[DictProtocol]":
    """Check if an object has a __dict__ attribute."""
    return obj is not None and hasattr(obj, "__dict__")


def is_row_mapping(v: Any) -> TypeGuard["RowMapping"]:
    """Check if a value is a SQLAlchemy RowMapping."""
    return isinstance(v, RowMapping)


def is_dict_with_field(v: Any, field_name: str) -> TypeGuard[dict[str, Any]]:
    """Check if a dictionary has a specific field."""
    return is_dict(v) and field_name in v


def is_dict_without_field(v: Any, field_name: str) -> TypeGuard[dict[str, Any]]:
    """Check if a dictionary does not have a specific field."""
    return is_dict(v) and field_name not in v


def is_pydantic_model_with_field(v: Any, field_name: str) -> TypeGuard[BaseModelLike]:
    """Check if a pydantic model has a specific field."""
    return is_pydantic_model(v) and hasattr(v, field_name)


def is_pydantic_model_without_field(v: Any, field_name: str) -> TypeGuard[BaseModelLike]:
    """Check if a pydantic model does not have a specific field."""
    return is_pydantic_model(v) and not hasattr(v, field_name)


def is_msgspec_struct_with_field(v: Any, field_name: str) -> TypeGuard[StructLike]:
    """Check if a msgspec struct has a specific field."""
    return is_msgspec_struct(v) and hasattr(v, field_name)


def is_msgspec_struct_without_field(v: Any, field_name: str) -> "TypeGuard[StructLike]":
    """Check if a msgspec struct does not have a specific field."""
    return is_msgspec_struct(v) and not hasattr(v, field_name)


def is_schema(v: Any) -> "TypeGuard[SupportedSchemaModel]":
    """Check if a value is a msgspec Struct, Pydantic model, or attrs instance."""
    if is_sqlmodel_table_model(v):
        return False
    return is_msgspec_struct(v) or is_pydantic_model(v) or is_attrs_instance(v)


def is_schema_or_dict(v: Any) -> "TypeGuard[Union[SupportedSchemaModel, dict[str, Any]]]":
    """Check if a value is a msgspec Struct, Pydantic model, attrs class, or dict."""
    return is_schema(v) or is_dict(v)


def is_schema_with_field(v: Any, field_name: str) -> "TypeGuard[SupportedSchemaModel]":
    """Check if a value is a msgspec Struct, Pydantic model, or attrs instance with a specific field."""
    if is_sqlmodel_table_model(v):
        return False
    return (
        is_msgspec_struct_with_field(v, field_name)
        or is_pydantic_model_with_field(v, field_name)
        or is_attrs_instance_with_field(v, field_name)
    )


def is_schema_without_field(v: Any, field_name: str) -> "TypeGuard[SupportedSchemaModel]":
    """Check if a value is a msgspec Struct, Pydantic model, or attrs instance without a specific field."""
    return is_schema(v) and not hasattr(v, field_name)


def is_schema_or_dict_with_field(v: Any, field_name: str) -> "TypeGuard[Union[SupportedSchemaModel, dict[str, Any]]]":
    """Check if a value is a msgspec Struct, Pydantic model, attrs instance, or dict with a specific field."""
    return is_schema_with_field(v, field_name) or is_dict_with_field(v, field_name)


def is_schema_or_dict_without_field(
    v: Any, field_name: str
) -> "TypeGuard[Union[SupportedSchemaModel, dict[str, Any]]]":
    """Check if a value is a msgspec Struct, Pydantic model, attrs instance, or dict without a specific field."""
    return is_schema_or_dict(v) and not is_schema_or_dict_with_field(v, field_name)


@overload
def schema_dump(data: "RowMapping", exclude_unset: bool = True) -> "dict[str, Any]": ...


@overload
def schema_dump(data: "Row[Any]", exclude_unset: bool = True) -> "dict[str, Any]": ...


@overload
def schema_dump(data: "DTODataLike[Any]", exclude_unset: bool = True) -> "dict[str, Any]": ...


@overload
def schema_dump(data: "ModelT", exclude_unset: bool = True) -> "ModelT": ...  # pyright: ignore[reportOverlappingOverload]


@overload
def schema_dump(
    data: Any,
    exclude_unset: bool = True,
) -> "dict[str, Any]": ...


def schema_dump(  # noqa: PLR0911
    data: "Union[dict[str, Any], ModelT, SupportedSchemaModel, DTODataLike[ModelT], RowMapping, Row[Any]]",
    exclude_unset: bool = True,
) -> "Union[dict[str, Any], ModelT]":
    """Dump a data object to a dictionary."""
    if is_dict(data):
        return data
    if is_row_mapping(data):
        return dict(data)
    if is_sqlmodel_table_model(data):
        return cast("ModelT", data)
    if is_pydantic_model(data):
        return data.model_dump(exclude_unset=exclude_unset)
    if is_msgspec_struct(data):
        if exclude_unset:
            return {
                f: getattr(data, f)
                for f in data.__struct_fields__
                if hasattr(data, f) and getattr(data, f) is not UNSET
            }
        return {f: getattr(data, f, None) for f in data.__struct_fields__}
    if is_attrs_instance(data):
        if exclude_unset:
            # Filter out attrs.NOTHING values for partial updates.
            def filter_unset_attrs(attr: Any, value: Any) -> bool:  # noqa: ARG001
                return value is not attrs_nothing

            return asdict(data, filter=filter_unset_attrs)
        if CATTRS_INSTALLED:
            return unstructure(data)  # type: ignore[no-any-return]
        return asdict(data)
    if is_dto_data(data):
        return cast("dict[str, Any]", data.as_builtins())
    if has_dict_attribute(data):
        return data.__dict__
    return cast("ModelT", data)


# ============================================================================
# Default type encoders
# ============================================================================


def _build_default_type_encoders() -> dict[type, Callable[[Any], Any]]:
    """Build the default type encoders dictionary.

    This function constructs the default encoders, including optional
    encoders for numpy and pydantic if those packages are installed.

    Returns:
        Dictionary mapping types to encoder functions.
    """
    encoders: dict[type, Callable[[Any], Any]] = {
        # Datetime types
        datetime.datetime: convert_datetime_to_gmt_iso,
        datetime.date: convert_date_to_iso,
        datetime.time: lambda v: v.isoformat(),
        datetime.timedelta: lambda v: v.total_seconds(),
        # Numeric types
        Decimal: str,  # Preserve precision as string
        # UUID and path types
        UUID: str,
        Path: str,
        PurePath: str,
        # Network types
        IPv4Address: str,
        IPv4Interface: str,
        IPv4Network: str,
        IPv6Address: str,
        IPv6Interface: str,
        IPv6Network: str,
        # Collection types
        frozenset: list,
        set: list,
        # Bytes
        bytes: lambda v: v.decode("utf-8", errors="replace"),
        # Enum (use .value to get the underlying value)
        enum.Enum: lambda v: v.value,
    }

    # Optional NumPy support
    if NUMPY_INSTALLED:
        import numpy as np

        encoders[np.ndarray] = lambda v: v.tolist()
        encoders[np.integer] = int
        encoders[np.floating] = float
        encoders[np.bool_] = bool

    # Optional Pydantic support
    if PYDANTIC_INSTALLED:
        from pydantic import BaseModel

        encoders[BaseModel] = lambda v: v.model_dump(mode="json")

    return encoders


DEFAULT_TYPE_ENCODERS: Final[dict[type, Callable[[Any], Any]]] = _build_default_type_encoders()
"""Default type encoders for common Python types.

These encoders handle serialization of types not natively supported
by JSON serializers. Users can override these by passing custom
``type_encoders`` to serializer functions.

Supported types:
    - ``datetime.datetime``: ISO 8601 with UTC timezone (Z suffix)
    - ``datetime.date``: ISO 8601 date format
    - ``datetime.time``: ISO 8601 time format
    - ``datetime.timedelta``: Total seconds as float
    - ``Decimal``: String representation (preserves precision)
    - ``UUID``: String representation
    - ``Path``, ``PurePath``: String representation
    - ``IPv4Address``, ``IPv6Address``, etc.: String representation
    - ``set``, ``frozenset``: Converted to list
    - ``bytes``: UTF-8 decoded string
    - ``enum.Enum``: Value of the enum member
    - ``numpy.ndarray``: Converted to list (if numpy installed)
    - ``pydantic.BaseModel``: model_dump with mode="json" (if pydantic installed)
"""


# ============================================================================
# Protocol and base classes
# ============================================================================


@runtime_checkable
class JSONSerializer(Protocol):
    """Protocol defining the JSON serialization interface.

    Implement this protocol to create custom serializers that integrate
    with Advanced Alchemy's serialization system.

    Example:
        >>> class MySerializer:
        ...     def encode(
        ...         self, data: Any, *, as_bytes: bool = False
        ...     ) -> "Union[str, bytes]":
        ...         # Custom encoding logic
        ...         pass
        ...
        ...     def decode(
        ...         self,
        ...         data: "Union[str, bytes]",
        ...         *,
        ...         decode_bytes: bool = True,
        ...     ) -> Any:
        ...         # Custom decoding logic
        ...         pass
    """

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return str.

        Returns:
            JSON string or bytes representation.
        """
        ...

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON to Python object.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        ...


class BaseJSONSerializer(ABC):
    """Abstract base class for JSON serializers.

    Provides common functionality for serializer implementations including
    type encoder merging and enc_hook creation.
    """

    __slots__ = ("_custom_type_encoders", "_type_encoders")

    def __init__(self, type_encoders: "Optional[TypeEncodersMap]" = None) -> None:
        """Initialize serializer with optional custom type encoders.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
                User-provided encoders take precedence over defaults.
        """
        self._custom_type_encoders: dict[type, Callable[[Any], Any]] = dict(type_encoders or {})
        self._type_encoders: dict[type, Callable[[Any], Any]] = {
            **DEFAULT_TYPE_ENCODERS,
            **(type_encoders or {}),
        }

    @staticmethod
    def _get_type_encoder(
        value: Any,
        type_encoders: Mapping[type, Callable[[Any], Any]],
    ) -> "Optional[Callable[[Any], Any]]":
        """Return the encoder matching ``value`` by exact type or MRO."""
        for base in value.__class__.__mro__[:-1]:
            encoder = type_encoders.get(base)
            if encoder is not None:
                return encoder
        return None

    def _encode_mapping_key_with_custom_type_encoder(self, key: Any) -> Any:
        encoder = self._get_type_encoder(key, self._custom_type_encoders)
        return encoder(key) if encoder is not None else key

    def _apply_custom_type_encoders_to_mapping(self, value: Mapping[object, object]) -> dict[Any, Any]:
        return {
            self._encode_mapping_key_with_custom_type_encoder(key): self._apply_custom_type_encoders(item)
            for key, item in value.items()
        }

    def _apply_custom_type_encoders_to_list(self, value: list[object]) -> list[Any]:
        return [self._apply_custom_type_encoders(item) for item in value]

    def _apply_custom_type_encoders_to_tuple(self, value: tuple[object, ...]) -> tuple[Any, ...]:
        return tuple(self._apply_custom_type_encoders(item) for item in value)

    def _apply_custom_type_encoders_to_set(self, value: Union[set[object], frozenset[object]]) -> list[Any]:
        return [self._apply_custom_type_encoders(item) for item in value]

    def _apply_custom_type_encoders(self, value: Any) -> Any:
        """Apply user-provided type encoders before backend-native encoding."""
        encoder = self._get_type_encoder(value, self._custom_type_encoders)
        if encoder is not None:
            return encoder(value)

        if isinstance(value, Mapping):
            return self._apply_custom_type_encoders_to_mapping(cast("Mapping[object, object]", value))
        if isinstance(value, list):
            return self._apply_custom_type_encoders_to_list(cast("list[object]", value))
        if isinstance(value, tuple):
            return self._apply_custom_type_encoders_to_tuple(cast("tuple[object, ...]", value))
        if isinstance(value, (set, frozenset)):
            return self._apply_custom_type_encoders_to_set(cast("Union[set[object], frozenset[object]]", value))
        return value

    def _prepare_data_for_encode(self, data: Any) -> Any:
        if not self._custom_type_encoders:
            return data
        return self._apply_custom_type_encoders(data)

    def _create_enc_hook(self) -> "Callable[[Any], Any]":
        """Create an encoding hook function from type_encoders.

        The hook walks the MRO of the value's type to find a matching
        encoder, allowing encoders for parent classes to handle subclasses.

        Returns:
            Encoding hook function suitable for msgspec/orjson.
        """
        type_encoders = self._type_encoders

        def enc_hook(value: Any) -> Any:
            encoder = self._get_type_encoder(value, type_encoders)
            if encoder is not None:
                return encoder(value)
            # Fallback: try string conversion
            try:
                return str(value)
            except Exception as exc:
                msg = f"Cannot serialize {type(value).__name__}"
                raise TypeError(msg) from exc

        return enc_hook

    @overload
    @abstractmethod
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    @abstractmethod
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    @abstractmethod
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    @abstractmethod
    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON."""
        ...

    @abstractmethod
    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON to Python object."""
        ...


# ============================================================================
# Serializer implementations
# ============================================================================


class MsgspecSerializer(BaseJSONSerializer):
    """High-performance JSON serializer using msgspec.

    This is the preferred serializer when msgspec is available, offering
    the best performance for JSON encoding/decoding.

    Example:
        >>> serializer = MsgspecSerializer()
        >>> serializer.encode({"key": "value"})
        '{"key":"value"}'

        >>> # With custom type encoders
        >>> serializer = MsgspecSerializer(type_encoders={set: sorted})
        >>> serializer.encode({"items": {3, 1, 2}})
        '{"items":[1,2,3]}'
    """

    __slots__ = ("_decoder", "_enc_hook", "_encoder")

    def __init__(
        self,
        type_encoders: "Optional[TypeEncodersMap]" = None,
        enc_hook: "Optional[Callable[[Any], Any]]" = None,
    ) -> None:
        """Initialize msgspec serializer.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
            enc_hook: Optional custom encoding hook. If provided, type_encoders
                is ignored and this hook is used directly for complete control.
        """
        from msgspec.json import Decoder, Encoder

        super().__init__(None if enc_hook is not None else type_encoders)

        self._enc_hook = enc_hook if enc_hook is not None else self._create_enc_hook()
        self._encoder: Final = Encoder(enc_hook=self._enc_hook)
        self._decoder: Final = Decoder()

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON using msgspec.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return UTF-8 string.

        Returns:
            JSON representation as string or bytes.
        """
        result = self._encoder.encode(self._prepare_data_for_encode(data))
        return result if as_bytes else result.decode("utf-8")

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON using msgspec.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not decode_bytes:
            return data
        return self._decoder.decode(data)


class OrjsonSerializer(BaseJSONSerializer):
    """High-performance JSON serializer using orjson.

    Provides excellent performance with native support for datetime,
    UUID, and numpy serialization.

    Example:
        >>> serializer = OrjsonSerializer()
        >>> serializer.encode({"key": "value"})
        '{"key":"value"}'
    """

    __slots__ = ("_enc_hook",)

    def __init__(self, type_encoders: "Optional[TypeEncodersMap]" = None) -> None:
        """Initialize orjson serializer.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
        """
        super().__init__(type_encoders)
        self._enc_hook = self._create_enc_hook()

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON using orjson.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return UTF-8 string.

        Returns:
            JSON representation as string or bytes.
        """
        import orjson  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]

        orjson_module: Any = orjson
        options: int = orjson_module.OPT_NAIVE_UTC | orjson_module.OPT_SERIALIZE_UUID
        if NUMPY_INSTALLED:
            options |= orjson_module.OPT_SERIALIZE_NUMPY

        result: bytes = orjson_module.dumps(self._prepare_data_for_encode(data), default=self._enc_hook, option=options)
        return result if as_bytes else result.decode("utf-8")

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON using orjson.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        import orjson  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]

        orjson_module: Any = orjson
        if isinstance(data, bytes) and not decode_bytes:
            return data
        return orjson_module.loads(data)


class StandardLibSerializer(BaseJSONSerializer):
    """JSON serializer using Python's standard library.

    Fallback serializer when neither msgspec nor orjson is available.
    Slower than the alternatives but always available.

    Example:
        >>> serializer = StandardLibSerializer()
        >>> serializer.encode({"key": "value"})
        '{"key": "value"}'
    """

    __slots__ = ("_enc_hook",)

    def __init__(self, type_encoders: "Optional[TypeEncodersMap]" = None) -> None:
        """Initialize standard library serializer.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
        """
        super().__init__(type_encoders)
        self._enc_hook = self._create_enc_hook()

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON using standard library.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return string.

        Returns:
            JSON representation as string or bytes.
        """
        result = json.dumps(self._prepare_data_for_encode(data), default=self._enc_hook)
        return result.encode("utf-8") if as_bytes else result

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON using standard library.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        if isinstance(data, bytes):
            if not decode_bytes:
                return data
            data = data.decode("utf-8")
        return json.loads(data)


# ============================================================================
# Serializer factory with caching
# ============================================================================

_serializer_cache: "dict[frozenset[tuple[type, int]], JSONSerializer]" = {}
_cache_lock: Final[threading.RLock] = threading.RLock()
_default_serializer: "Optional[JSONSerializer]" = None


def _create_default_serializer() -> "JSONSerializer":
    """Create the default serializer based on available libraries.

    Priority: msgspec > orjson > standard library

    Returns:
        Best available JSON serializer.
    """
    if MSGSPEC_INSTALLED:
        return MsgspecSerializer()
    if ORJSON_INSTALLED:
        return OrjsonSerializer()
    return StandardLibSerializer()


def _create_serializer(type_encoders: "TypeEncodersMap") -> "JSONSerializer":
    """Create a serializer with custom type encoders.

    Args:
        type_encoders: Custom type encoders mapping.

    Returns:
        JSON serializer configured with the given encoders.
    """
    if MSGSPEC_INSTALLED:
        return MsgspecSerializer(type_encoders=type_encoders)
    if ORJSON_INSTALLED:
        return OrjsonSerializer(type_encoders=type_encoders)
    return StandardLibSerializer(type_encoders=type_encoders)


def get_serializer(type_encoders: "Optional[TypeEncodersMap]" = None) -> "JSONSerializer":
    """Get a cached serializer instance.

    This factory function returns cached serializer instances to avoid
    recreating encoders for the same configuration. The default serializer
    (no custom type_encoders) is a singleton for maximum performance.

    Args:
        type_encoders: Optional mapping of types to encoder functions.
            If None, returns the default singleton serializer.

    Returns:
        A JSONSerializer instance configured with the given type encoders.

    Example:
        >>> # Default serializer (singleton)
        >>> s1 = get_serializer()
        >>> s2 = get_serializer()
        >>> s1 is s2
        True

        >>> # Custom type encoders (cached by configuration)
        >>> encoders = {str: lambda s: s.upper()}
        >>> s3 = get_serializer(encoders)
        >>> s4 = get_serializer(encoders)
        >>> s3 is s4
        True
    """
    global _default_serializer  # noqa: PLW0603

    if type_encoders is None:
        with _cache_lock:
            if _default_serializer is None:
                _default_serializer = _create_default_serializer()
            return _default_serializer

    # Create hashable cache key using type and function id
    # Note: Different lambda objects create different keys even if equivalent
    try:
        cache_key = frozenset((k, id(v)) for k, v in type_encoders.items())
    except TypeError:
        # Fallback for unhashable keys - create without caching
        return _create_serializer(type_encoders)

    with _cache_lock:
        if cache_key not in _serializer_cache:
            _serializer_cache[cache_key] = _create_serializer(type_encoders)
        return _serializer_cache[cache_key]


# ============================================================================
# Public API functions
# ============================================================================


@overload
def encode_json(data: Any) -> str: ...


@overload
def encode_json(data: Any, *, as_bytes: Literal[False]) -> str: ...


@overload
def encode_json(data: Any, *, as_bytes: Literal[True]) -> bytes: ...


@overload
def encode_json(data: Any, *, type_encoders: "TypeEncodersMap") -> str: ...


@overload
def encode_json(data: Any, *, type_encoders: TypeEncodersMap, as_bytes: Literal[False]) -> str: ...


@overload
def encode_json(data: Any, *, type_encoders: TypeEncodersMap, as_bytes: Literal[True]) -> bytes: ...


def encode_json(
    data: Any,
    *,
    type_encoders: "Optional[TypeEncodersMap]" = None,
    as_bytes: bool = False,
) -> "Union[str, bytes]":
    """Encode data to JSON with optional custom type encoders.

    This is the primary interface for JSON encoding in Advanced Alchemy.
    It supports custom type encoders that can be passed per-call.

    Args:
        data: Data to encode to JSON.
        type_encoders: Optional mapping of types to encoder functions.
            These are merged with DEFAULT_TYPE_ENCODERS, with user
            encoders taking precedence.
        as_bytes: If True, return bytes; otherwise return str.

    Returns:
        JSON representation of data as string or bytes.

    Example:
        >>> import datetime
        >>> encode_json({"date": datetime.date(2025, 12, 17)})
        '{"date":"2025-12-17"}'

        >>> # Custom type encoder
        >>> class Point:
        ...     def __init__(self, x, y):
        ...         self.x, self.y = x, y
        >>> encode_json(
        ...     {"point": Point(1, 2)},
        ...     type_encoders={Point: lambda p: [p.x, p.y]},
        ... )
        '{"point":[1,2]}'

        >>> # Return bytes
        >>> encode_json({"key": "value"}, as_bytes=True)
        b'{"key":"value"}'
    """
    serializer = get_serializer(type_encoders)
    return serializer.encode(data, as_bytes=as_bytes)


def decode_json(data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
    """Decode JSON string or bytes to Python object.

    Args:
        data: JSON string or bytes to decode.
        decode_bytes: If True, decode bytes input. If False, bytes
            are returned as-is without decoding.

    Returns:
        Decoded Python object.

    Example:
        >>> decode_json('{"key": "value"}')
        {'key': 'value'}

        >>> decode_json(b'{"key": "value"}')
        {'key': 'value'}
    """
    serializer = get_serializer()
    return serializer.decode(data, decode_bytes=decode_bytes)


def encode_complex_type(obj: Any) -> Any:  # noqa: PLR0911
    """Convert an object to a JSON-serializable format if possible.

    Handles types that are not natively JSON serializable:
    - datetime, date, time: ISO format strings
    - timedelta: total seconds as float
    - Decimal: string representation
    - bytes: hex string
    - UUID: string representation
    - set, frozenset: list

    Args:
        obj: The object to encode.

    Returns:
        A JSON-serializable representation of the object, or None if the type is not supported.
    """
    if isinstance(obj, datetime.datetime):
        return {"__type__": "datetime", "value": obj.isoformat()}
    if isinstance(obj, datetime.date):
        return {"__type__": "date", "value": obj.isoformat()}
    if isinstance(obj, datetime.time):
        return {"__type__": "time", "value": obj.isoformat()}
    if isinstance(obj, datetime.timedelta):
        return {"__type__": "timedelta", "value": obj.total_seconds()}
    if isinstance(obj, Decimal):
        return {"__type__": "decimal", "value": str(obj)}
    if isinstance(obj, bytes):
        return {"__type__": "bytes", "value": obj.hex()}
    if isinstance(obj, UUID):
        return {"__type__": "uuid", "value": str(obj)}
    if isinstance(obj, (set, frozenset)):
        items: list[Any] = list(cast("Union[set[Any], frozenset[Any]]", obj))  # type: ignore[redundant-cast]
        return {"__type__": "set", "value": items}
    return None


def decode_complex_type(value: Any) -> Any:
    """Recursively decode special type markers.

    Decodes the special `{"__type__": ..., "value": ...}` structures.
    """
    if isinstance(value, list):
        value_list = cast("list[Any]", value)  # type: ignore[redundant-cast]
        return [decode_complex_type(v) for v in value_list]

    if not isinstance(value, dict):
        return value

    # Decode any nested values first
    value_dict = cast("dict[Any, Any]", value)  # type: ignore[redundant-cast]
    decoded: dict[str, Any] = {str(k): decode_complex_type(v) for k, v in value_dict.items()}

    # Then decode "typed" marker dicts
    if "__type__" in decoded and "value" in decoded:
        return _decode_typed_marker(decoded)

    return decoded


def _decode_typed_marker(obj: dict[str, Any]) -> Any:  # noqa: PLR0911
    """Custom JSON decoder for special types.

    Args:
        obj: The dictionary to decode.

    Returns:
        The decoded object, or the original dict if not a special type.
    """
    type_name = obj["__type__"]
    value = obj["value"]

    if type_name == "datetime":
        return datetime.datetime.fromisoformat(value)
    if type_name == "date":
        return datetime.date.fromisoformat(value)
    if type_name == "time":
        return datetime.time.fromisoformat(value)
    if type_name == "timedelta":
        return datetime.timedelta(seconds=value)
    if type_name == "decimal":
        return Decimal(value)
    if type_name == "bytes":
        return bytes.fromhex(value)
    if type_name == "uuid":
        return UUID(value)
    if type_name == "set":
        return set(value)

    return obj
